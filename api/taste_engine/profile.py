"""Profile — short-term (7-day) and long-term (lifetime) taste profiles."""
import json
import logging
from datetime import datetime, timedelta
from api.database import get_db

logger = logging.getLogger(__name__)

SHORT_TERM_DAYS = 7
SHORT_TERM_DECAY = 0.7
LONG_TERM_DECAY = 0.95


def update_taste_profile(user_id: int, session_id: int):
    """Update taste profiles incrementally after a session completes."""
    with get_db() as db:
        existing = db.execute(
            "SELECT short_term_json, long_term_json FROM taste_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        short_term = json.loads(existing["short_term_json"]) if existing else {}
        long_term = json.loads(existing["long_term_json"]) if existing else {}

        session_data = db.execute(
            "SELECT fingerprint_json FROM listening_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()

        if not session_data or not session_data["fingerprint_json"]:
            return

        fp = json.loads(session_data["fingerprint_json"])

        short_term = _blend_profile(short_term, fp, SHORT_TERM_DECAY)
        long_term = _blend_profile(long_term, fp, LONG_TERM_DECAY)

        short_term = _compute_behavioral_metrics(user_id, short_term, SHORT_TERM_DAYS)
        long_term = _compute_behavioral_metrics(user_id, long_term, None)

        db.execute(
            """INSERT INTO taste_profiles (user_id, short_term_json, long_term_json, profile_version, updated_at)
               VALUES (?, ?, ?, 'v2.0', CURRENT_TIMESTAMP)
               ON CONFLICT(user_id) DO UPDATE SET
                   short_term_json = excluded.short_term_json,
                   long_term_json = excluded.long_term_json,
                   updated_at = CURRENT_TIMESTAMP""",
            (user_id, json.dumps(short_term), json.dumps(long_term)),
        )


def _blend_profile(profile: dict, fingerprint: dict, decay: float) -> dict:
    """Blend new session fingerprint into existing profile with decay factor."""
    result = {}

    artist_ids = fingerprint.get("artist_ids", [])
    for aid in artist_ids:
        old_score = profile.get("artist_ids", {}).get(aid, 0)
        result[aid] = round(old_score * decay + (1 - decay) * 10, 2)

    if "artist_ids" in profile:
        for aid, score in profile["artist_ids"].items():
            if aid not in result:
                result[aid] = round(score * decay, 2)

    blended = {"artist_ids": result}

    for key in ["completion_rate", "skip_rate", "avg_song_length"]:
        if key in fingerprint:
            old = profile.get(key, 0)
            blended[key] = round(old * decay + fingerprint[key] * (1 - decay), 2)

    return blended


def _compute_behavioral_metrics(user_id: int, profile: dict, days: int | None) -> dict:
    """Compute behavioral metrics from listening history."""
    with get_db() as db:
        query = """SELECT
                       COUNT(DISTINCT artist_id) as unique_artists,
                       COUNT(*) as total_plays,
                       AVG(duration_seconds) as avg_duration,
                       SUM(CASE WHEN video_id = LAG(video_id) OVER (ORDER BY played_at) THEN 1 ELSE 0 END) as repeat_count
                   FROM listening_history WHERE user_id = ?"""
        params: list = [user_id]

        if days:
            query += " AND played_at > datetime('now', ?)"
            params.append(f"-{days} days")

        row = db.execute(query, params).fetchone()

        if row and row["total_plays"]:
            profile["artist_diversity"] = round(
                (row["unique_artists"] / row["total_plays"]) if row["total_plays"] else 0, 2
            )
            profile["repeat_tolerance"] = round(
                1 - (row["repeat_count"] / row["total_plays"]) if row["total_plays"] else 0.5, 2
            )
            avg_dur = row["avg_duration"] or 0
            if avg_dur < 180:
                profile["preferred_song_length"] = {"short": 0.7, "medium": 0.25, "long": 0.05}
            elif avg_dur < 300:
                profile["preferred_song_length"] = {"short": 0.15, "medium": 0.7, "long": 0.15}
            else:
                profile["preferred_song_length"] = {"short": 0.05, "medium": 0.25, "long": 0.7}

    return profile


def get_taste_profile(user_id: int) -> dict | None:
    """Get user's taste profile."""
    with get_db() as db:
        row = db.execute(
            "SELECT short_term_json, long_term_json, profile_version, updated_at FROM taste_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        if not row:
            return None

        return {
            "short_term": json.loads(row["short_term_json"]),
            "long_term": json.loads(row["long_term_json"]),
            "version": row["profile_version"],
            "updated_at": row["updated_at"],
        }


def compute_profile_drift(user_id: int) -> float:
    """Compute cosine distance between short-term and long-term profiles."""
    profile = get_taste_profile(user_id)
    if not profile:
        return 0.0

    short_artists = set(profile["short_term"].get("artist_ids", {}).keys())
    long_artists = set(profile["long_term"].get("artist_ids", {}).keys())

    if not short_artists or not long_artists:
        return 0.0

    intersection = short_artists & long_artists
    union = short_artists | long_artists

    jaccard = len(intersection) / len(union) if union else 0
    return round(1 - jaccard, 2)
