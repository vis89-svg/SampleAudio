"""Transition Recording — tracks sequential song listening patterns."""
import logging
from api.database import get_db

logger = logging.getLogger(__name__)


async def record_transition(user_id: int, play_data: dict):
    """Record a transition from the previous song to the current song."""
    video_id = play_data.get("video_id")
    artist_id = play_data.get("artist_id")
    completed = play_data.get("completed", False)
    skipped = play_data.get("skipped", False)

    with get_db() as db:
        prev_play = db.execute(
            """SELECT video_id, artist_id FROM listening_history
               WHERE user_id = ? AND video_id != ?
               ORDER BY played_at DESC LIMIT 1""",
            (user_id, video_id),
        ).fetchone()

        if not prev_play:
            return

        from_video_id = prev_play["video_id"]
        from_artist_id = prev_play["artist_id"]

        if from_video_id == video_id:
            return

        existing = db.execute(
            """SELECT id, transition_count, completed_count, skipped_count
               FROM song_transitions
               WHERE user_id = ? AND from_video_id = ? AND to_video_id = ?""",
            (user_id, from_video_id, video_id),
        ).fetchone()

        if existing:
            db.execute(
                """UPDATE song_transitions
                   SET transition_count = transition_count + 1,
                       completed_count = completed_count + ?,
                       skipped_count = skipped_count + ?,
                       last_seen = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (1 if completed else 0, 1 if skipped else 0, existing["id"]),
            )
        else:
            db.execute(
                """INSERT INTO song_transitions
                   (user_id, from_video_id, to_video_id, from_artist_id, to_artist_id,
                    completed_count, skipped_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, from_video_id, video_id, from_artist_id, artist_id,
                 1 if completed else 0, 1 if skipped else 0),
            )


async def get_top_transitions(user_id: int, from_video_id: str, limit: int = 10) -> list[dict]:
    """Get top transitions from a given song."""
    with get_db() as db:
        rows = db.execute(
            """SELECT to_video_id, to_artist_id, transition_count, completed_count, skipped_count
               FROM song_transitions
               WHERE user_id = ? AND from_video_id = ?
               ORDER BY transition_count DESC, completed_count DESC
               LIMIT ?""",
            (user_id, from_video_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


async def get_all_transitions(user_id: int, limit: int = 100) -> list[dict]:
    """Get all transitions for a user."""
    with get_db() as db:
        rows = db.execute(
            """SELECT from_video_id, to_video_id, from_artist_id, to_artist_id,
                      transition_count, completed_count, skipped_count
               FROM song_transitions WHERE user_id = ?
               ORDER BY transition_count DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
