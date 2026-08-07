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
    """Get all user songs with effective scores and full metadata."""
    with get_db() as db:
        rows = db.execute(
            """SELECT
                   h.video_id,
                   h.title,
                   h.artist,
                   h.album,
                   h.thumbnail,
                   h.duration,
                   h.duration_seconds,
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
                "title": row["title"],
                "artist": row["artist"],
                "album": row["album"],
                "thumbnail": row["thumbnail"],
                "duration": row["duration"],
                "duration_seconds": row["duration_seconds"],
                "artist_id": row["artist_id"],
                "album_id": row["album_id"],
                "score": round(score, 2),
                "plays": row["plays"],
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored


async def update_scores(user_id: int, play_data: dict):
    """Incrementally update scores for the played song."""
    video_id = play_data.get("video_id")
    artist_id = play_data.get("artist_id")
    album_id = play_data.get("album_id")
    completed = play_data.get("completed", False)
    skipped = play_data.get("skipped", False)
    liked = False  # We don't know if liked in this event, would need separate tracking

    if not video_id or not artist_id:
        return

    with get_db() as db:
        # Get current play count and completion count for this song
        row = db.execute(
            """SELECT COUNT(*) as plays,
                      SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) as completed_count,
                      SUM(CASE WHEN skipped = 1 THEN 1 ELSE 0 END) as skipped_count
               FROM listening_history
               WHERE user_id = ? AND video_id = ?""",
            (user_id, video_id),
        ).fetchone()

        plays = row["plays"] if row else 0
        completed_count = row["completed_count"] if row else 0
        skipped_count = row["skipped_count"] if row else 0

        # Check if liked
        like_row = db.execute(
            "SELECT 1 FROM user_likes WHERE user_id = ? AND video_id = ?",
            (user_id, video_id),
        ).fetchone()
        liked = bool(like_row)

        # Check if artist followed
        followed = False
        if artist_id:
            follow_row = db.execute(
                "SELECT 1 FROM followed_artists WHERE user_id = ? AND artist_id = ?",
                (user_id, artist_id),
            ).fetchone()
            followed = bool(follow_row)

        # Get most recent play for recency
        recent_row = db.execute(
            "SELECT played_at FROM listening_history WHERE user_id = ? AND video_id = ? ORDER BY played_at DESC LIMIT 1",
            (user_id, video_id),
        ).fetchone()

        from datetime import datetime
        recency_days = 999
        if recent_row and recent_row["played_at"]:
            try:
                played_at = datetime.fromisoformat(recent_row["played_at"])
                recency_days = (datetime.utcnow() - played_at).days
            except Exception:
                pass

        score = compute_song_score(
            plays=plays,
            completed=completed_count,
            liked=liked,
            followed_artist=followed,
            recency_days=recency_days,
            skipped=skipped_count > 0,
        )

        # Store/update in a scored_songs cache table if we create one, or just rely on on-demand computation
        # For now, we just ensure the data is in listening_history for on-demand scoring
        # This function mainly serves to trigger any cache invalidation if we add caching later
        logger.debug(f"Updated score for {video_id}: {score:.2f} (plays={plays}, completed={completed_count})")
