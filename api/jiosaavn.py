"""JioSaavn API client — fallback clean-audio source."""
import json
import threading
import urllib.parse
import urllib.request

from config import JIOSAAVN_ENABLED, JIOSAAVN_SEARCH_LIMIT

API_URL = "https://www.jiosaavn.com/api.php"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

_cache: dict[str, list[dict]] = {}
_cache_lock = threading.Lock()


def _call(params: dict) -> dict:
    url = API_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def search_songs(query: str, limit: int | None = None) -> list[dict]:
    """Search songs on JioSaavn. Returns normalized song dicts."""
    if not JIOSAAVN_ENABLED:
        return []
    limit = limit or JIOSAAVN_SEARCH_LIMIT
    key = f"{query}|{limit}"
    with _cache_lock:
        if key in _cache:
            return _cache[key]

    params = {
        "__call": "search.getResults",
        "api_version": "4",
        "_format": "json",
        "_marker": "0",
        "ctx": "web6dot0",
        "q": query,
        "n": str(limit),
    }

    try:
        data = _call(params)
    except Exception:
        return []

    results = data.get("results", []) if isinstance(data, dict) else []
    songs = []
    for r in results:
        if r.get("type") != "song":
            continue
        more = r.get("more_info", {}) or {}
        artist_map = more.get("artistMap", {}) or {}
        artists = [a.get("name", "") for a in artist_map.get("primary_artists", [])
                   if a.get("name")]
        try:
            duration = int(more.get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0
        songs.append({
            "id": r.get("id", ""),
            "title": r.get("title", ""),
            "artist": ", ".join(artists),
            "artists": artists,
            "album": more.get("album") or r.get("album", ""),
            "duration_seconds": duration,
            "url": r.get("perma_url", ""),
            "thumbnail": r.get("image", ""),
            "bitrate_320": more.get("320kbps") == "true",
        })

    with _cache_lock:
        _cache[key] = songs
    return songs
