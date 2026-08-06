"""Daily Mix generation — clusters listening history into personalized playlists."""
import random
from collections import Counter
from api.search import get_recommendations, get_artist, get_album
from api.database import get_db


def get_top_artists(user_id: int, limit: int = 20) -> list[dict]:
    """Get most played artists from listening history."""
    with get_db() as db:
        rows = db.execute(
            """SELECT artist, artist_id, COUNT(*) as play_count
               FROM listening_history
               WHERE user_id = ? AND artist IS NOT NULL AND artist != ''
               GROUP BY artist
               ORDER BY play_count DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
        return [{"artist": r["artist"], "artist_id": r["artist_id"], "play_count": r["play_count"]} for r in rows]


def get_top_albums(user_id: int, limit: int = 10) -> list[dict]:
    """Get most played albums from listening history."""
    with get_db() as db:
        rows = db.execute(
            """SELECT album, album_id, artist, COUNT(*) as play_count
               FROM listening_history
               WHERE user_id = ? AND album IS NOT NULL AND album != ''
               GROUP BY album
               ORDER BY play_count DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
        return [{"album": r["album"], "album_id": r["album_id"], "artist": r["artist"], "play_count": r["play_count"]} for r in rows]


def get_recently_played(user_id: int, limit: int = 20) -> list[dict]:
    """Get recently played tracks with full data."""
    with get_db() as db:
        rows = db.execute(
            """SELECT video_id, title, artist, album, thumbnail, duration, duration_seconds, artist_id, album_id
               FROM listening_history
               WHERE user_id = ?
               ORDER BY played_at DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def get_liked_songs(user_id: int) -> list[dict]:
    """Get liked songs with full data."""
    with get_db() as db:
        rows = db.execute(
            """SELECT video_id, title, artist, album, thumbnail, duration, duration_seconds, artist_id, album_id
               FROM user_likes
               WHERE user_id = ?
               ORDER BY liked_at DESC""",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def cluster_artists(top_artists: list[dict], num_clusters: int = 3) -> list[list[dict]]:
    """Simple clustering: split top artists into groups by play count tiers."""
    if not top_artists:
        return []

    clusters = [[] for _ in range(num_clusters)]
    for i, artist in enumerate(top_artists):
        cluster_idx = i % num_clusters
        clusters[cluster_idx].append(artist)

    return [c for c in clusters if c]


def generate_daily_mix(user_id: int, num_mixes: int = 3) -> list[dict]:
    """Generate Daily Mix playlists based on listening history.

    Returns a list of mix dicts:
    [
        {
            "name": "Daily Mix 01",
            "based_on": ["Artist1", "Artist2"],
            "tracks": [...]
        },
        ...
    ]
    """
    top_artists = get_top_artists(user_id, limit=15)
    if not top_artists:
        return []

    clusters = cluster_artists(top_artists, num_mixes)
    mixes = []

    for i, cluster in enumerate(clusters):
        mix_name = f"Daily Mix {i + 1}"
        based_on = [a["artist"] for a in cluster[:3]]
        tracks = []

        for artist in cluster[:3]:
            if artist.get("artist_id"):
                try:
                    artist_data = get_artist(artist["artist_id"])
                    top_songs = artist_data.get("top_songs", [])[:8]
                    for s in top_songs:
                        tracks.append({
                            "id": s.get("videoId", ""),
                            "title": s.get("title", ""),
                            "artist": s.get("artist", artist["artist"]),
                            "artist_id": s.get("artist_id", ""),
                            "album": s.get("album", ""),
                            "album_id": s.get("album_id", ""),
                            "duration": s.get("duration", ""),
                            "duration_seconds": s.get("duration_seconds", 0),
                            "thumbnail": s.get("thumbnail", ""),
                            "url": f"https://music.youtube.com/watch?v={s.get('videoId', '')}",
                        })
                except Exception:
                    pass
            if len(tracks) >= 20:
                break

        if tracks:
            tracks = tracks[:25]
            mixes.append({
                "name": mix_name,
                "based_on": based_on,
                "tracks": tracks,
            })

    return mixes


def generate_suggestions(user_id: int) -> dict:
    """Generate personalized suggestions based on liked songs and listening history."""
    liked = get_liked_songs(user_id)
    top_artists = get_top_artists(user_id, limit=5)
    top_albums = get_top_albums(user_id, limit=5)

    suggestions = {
        "based_on_likes": [],
        "top_artists": top_artists,
        "top_albums": top_albums,
    }

    if liked:
        seed = random.choice(liked)
        try:
            recs = get_recommendations(seed["video_id"], limit=10)
            for t in recs:
                suggestions["based_on_likes"].append({
                    "id": t.get("id", ""),
                    "title": t.get("title", ""),
                    "artist": t.get("artist", ""),
                    "artist_id": t.get("artist_id", ""),
                    "album": t.get("album", ""),
                    "album_id": t.get("album_id", ""),
                    "duration": t.get("duration", ""),
                    "duration_seconds": t.get("duration_seconds", 0),
                    "thumbnail": t.get("thumbnail", ""),
                    "url": t.get("url", ""),
                })
        except Exception:
            pass

    return suggestions
