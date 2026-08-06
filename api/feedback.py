"""Feedback — track user reactions to recommendations."""
import logging
from api.database import get_db

logger = logging.getLogger(__name__)


async def record_recommendation_display(user_id: int, mix_type: str,
                                        mix_index: int, tracks: list[dict]):
    """Record that recommendations were shown to user."""
    with get_db() as db:
        for pos, track in enumerate(tracks):
            db.execute(
                """INSERT INTO recommendation_feedback
                   (user_id, mix_type, mix_index, video_id, position, engine_version)
                   VALUES (?, ?, ?, ?, ?, 'v2.0')""",
                (user_id, mix_type, mix_index, track.get("id", track.get("video_id", "")), pos),
            )


async def record_recommendation_interaction(user_id: int, mix_type: str,
                                            video_id: str, interaction: str):
    """Record user interaction with a recommended track.

    interaction: 'played', 'completed', 'liked', 'skipped'
    """
    with get_db() as db:
        db.execute(
            f"""UPDATE recommendation_feedback
                SET {interaction} = 1
                WHERE user_id = ? AND mix_type = ? AND video_id = ?
                ORDER BY shown_at DESC LIMIT 1""",
            (user_id, mix_type, video_id),
        )


async def get_feedback_stats(user_id: int, mix_type: str) -> dict:
    """Get feedback statistics for a mix type."""
    with get_db() as db:
        row = db.execute(
            """SELECT
                   COUNT(*) as total_shown,
                   SUM(played) as total_played,
                   SUM(completed) as total_completed,
                   SUM(liked) as total_liked,
                   SUM(skipped) as total_skipped
               FROM recommendation_feedback
               WHERE user_id = ? AND mix_type = ?""",
            (user_id, mix_type),
        ).fetchone()

        if not row:
            return {}

        return {
            "total_shown": row["total_shown"],
            "total_played": row["total_played"] or 0,
            "total_completed": row["total_completed"] or 0,
            "total_liked": row["total_liked"] or 0,
            "total_skipped": row["total_skipped"] or 0,
            "play_rate": round((row["total_played"] or 0) / row["total_shown"], 2) if row["total_shown"] else 0,
            "skip_rate": round((row["total_skipped"] or 0) / row["total_shown"], 2) if row["total_shown"] else 0,
        }
