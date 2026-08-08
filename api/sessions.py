"""Session Detection — groups plays into listening sessions with 30-min gap threshold."""
import json
import logging
from datetime import datetime, timedelta
from api.database import get_db

logger = logging.getLogger(__name__)

SESSION_GAP_MINUTES = 30
MAX_SEQUENCE_LENGTH = 10


async def update_session(user_id: int, play_data: dict) -> int | None:
    """Detect or create session for a play. Returns session_id."""
    now = datetime.utcnow()
    video_id = play_data.get("video_id")
    artist_id = play_data.get("artist_id")
    album_id = play_data.get("album_id")
    completed = play_data.get("completed", False)
    duration_played = play_data.get("duration_played", 0)

    with get_db() as db:
        last_play = db.execute(
            """SELECT id, session_id, played_at FROM listening_history
               WHERE user_id = ? AND session_id IS NOT NULL
               ORDER BY id DESC LIMIT 1""",
            (user_id,),
        ).fetchone()

        session_id = None

        if last_play and last_play["session_id"]:
            last_time = datetime.fromisoformat(last_play["played_at"])
            if (now - last_time) < timedelta(minutes=SESSION_GAP_MINUTES):
                session_id = last_play["session_id"]
            else:
                await compute_fingerprint(last_play["session_id"])

        if session_id is None:
            cursor = db.execute(
                """INSERT INTO listening_sessions (user_id, started_at)
                   VALUES (?, ?)""",
                (user_id, now),
            )
            session_id = cursor.lastrowid

        cur = db.execute(
            """INSERT OR IGNORE INTO session_songs
               (session_id, song_id, video_id, artist_id, album_id, play_order, completed, duration_played)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, video_id, video_id, artist_id, album_id,
             _get_next_play_order(db, session_id), completed, duration_played),
        )

        db.execute(
            """UPDATE listening_sessions
               SET songs_count = songs_count + ?,
                   ended_at = ?
               WHERE id = ?""",
            (cur.rowcount, now, session_id),
        )

        db.execute(
            """UPDATE listening_history SET session_id = ?
               WHERE id = (
                   SELECT id FROM listening_history
                   WHERE user_id = ? AND video_id = ? AND session_id IS NULL
                   ORDER BY id DESC LIMIT 1
               )""",
            (session_id, user_id, video_id),
        )

    await compute_fingerprint(session_id)
    return session_id


def _get_next_play_order(db, session_id: int) -> int:
    row = db.execute(
        "SELECT COALESCE(MAX(play_order), 0) + 1 FROM session_songs WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    return row[0]


async def compute_fingerprint(session_id: int) -> str | None:
    """Compute session fingerprint from session songs. Returns JSON string."""
    with get_db() as db:
        rows = db.execute(
            """SELECT video_id, artist_id, completed, duration_played
               FROM session_songs WHERE session_id = ? ORDER BY play_order""",
            (session_id,),
        ).fetchall()

        if not rows:
            return None

        artist_ids = []
        sequence = []
        completed_count = 0
        total_duration = 0
        song_count = len(rows)

        for row in rows:
            aid = row["artist_id"]
            if aid and aid not in artist_ids:
                artist_ids.append(aid)
            if aid and len(sequence) < MAX_SEQUENCE_LENGTH:
                sequence.append(aid)
            if row["completed"]:
                completed_count += 1
            total_duration += row["duration_played"] or 0

        fingerprint = {
            "artist_ids": artist_ids,
            "sequence": sequence,
            "completion_rate": round(completed_count / song_count, 2) if song_count else 0,
            "skip_rate": round(1 - (completed_count / song_count), 2) if song_count else 0,
            "avg_song_length": round(total_duration / song_count) if song_count else 0,
        }

        fp_json = json.dumps(fingerprint)
        db.execute(
            "UPDATE listening_sessions SET fingerprint_json = ? WHERE id = ?",
            (fp_json, session_id),
        )
        return fp_json


def get_recent_sessions(user_id: int, limit: int = 20) -> list[dict]:
    """Get recent sessions with fingerprints."""
    with get_db() as db:
        rows = db.execute(
            """SELECT id, started_at, ended_at, songs_count, fingerprint_json
               FROM listening_sessions WHERE user_id = ?
               ORDER BY started_at DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
