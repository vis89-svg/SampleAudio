"""User profile routes — listening history, likes, followed artists/albums."""
from fastapi import APIRouter, Depends, HTTPException
from api.auth import get_current_user
from api.database import get_db
from api.models import (
    HistoryEntry, LikeEntry, FollowedArtist, FollowedAlbum, UserPreferences
)
from api.daily_mix import (
    generate_daily_mix, generate_suggestions,
    generate_discovery_mix, generate_because_you_liked,
    generate_album_suggestions, generate_new_artist_suggestions,
    get_top_artists, get_top_albums, get_recently_played, get_liked_songs
)
from api.events import publish_play_event, subscribe
from api.sessions import update_session, compute_fingerprint
from api.transitions import record_transition

router = APIRouter(prefix="/api/user", tags=["user"])


# === Listening History ===

@router.post("/history")
async def log_play(entry: HistoryEntry, user: dict = Depends(get_current_user)):
    """Log a song play to listening history and publish event."""
    with get_db() as db:
        db.execute(
            """INSERT INTO listening_history
               (user_id, video_id, title, artist, album, thumbnail, duration,
                duration_seconds, artist_id, album_id, duration_played, completed,
                skipped, skip_position, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user["user_id"], entry.video_id, entry.title, entry.artist,
             entry.album, entry.thumbnail, entry.duration, entry.duration_seconds,
             entry.artist_id, entry.album_id, entry.duration_played, entry.completed,
             entry.skipped, entry.skip_position, entry.source or "search"),
        )
    await publish_play_event(user["user_id"], entry.model_dump())
    return {"status": "ok"}


@router.get("/history")
def get_history(limit: int = 50, user: dict = Depends(get_current_user)):
    """Get listening history (most recent first) with full song data."""
    with get_db() as db:
        rows = db.execute(
            """SELECT video_id, title, artist, album, thumbnail, duration, duration_seconds, artist_id, album_id, played_at, duration_played, completed
               FROM listening_history WHERE user_id = ?
               ORDER BY played_at DESC LIMIT ?""",
            (user["user_id"], limit),
        ).fetchall()
        return {"history": [dict(r) for r in rows]}


# === Likes ===

@router.post("/like")
def like_song(entry: LikeEntry, user: dict = Depends(get_current_user)):
    """Like a song."""
    with get_db() as db:
        db.execute(
            """INSERT OR IGNORE INTO user_likes
               (user_id, video_id, title, artist, album, thumbnail, duration, duration_seconds, artist_id, album_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user["user_id"], entry.video_id, entry.title, entry.artist,
             entry.album, entry.thumbnail, entry.duration, entry.duration_seconds,
             entry.artist_id, entry.album_id),
        )
    return {"status": "ok"}


@router.delete("/like/{video_id}")
def unlike_song(video_id: str, user: dict = Depends(get_current_user)):
    """Unlike a song."""
    with get_db() as db:
        db.execute(
            "DELETE FROM user_likes WHERE user_id = ? AND video_id = ?",
            (user["user_id"], video_id),
        )
    return {"status": "ok"}


@router.get("/likes")
def get_likes(user: dict = Depends(get_current_user)):
    """Get all liked songs with full data."""
    with get_db() as db:
        rows = db.execute(
            """SELECT video_id, title, artist, album, thumbnail, duration, duration_seconds, artist_id, album_id, liked_at
               FROM user_likes WHERE user_id = ? ORDER BY liked_at DESC""",
            (user["user_id"],),
        ).fetchall()
        return {"likes": [dict(r) for r in rows]}


# === Followed Artists ===

@router.post("/follow-artist")
def follow_artist(entry: FollowedArtist, user: dict = Depends(get_current_user)):
    """Follow an artist."""
    with get_db() as db:
        db.execute(
            "INSERT OR IGNORE INTO followed_artists (user_id, artist_id, artist_name) VALUES (?, ?, ?)",
            (user["user_id"], entry.artist_id, entry.artist_name),
        )
    return {"status": "ok"}


