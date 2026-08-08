"""Genre-based playlist sections — detect the user's top genres from listening
history, then surface official YouTube Music genre playlists for those genres.

Detection: YTM's "Moods & Genres" genre category pages list official playlists
whose subtitles name the artists in them. We build a genre -> artist-name map
from those pages (one browse request per genre, cached), then score each genre
by how many of the user's top artists appear in it.

Fallback: when the user has no usable history, return fixed mood playlists
(Workout, Sleep, Chill, Classical, Party, Mellow) so the section is never empty.
"""
import threading
import time

from api.search import _get_ytmusic
from api.database import get_db
from api.daily_mix import get_top_artists

GENRE_BROWSE_PARAMS = {
    "Rock": "ggMPOg1uXzJKTm5jUEZ5Uzlu",
    "Pop": "ggMPOg1uX1lLQkxHbHhWQUUy",
    "Hip-hop": "ggMPOg1uX0M2dmRieXNxTW1s",
    "R&B & soul": "ggMPOg1uX2JxQ2hxc2J5UFhR",
    "Jazz": "ggMPOg1uX3lPcDFRaE9wM1BS",
    "Classical": "ggMPOg1uX1N4VmduTmdUR3dm",
    "Country & Americana": "ggMPOg1uX1RXcFlyZEpRb1d3",
    "Dance & electronic": "ggMPOg1uX1NPTld3SDN3WGs4",
    "Metal": "ggMPOg1uXzdlSXhKZ0hMV1Z4",
    "Indie & alternative": "ggMPOg1uX21NWWpBbU01SDgy",
    "Latin": "ggMPOg1uX29wWTRjMHV1dWN5",
}

MOOD_PLAYLISTS = [
    {"key": "workout", "name": "Workout",
     "playlist_id": "VLRDCLAK5uy_n7AeQQ7AO_YuS1kymCjW_OgEkplisOXoA"},
    {"key": "sleep", "name": "Sleep",
     "playlist_id": "VLRDCLAK5uy_k2csipDOuQwX6-GGZd4ys5MM5bueEqkrE"},
    {"key": "chill", "name": "Chill",
     "playlist_id": "VLRDCLAK5uy_mYa86YJNGqE4Jl5jG7DZP9NKdflw0hQL0"},
    {"key": "classical", "name": "Classical",
     "playlist_id": "VLRDCLAK5uy_mv1P2oVguxLCIDXavV-jcDG1lQyukfSpo"},
    {"key": "party", "name": "Party",
     "playlist_id": "VLRDCLAK5uy_mkXiaMATud8GJQ3aX7f0nCeCqvehA9wTQ"},
    {"key": "mellow", "name": "Mellow",
     "playlist_id": "VLRDCLAK5uy_nDL8KeBrUagwyISwNmyEiSfYgz1gVCesg"},
]

BROWSE_CACHE_TTL = 12 * 3600  # genre category pages are stable
USER_CACHE_TTL = 6 * 3600     # re-detect genres a few times a day

_browse_cache: dict[str, tuple[float, list, set]] = {}
_browse_lock = threading.Lock()

_user_cache: dict[int, tuple[float, list[dict]]] = {}
_user_lock = threading.Lock()

_playlist_cache: dict[str, tuple[float, list[dict]]] = {}
_playlist_lock = threading.Lock()


