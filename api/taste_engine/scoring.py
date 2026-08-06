"""Scoring — effective song score computation."""
import logging
from datetime import datetime, timedelta
from api.database import get_db

logger = logging.getLogger(__name__)


def compute_song_score(plays: int, completed: int, liked: bool,
                       followed_artist: bool, recency_days: int,
                       skipped: bool) -> float:
    """Compute effective song score from behavioral signals."""
    score = (
        plays
        + completed * 1.5
        + (3.0 if liked else 0.0)
        + (2.0 if followed_artist else 0.0)
        + _recency_bonus(recency_days)
        - (2.0 if skipped else 0.0)
    )
    return max(score, 0.1)


def _recency_bonus(days_ago: int) -> float:
    """Higher bonus for more recent plays."""
    if days_ago <= 1:
        return 5.0
    if days_ago <= 7:
        return 3.0
    if days_ago <= 30:
        return 1.0
    return 0.0


def get_scored_songs(user_id: int) -> list[dict]:
    """Get all user songs with effective scores."""
    with get_db() as db:
        rows = db.execute(
            """SELECT
                   h.video_id,
                   h.artist_id,
                   h.album_id,
                   COUNT(*) as plays,
                   SUM(CASE WHEN h.completed = 1 THEN 1 ELSE 0 END) as completed,
                   MAX(CASE WHEN l.video_id IS NOT NULL THEN 1 ELSE 0 END) as liked,
                   MAX(CASE WHEN fa.artist_id IS NOT NULL THEN 1 ELSE 0 END) as followed_artist,
                   MAX(julianday('now') - julianday(h.played_at)) as recency_days,
                   SUM(CASE WHEN h.skipped = 1 THEN 1 ELSE 0 END) as skipped
               FROM listening_history h
               LEFT JOIN user_likes l ON h.video_id = l.video_id AND l.user_id = h.user_id
               LEFT JOIN followed_artists fa ON h.artist_id = fa.artist_id AND fa.user_id = h.user_id
               WHERE h.user_id = ?
               GROUP BY h.video_id, h.artist_id, h.album_id
               ORDER BY plays DESC""",
            (user_id,),
        ).fetchall()

        scored = []
        for row in rows:
            score = compute_song_score(
                plays=row["plays"],
                completed=row["completed"],
                liked=bool(row["liked"]),
                followed_artist=bool(row["followed_artist"]),
                recency_days=int(row["recency_days"] or 999),
                skipped=bool(row["skipped"]),
            )
            scored.append({
                "video_id": row["video_id"],
                "artist_id": row["artist_id"],
                "album_id": row["album_id"],
                "score": round(score, 2),
                "plays": row["plays"],
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored


async def update_scores(user_id: int, play_data: dict):
    """Placeholder for incremental score updates (computed on-demand for now)."""
    pass