@router.delete("/follow-artist/{artist_id}")
def unfollow_artist(artist_id: str, user: dict = Depends(get_current_user)):
    """Unfollow an artist."""
    with get_db() as db:
        db.execute(
            "DELETE FROM followed_artists WHERE user_id = ? AND artist_id = ?",
            (user["user_id"], artist_id),
        )
    return {"status": "ok"}


@router.get("/followed-artists")
def get_followed_artists(user: dict = Depends(get_current_user)):
    """Get all followed artists."""
    with get_db() as db:
        rows = db.execute(
            "SELECT artist_id, artist_name, followed_at FROM followed_artists WHERE user_id = ? ORDER BY followed_at DESC",
            (user["user_id"],),
        ).fetchall()
        return {"artists": [dict(r) for r in rows]}


# === Followed Albums ===

@router.post("/follow-album")
def follow_album(entry: FollowedAlbum, user: dict = Depends(get_current_user)):
    """Follow an album."""
    with get_db() as db:
        db.execute(
            "INSERT OR IGNORE INTO followed_albums (user_id, album_id, album_title, album_artist) VALUES (?, ?, ?, ?)",
            (user["user_id"], entry.album_id, entry.album_title, entry.album_artist),
        )
    return {"status": "ok"}


@router.delete("/follow-album/{album_id}")
def unfollow_album(album_id: str, user: dict = Depends(get_current_user)):
    """Unfollow an album."""
    with get_db() as db:
        db.execute(
            "DELETE FROM followed_albums WHERE user_id = ? AND album_id = ?",
            (user["user_id"], album_id),
        )
    return {"status": "ok"}


@router.get("/followed-albums")
def get_followed_albums(user: dict = Depends(get_current_user)):
    """Get all followed albums."""
    with get_db() as db:
        rows = db.execute(
            "SELECT album_id, album_title, album_artist, followed_at FROM followed_albums WHERE user_id = ? ORDER BY followed_at DESC",
            (user["user_id"],),
        ).fetchall()
        return {"albums": [dict(r) for r in rows]}


# === Preferences ===

@router.get("/preferences")
def get_preferences(user: dict = Depends(get_current_user)):
    """Get user preferences."""
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM user_preferences WHERE user_id = ?",
            (user["user_id"],),
        ).fetchone()
        if not row:
            return {"preferred_quality": "normal", "clean_audio": True, "daily_mix_count": 6, "theme": "dark"}
        return dict(row)


@router.put("/preferences")
def update_preferences(prefs: UserPreferences, user: dict = Depends(get_current_user)):
    """Update user preferences."""
    with get_db() as db:
        db.execute(
            """INSERT INTO user_preferences (user_id, preferred_quality, clean_audio, daily_mix_count, theme)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
               preferred_quality = excluded.preferred_quality,
               clean_audio = excluded.clean_audio,
               daily_mix_count = excluded.daily_mix_count,
               theme = excluded.theme""",
            (user["user_id"], prefs.preferred_quality, prefs.clean_audio,
             prefs.daily_mix_count, prefs.theme),
        )
    return {"status": "ok"}


# === Profile ===

@router.get("/profile")
def profile(user: dict = Depends(get_current_user)):
    """Get user profile with stats."""
    from api.auth import get_user_profile
    profile_data = get_user_profile(user["user_id"])

    with get_db() as db:
        stats = {}
        stats["history_count"] = db.execute(
            "SELECT COUNT(*) FROM listening_history WHERE user_id = ?",
            (user["user_id"],),
        ).fetchone()[0]
        stats["likes_count"] = db.execute(
            "SELECT COUNT(*) FROM user_likes WHERE user_id = ?",
            (user["user_id"],),
        ).fetchone()[0]
        stats["followed_artists_count"] = db.execute(
            "SELECT COUNT(*) FROM followed_artists WHERE user_id = ?",
            (user["user_id"],),
        ).fetchone()[0]
        stats["followed_albums_count"] = db.execute(
            "SELECT COUNT(*) FROM followed_albums WHERE user_id = ?",
            (user["user_id"],),
        ).fetchone()[0]

    profile_data["stats"] = stats
    return profile_data