def _get_genre_browse(genre: str):
    """Return (playlists, artist_names) for a genre category page."""
    with _browse_lock:
        cached = _browse_cache.get(genre)
        if cached and time.time() - cached[0] < BROWSE_CACHE_TTL:
            return cached[1], cached[2]

    params = GENRE_BROWSE_PARAMS[genre]
    yt = _get_ytmusic()
    resp = yt._send_request(
        "browse",
        {"browseId": "FEmusic_moods_and_genres_category", "params": params},
    )
    playlists = []
    artists = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "musicTwoRowItemRenderer":
                    title = "".join(r.get("text", "") for r in v.get("title", {}).get("runs") or [])
                    bid = v.get("navigationEndpoint", {}).get("browseEndpoint", {}).get("browseId", "")
                    if bid.startswith("VL") and not title.lower().startswith("presenting"):
                        playlists.append({"title": title, "browse_id": bid})
                    sub = "".join(r.get("text", "") for r in v.get("subtitle", {}).get("runs") or [])
                    for part in sub.split(","):
                        name = part.strip()
                        if name:
                            artists.add(name.lower())
                walk(v)
        elif isinstance(o, list):
            for item in o:
                walk(item)

    walk(resp)

    with _browse_lock:
        _browse_cache[genre] = (time.time(), playlists, artists)
    return playlists, artists


def detect_user_genres(user_id: int, limit: int = 3) -> list[str]:
    """Top genres for a user, scored by artist overlap with YTM genre pages."""
    top_artists = get_top_artists(user_id, limit=25)
    if not top_artists:
        return []

    scores = {}
    for genre in GENRE_BROWSE_PARAMS:
        try:
            _, artist_names = _get_genre_browse(genre)
        except Exception:
            continue
        score = 0
        for a in top_artists:
            name = (a.get("artist") or "").split(",")[0].strip().lower()
            if name and name in artist_names:
                score += a.get("play_count", 1)
        if score > 0:
            scores[genre] = score

    if not scores:
        return []
    return [g for g, _ in sorted(scores.items(), key=lambda x: -x[1])[:limit]]


def _pick_playlist(playlists: list, genre: str) -> str | None:
    """Prefer a general hits/essentials playlist over niche ones."""
    if not playlists:
        return None
    genre_lower = genre.lower()
    for p in playlists:
        t = p["title"].lower()
        if genre_lower in t or "hits" in t or "hotlist" in t or "essentials" in t:
            return p["browse_id"]
    return playlists[0]["browse_id"]


def _fetch_playlist_tracks(browse_id: str) -> list[dict]:
    with _playlist_lock:
        cached = _playlist_cache.get(browse_id)
        if cached and time.time() - cached[0] < BROWSE_CACHE_TTL:
            return cached[1]
    try:
        yt = _get_ytmusic()
        playlist = yt.get_playlist(browse_id, limit=100)
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
                "thumbnail": (max(t.get("thumbnails", []), key=lambda th: th.get("width", 0) * th.get("height", 0))
                              .get("url", "") if t.get("thumbnails") else ""),
                "url": f"https://music.youtube.com/watch?v={t.get('videoId', '')}",
            })
    except Exception:
        return []
    with _playlist_lock:
        _playlist_cache[browse_id] = (time.time(), tracks)
    return tracks


def get_user_genre_charts(user_id: int) -> dict:
    """Return {genres: [...], personalized: bool} for the home feed section."""
    with _user_lock:
        cached = _user_cache.get(user_id)
        if cached and time.time() - cached[0] < USER_CACHE_TTL:
            return cached[1]

    genres = detect_user_genres(user_id)
    result: dict = {"genres": [], "personalized": bool(genres)}

    if genres:
        for genre in genres:
            try:
                playlists, _ = _get_genre_browse(genre)
            except Exception:
                continue
            bid = _pick_playlist(playlists, genre)
            if not bid:
                continue
            tracks = _fetch_playlist_tracks(bid)
            if tracks:
                result["genres"].append({
                    "key": genre.lower().replace(" & ", "-").replace(" ", "-"),
                    "name": genre,
                    "tracks": tracks[:100],
                })
    else:
        for mood in MOOD_PLAYLISTS:
            tracks = _fetch_playlist_tracks(mood["playlist_id"])
            if tracks:
                result["genres"].append({
                    "key": mood["key"],
                    "name": mood["name"],
                    "tracks": tracks[:100],
                })

    with _user_lock:
        _user_cache[user_id] = (time.time(), result)
    return result
