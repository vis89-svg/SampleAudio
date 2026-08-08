"""Discover page — moods, genres, regional & language, decades categories.

Sources: YTM's "Moods & Genres" category index (get_mood_categories) plus one
raw browse per category page (same walk used for genre detection). All general
(not personalized) content, cached for 12h.

Regional category pages get a pinned "Hot Hits" card when a matching
Hot Hits playlist exists (Bollywood / Tamil / Malayalam).
"""
import threading
import time

from api.search import _get_ytmusic, _thumb_url
from api.charts import HOT_HITS_PLAYLISTS

INDEX_CACHE_TTL = 12 * 3600
CATEGORY_CACHE_TTL = 12 * 3600

# YTM "Genres" entries that are actually languages/regional categories
REGIONAL_TITLES = {
    "Hindi", "Tamil", "Telugu", "Kannada", "Malayalam", "Marathi",
    "Punjabi", "Bengali", "Bhojpuri", "Gujarati", "Haryanvi",
}

GENRE_TITLES = {
    "African", "Arabic", "Carnatic classical", "Classical",
    "Country & Americana", "Dance & electronic", "Desi hip-hop",
    "Devotional", "Family", "Folk & acoustic", "Ghazal/sufi",
    "Hindustani classical", "Hip-hop", "Indian indie", "Indian pop",
    "Indie & alternative", "J-Pop", "Jazz", "K-Pop", "Latin", "Metal",
    "Monsoon", "Pop", "R&B & soul", "Reggae & caribbean", "Rock",
}

DECADES_TITLE = "Decades"

# key -> HOT_HITS_PLAYLISTS key for the pinned card on regional pages
_HOT_HITS_BY_REGION = {
    "hindi": "bollywood",
    "tamil": "tamil",
    "malayalam": "malayalam",
    "telugu": "telugu",
}

_index_cache: dict[str, tuple[float, dict]] = {}
_index_lock = threading.Lock()

_cat_cache: dict[str, tuple[float, dict]] = {}
_cat_lock = threading.Lock()


def _slug(title: str) -> str:
    return title.lower().replace("&", "").replace(" ", "-")


def _get_raw_categories() -> dict:
    """{section_name: [{"title", "params"}, ...]} straight from YTM, cached."""
    with _index_lock:
        cached = _index_cache.get("raw")
        if cached and time.time() - cached[0] < INDEX_CACHE_TTL:
            return cached[1]
    try:
        cats = _get_ytmusic().get_mood_categories()
    except Exception:
        cats = {}
    with _index_lock:
        _index_cache["raw"] = (time.time(), cats)
    return cats


def _get_index() -> dict:
    """{key: {"title": str, "params": str}} for every category."""
    result = {}
    for section, items in _get_raw_categories().items():
        for item in items:
            title = item.get("title", "").strip()
            params = item.get("params", "")
            if title and params:
                result[_slug(title)] = {"title": title, "params": params}
    return result


def get_discover() -> dict:
    """Sections for the Discover page: moods, genres, regional, decades."""
    index = _get_index()
    raw = _get_raw_categories()

    moods = []
    for item in raw.get("Moods & moments", []):
        title = item.get("title", "").strip()
        key = _slug(title)
        if key in index:
            moods.append({"key": key, "name": title})

    genres, regional, decades = [], [], []
    for key, info in index.items():
        title = info["title"]
        if key == _slug(DECADES_TITLE):
            decades.append({"key": key, "name": title})
        elif title in REGIONAL_TITLES:
            regional.append({"key": key, "name": title})
        elif title in GENRE_TITLES:
            genres.append({"key": key, "name": title})

    genres.sort(key=lambda x: x["name"])
    regional.sort(key=lambda x: x["name"])
    return {"moods": moods, "genres": genres,
            "regional": regional, "decades": decades}


def _walk_playlists(resp) -> list[dict]:
    """All VL-browse playlists in a category page, deduped by title."""
    out = []
    seen = set()

    def rec(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "musicTwoRowItemRenderer":
                    title = "".join(r.get("text", "")
                                    for r in v.get("title", {}).get("runs") or [])
                    nav = v.get("navigationEndpoint", {}).get("browseEndpoint", {}) or {}
                    bid = nav.get("browseId", "")
                    if bid.startswith("VL") and title and title not in seen:
                        seen.add(title)
                        thumbs = (v.get("thumbnailRenderer", {})
                                  .get("musicThumbnailRenderer", {})
                                  .get("thumbnail", {})
                                  .get("thumbnails", []))
                        out.append({
                            "id": bid,
                            "title": title,
                            "thumbnail": _thumb_url(thumbs),
                        })
                rec(v)
        elif isinstance(o, list):
            for v in o:
                rec(v)

    rec(resp)
    return out


def _walk_sections(resp) -> list[dict]:
    """Category page carousels grouped by shelf title."""
    sections = []
    current = None

    def rec(o):
        nonlocal current
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "musicCarouselShelfBasicHeaderRenderer":
                    current = "".join(r.get("text", "")
                                      for r in v.get("title", {}).get("runs") or [])
                elif k == "musicCarouselShelfRenderer":
                    items = _walk_playlists({k: v})
                    if items and current:
                        sections.append({"name": current, "playlists": items})
                    current = None
                rec(v)
        elif isinstance(o, list):
            for v in o:
                rec(v)

    rec(resp)

    # Anything not inside a named carousel (e.g. grid shelves) as "Songs"
    flat = _walk_playlists(resp)
    named = {p["id"] for s in sections for p in s["playlists"]}
    leftovers = [p for p in flat if p["id"] not in named]
    if leftovers:
        sections.append({"name": "Playlists", "playlists": leftovers})
    return sections


def get_discover_category(key: str) -> dict:
    """One category page: name + sections of playlists."""
    with _cat_lock:
        cached = _cat_cache.get(key)
        if cached and time.time() - cached[0] < CATEGORY_CACHE_TTL:
            return cached[1]

    index = _get_index()
    info = index.get(key)
    if not info:
        return {"key": key, "name": key, "sections": []}

    sections = []
    try:
        resp = _get_ytmusic()._send_request(
            "browse",
            {"browseId": "FEmusic_moods_and_genres_category",
             "params": info["params"]},
        )
        sections = _walk_sections(resp)
    except Exception:
        sections = []

    # Pin the matching Hot Hits playlist at the top of regional pages
    hh_key = _HOT_HITS_BY_REGION.get(key)
    if hh_key:
        hh = next((h for h in HOT_HITS_PLAYLISTS if h["key"] == hh_key), None)
        if hh:
            sections.insert(0, {
                "name": "Hot Hits",
                "playlists": [{
                    "id": hh["playlist_id"],
                    "title": hh["name"],
                    "thumbnail": "",
                    "hot": True,
                }],
            })

    result = {"key": key, "name": info["title"], "sections": sections}
    with _cat_lock:
        _cat_cache[key] = (time.time(), result)
    return result