# === Personalized Recommendations ===

@router.get("/daily-mix")
def daily_mix(user: dict = Depends(get_current_user)):
    """Generate Daily Mix playlists based on listening history."""
    mixes = generate_daily_mix(user["user_id"])
    return {"mixes": mixes}


@router.get("/mixes/discovery")
def discovery_mix(user: dict = Depends(get_current_user)):
    """Generate Discovery Mix with more adventurous tracks."""
    mix = generate_discovery_mix(user["user_id"])
    return {"mix": mix}


@router.get("/mixes/because-you-liked")
def because_you_liked(user: dict = Depends(get_current_user)):
    """Generate 'Because You Liked' suggestions."""
    suggestions = generate_because_you_liked(user["user_id"])
    return {"suggestions": suggestions}


@router.get("/mixes/albums")
def album_suggestions(user: dict = Depends(get_current_user)):
    """Suggest albums user has partially played."""
    albums = generate_album_suggestions(user["user_id"])
    return {"albums": albums}


@router.get("/mixes/new-artists")
def new_artist_suggestions(user: dict = Depends(get_current_user)):
    """Suggest new artists based on favorites."""
    artists = generate_new_artist_suggestions(user["user_id"])
    return {"artists": artists}


@router.get("/suggestions")
def suggestions(user: dict = Depends(get_current_user)):
    """Generate personalized suggestions based on liked songs and history."""
    return generate_suggestions(user["user_id"])


@router.get("/top-artists")
def top_artists(limit: int = 10, user: dict = Depends(get_current_user)):
    """Get top artists by play count from listening history."""
    artists = get_top_artists(user["user_id"], limit)
    return {"artists": artists}


@router.get("/top-albums")
def top_albums(limit: int = 10, user: dict = Depends(get_current_user)):
    """Get top albums by play count from listening history."""
    albums = get_top_albums(user["user_id"], limit)
    return {"albums": albums}


@router.get("/recently-played")
def recently_played(limit: int = 20, user: dict = Depends(get_current_user)):
    """Get recently played tracks with full song data."""
    tracks = get_recently_played(user["user_id"], limit)
    return {"tracks": tracks}


@router.get("/liked-songs")
def liked_songs(user: dict = Depends(get_current_user)):
    """Get liked songs with full data."""
    songs = get_liked_songs(user["user_id"])
    return {"songs": songs}


# === Recommendation v2 Routes ===

from api.sessions import get_recent_sessions
from api.transitions import get_all_transitions


@router.get("/sessions")
def api_sessions(user: dict = Depends(get_current_user)):
    """Get recent listening sessions."""
    sessions = get_recent_sessions(user["user_id"])
    return {"sessions": sessions}


@router.get("/transitions")
def api_transitions(user: dict = Depends(get_current_user)):
    """Get song transitions."""
    transitions = get_all_transitions(user["user_id"])
    return {"transitions": transitions}


# === Event Bus Initialization ===

from api.taste_engine.profile import update_taste_profile
from api.taste_engine.scoring import update_scores


def _handle_profile_update(user_id: int, play_data: dict):
    """Update taste profile after session completes."""
    with get_db() as db:
        last = db.execute(
            "SELECT session_id FROM listening_history WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        if last and last["session_id"]:
            update_taste_profile(user_id, last["session_id"])


def _init_event_bus():
    """Register event handlers for the play event pipeline."""
    subscribe(update_session)
    subscribe(record_transition)
    subscribe(update_scores)
    subscribe(_handle_profile_update)


_init_event_bus()
