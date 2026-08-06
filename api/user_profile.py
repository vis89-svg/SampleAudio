"""User profile routes — listening history, likes, followed artists/albums."""
from fastapi import APIRouter, Depends, HTTPException
from api.auth import get_current_user
from api.database import get_db
from api.models import (
    HistoryEntry, LikeEntry, FollowedArtist, FollowedAlbum, UserPreferences
)
from api.daily_mix import (
    generate_daily_mix, generate_suggestions,
    get_top_artists, get_top_albums, get_recently_played, get_liked_songs
)

router = APIRouter(prefix="/api/user", tags=["user"])


# === Listening History ===

@router.post("/history")
def log_play(entry: HistoryEntry, user: dict = Depends(get_current_user)):
    """Log a song play to listening history."""
    with get_db() as db:
        db.execute(
            """INSERT INTO listening_history
               (user_id, video_id, title, artist, album, thumbnail, duration, duration_seconds, artist_id, album_id, duration_played, completed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user["user_id"], entry.video_id, entry.title, entry.artist,
             entry.album, entry.thumbnail, entry.duration, entry.duration_seconds,
             entry.artist_id, entry.album_id, entry.duration_played, entry.completed),
        )
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
