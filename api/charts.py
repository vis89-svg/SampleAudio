"""Charts via official YouTube Music chart playlists."""
import threading
import time

from api.search import _get_ytmusic, _thumb_url

CHART_CACHE_TTL = 6 * 3600  # charts update roughly daily

HOT_HITS_PLAYLISTS = [
    {"key": "bollywood", "name": "Hot Hits Bollywood",
     "playlist_id": "VLRDCLAK5uy_lhIiKLMQM6_gokxx581SC-xQBSfJm9gqc"},
    {"key": "tamil", "name": "Hot Hits Tamil",
     "playlist_id": "VLRDCLAK5uy_nTbyVypdXPQd00z15bTWjZr7pG-26yyQ4"},
    {"key": "malayalam", "name": "Hot Hits Malayalam",
     "playlist_id": "VLRDCLAK5uy_lXm4Xn4GwyFVjP0xgJvoZ6cdeBJZUmgSw"},
    {"key": "english", "name": "Hot Hits English",
     "playlist_id": "VLRDCLAK5uy_nmS3YoxSwVVQk9lEQJ0UX4ZCjXsW_psU8"},
]

CHART_PLAYLISTS = [
    {"key": "top50_global", "name": "Top 50 - Global",
     "playlist_id": "VLPLQzQq5ElQ5kg"},
    {"key": "top50_india", "name": "Top 50 - India",
     "playlist_id": "VLPLBaSXcDCrwvWeD5S4oypFcagbg-CQZC9c"},
    {"key": "top_songs_global", "name": "Top Songs - Global",
     "playlist_id": "VLPL4fGSI1pDJn6puJdseH2Rt9sMvt9E2M4i"},
    {"key": "top_songs_india", "name": "Top Songs - India",
     "playlist_id": "VLPL4fGSI1pDJn4pTWyM3t61lOyZ6_4jcNOw"},
    {"key": "top100_billboard", "name": "Top 100 Billboard",
     "playlist_id": "VLPLdv33Q3_-41Eu4LYKUv6ZMyVOub99HSSg"},
]

_cache: dict[str, tuple[float, list[dict]]] = {}
_lock = threading.Lock()


def _fetch_playlist(playlist_id: str) -> list[dict]:
    yt = _get_ytmusic()
    playlist = yt.get_playlist(playlist_id, limit=100)
    tracks = []
    for t in playlist.get("tracks", []):
        if not t.get("videoId"):
            continue
        artists_list = t.get("artists", [])
        album = t.get("album", {}) or {}
        tracks.append({
            "id": t.get("videoId", ""),
            "title": t.get("title", ""),
            "artist": ", ".join(a.get("name", "") for a in artists_list) if artists_list else "",
            "artist_id": artists_list[0].get("id", "") if artists_list else "",
            "album": album.get("name", ""),
            "album_id": album.get("id", ""),
            "duration": t.get("duration", ""),
            "duration_seconds": t.get("duration_seconds", 0),
            "thumbnail": _thumb_url(t.get("thumbnails", [])),
            "url": f"https://music.youtube.com/watch?v={t.get('videoId', '')}",
        })
    return tracks


def _find_playlist_def(key: str) -> dict | None:
    return (next((c for c in CHART_PLAYLISTS if c["key"] == key), None)
            or next((c for c in HOT_HITS_PLAYLISTS if c["key"] == key), None))


def get_chart_tracks(key: str) -> list[dict]:
    with _lock:
        cached = _cache.get(key)
        if cached and time.time() - cached[0] < CHART_CACHE_TTL:
            return cached[1]
    chart_def = _find_playlist_def(key)
    if not chart_def:
        return []
    try:
        tracks = _fetch_playlist(chart_def["playlist_id"])
    except Exception:
        return []
    with _lock:
        _cache[key] = (time.time(), tracks)
    return tracks


def get_all_charts() -> list[dict]:
    charts = []
    for chart_def in CHART_PLAYLISTS:
        tracks = get_chart_tracks(chart_def["key"])
        if tracks:
            charts.append({
                "key": chart_def["key"],
                "name": chart_def["name"],
                "tracks": tracks,
            })
    return charts


def get_hot_hits() -> list[dict]:
    """Official YTM 'Hot Hits' equivalent playlists per region (auto-updating)."""
    result = []
    for hit_def in HOT_HITS_PLAYLISTS:
        tracks = get_chart_tracks(hit_def["key"])
        if tracks:
            result.append({
                "key": hit_def["key"],
                "name": hit_def["name"],
                "tracks": tracks[:100],
            })
    return result
