"""YouTube Music search via ytmusicapi"""
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from ytmusicapi import YTMusic

_yt: Optional[YTMusic] = None

_song_details_cache: dict[str, dict] = {}
_song_details_lock = threading.Lock()

_recommendations_cache: dict[str, tuple[float, list[dict]]] = {}
_recommendations_lock = threading.Lock()
RECOMMENDATIONS_CACHE_TTL = 3600  # seconds

_artist_page_cache: dict[str, tuple[float, dict]] = {}
_artist_page_lock = threading.Lock()
ARTIST_PAGE_CACHE_TTL = 12 * 3600  # artist pages change rarely

_featuring_cache: dict[str, tuple[float, list[dict]]] = {}
_featuring_lock = threading.Lock()
FEATURING_CACHE_TTL = 6 * 3600

_radio_cache: dict[str, tuple[float, list[dict]]] = {}
_radio_lock = threading.Lock()
RADIO_CACHE_TTL = 6 * 3600

_playlist_cache: dict[str, tuple[float, dict]] = {}
_playlist_lock = threading.Lock()
PLAYLIST_CACHE_TTL = 12 * 3600

_artist_cache: dict[tuple[str, int | None], tuple[float, dict]] = {}
_artist_cache_lock = threading.Lock()
ARTIST_CACHE_TTL = 12 * 3600


def _get_ytmusic() -> YTMusic:
    global _yt
    if _yt is None:
        _yt = YTMusic()
    return _yt


def _thumb_url(thumbnails: list) -> str:
    if not thumbnails:
        return ""
    best = max(thumbnails, key=lambda t: t.get("width", 0) * t.get("height", 0))
    return best.get("url", "")


def search_songs(query: str, limit: int = 10) -> list[dict]:
    yt = _get_ytmusic()
    results = yt.search(query, filter="songs", limit=limit)
    songs = []
    for r in results:
        if r.get("resultType") != "song":
            continue
        artists = r.get("artists", [])
        album = r.get("album", {}) or {}
        songs.append({
            "id": r.get("videoId", ""),
            "title": r.get("title", ""),
            "artist": ", ".join(a.get("name", "") for a in artists),
            "artist_id": artists[0].get("id", "") if artists else "",
            "album": album.get("name", ""),
            "album_id": album.get("id", ""),
            "duration": r.get("duration", ""),
            "duration_seconds": r.get("duration_seconds", 0),
            "thumbnail": _thumb_url(r.get("thumbnails", [])),
            "url": f"https://music.youtube.com/watch?v={r.get('videoId', '')}",
            "isExplicit": r.get("isExplicit", False),
        })
    return songs


def search_artists(query: str, limit: int = 10) -> list[dict]:
    yt = _get_ytmusic()
    results = yt.search(query, filter="artists", limit=limit)
    artists = []
    for r in results:
        if r.get("resultType") != "artist":
            continue
        artists.append({
            "id": r.get("browseId", ""),
            "name": r.get("artist", r.get("title", "")),
            "thumbnail": _thumb_url(r.get("thumbnails", [])),
        })
    return artists


def search_albums(query: str, limit: int = 10) -> list[dict]:
    yt = _get_ytmusic()
    results = yt.search(query, filter="albums", limit=limit)
    albums = []
    for r in results:
        if r.get("resultType") != "album":
            continue
        albums.append({
            "id": r.get("browseId", ""),
            "title": r.get("title", ""),
            "artist": r.get("artist", ""),
            "year": r.get("year", ""),
            "type": r.get("type", ""),
            "thumbnail": _thumb_url(r.get("thumbnails", [])),
        })
    return albums


def search_all(query: str, limit: int = 10) -> dict:
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_songs = pool.submit(search_songs, query, limit)
        f_artists = pool.submit(search_artists, query, limit)
        f_albums = pool.submit(search_albums, query, limit)
        return {
            "songs": f_songs.result(),
            "artists": f_artists.result(),
            "albums": f_albums.result(),
        }


def _play_counts(user_id: int | None, video_ids: list[str]) -> dict[str, int]:
    """Per-user play counts from listening history for the given video ids."""
    if not user_id or not video_ids:
        return {}
    from api.database import get_db
    counts: dict[str, int] = {}
    ids = [v for v in video_ids if v]
    if not ids:
        return counts
    placeholders = ",".join("?" * len(ids))
    with get_db() as db:
        rows = db.execute(
            f"""SELECT video_id, COUNT(*) AS c FROM listening_history
                WHERE user_id = ? AND video_id IN ({placeholders})
                GROUP BY video_id""",
            (user_id, *ids),
        ).fetchall()
    for r in rows:
        counts[r["video_id"]] = r["c"]
    return counts


def _attach_play_counts(songs: list[dict], user_id: int | None) -> list[dict]:
    if not user_id:
        return songs
    counts = _play_counts(user_id, [s.get("id", "") for s in songs])
    for s in songs:
        s["play_count"] = counts.get(s.get("id", ""), 0)
    return songs


def _artist_page_sections(raw: dict) -> list[dict]:
    """Walk a raw browse response for musicCarouselShelfRenderer sections."""
    sections = []
    def rec(o):
        if isinstance(o, dict):
            if "musicCarouselShelfRenderer" in o:
                shelf = o["musicCarouselShelfRenderer"]
                header = shelf.get("header", {}).get("musicCarouselShelfBasicHeaderRenderer", {})
                title = ""
                tr = header.get("title", {})
                runs = tr.get("runs", []) if tr else []
                if runs:
                    title = "".join(r.get("text", "") for r in runs)
                sections.append({"title": title, "shelf": shelf})
            for v in o.values():
                rec(v)
        elif isinstance(o, list):
            for v in o:
                rec(v)
    rec(raw)
    return sections


def _two_row_item(item: dict) -> dict:
    r = item.get("musicTwoRowItemRenderer", {}) or {}
    title = r.get("title", {}).get("runs", [{}])[0].get("text", "")
    subtitle = "".join(x.get("text", "") for x in r.get("subtitle", {}).get("runs", []))
    nav = r.get("navigationEndpoint", {}) or {}
    browse_id = nav.get("browseEndpoint", {}).get("browseId", "")
    playlist_id = nav.get("watchPlaylistEndpoint", {}).get("playlistId", "")
    thumbs = (r.get("thumbnailRenderer", {})
              .get("musicThumbnailRenderer", {})
              .get("thumbnail", {})
              .get("thumbnails", []))
    return {
        "id": browse_id or playlist_id,
        "browse_id": browse_id,
        "playlist_id": playlist_id,
        "title": title,
        "subtitle": subtitle,
        "thumbnail": _thumb_url(thumbs),
    }


def get_artist_page(browse_id: str) -> dict:
    """Raw artist page sections: Featured on, Playlists by X, Fans might also like.

    The parsed get_artist response omits these, so we walk the raw browse.
    """
    with _artist_page_lock:
        cached = _artist_page_cache.get(browse_id)
        if cached and time.time() - cached[0] < ARTIST_PAGE_CACHE_TTL:
            return cached[1]

    yt = _get_ytmusic()
    try:
        raw = yt._send_request("browse", {"browseId": browse_id})
    except Exception:
        return {"featured": [], "by_artist": [], "fans_also_like": []}

    featured, by_artist, fans = [], [], []
    for sec in _artist_page_sections(raw):
        title = sec["title"]
        items = [_two_row_item(c) for c in sec["shelf"].get("contents", [])]
        items = [i for i in items if i["id"]]
        if not items:
            continue
        if title == "Featured on":
            featured = items
        elif title == "Playlists by":
            by_artist = items
        elif title.startswith("Playlists by"):
            by_artist = items
        elif title == "Fans might also like":
            fans = items

    result = {
        "featured": featured,
        "by_artist": by_artist,
        "fans_also_like": fans,
    }
    with _artist_page_lock:
        _artist_page_cache[browse_id] = (time.time(), result)
    return result


def get_artist_featuring(browse_id: str, limit: int = 40) -> list[dict]:
    """Songs where the artist appears but is not the primary artist.

    YTM exposes no dedicated "featuring" feed, so we search the artist name
    for songs and keep ones whose primary artist differs.
    """
    with _featuring_lock:
        cached = _featuring_cache.get(browse_id)
        if cached and time.time() - cached[0] < FEATURING_CACHE_TTL:
            return cached[1][:limit]

    artist = get_artist(browse_id)
    name = (artist.get("name") or "").strip().lower()
    results = []
    if name:
        try:
            raw = _get_ytmusic().search(name, filter="songs", limit=100)
        except Exception:
            raw = []
        for r in raw:
            if r.get("resultType") != "song" or not r.get("videoId"):
                continue
            artists_list = r.get("artists", []) or []
            names = [a.get("name", "").lower() for a in artists_list]
            primary = names[0] if names else ""
            if not primary or primary == name:
                continue
            if not any(name in n for n in names):
                continue
            album = r.get("album", {}) or {}
            results.append({
                "id": r.get("videoId", ""),
                "title": r.get("title", ""),
                "artist": ", ".join(a.get("name", "") for a in artists_list),
                "artist_id": artists_list[0].get("id", "") if artists_list else "",
                "album": album.get("name", ""),
                "album_id": album.get("id", ""),
                "duration": r.get("duration", ""),
                "duration_seconds": r.get("duration_seconds", 0),
                "thumbnail": _thumb_url(r.get("thumbnails", [])),
                "url": f"https://music.youtube.com/watch?v={r.get('videoId', '')}",
            })
    with _featuring_lock:
        _featuring_cache[browse_id] = (time.time(), results)
    return results[:limit]


def get_artist_radio(browse_id: str, limit: int = 50) -> list[dict]:
    """Artist radio via the page's radioId (an RD playlist)."""
    with _radio_lock:
        cached = _radio_cache.get(browse_id)
        if cached and time.time() - cached[0] < RADIO_CACHE_TTL:
            return cached[1][:limit]

    radio_id = get_artist(browse_id).get("radio_id", "")
    results = []
    if radio_id:
        try:
            watch = _get_ytmusic().get_watch_playlist(playlistId=radio_id, limit=limit)
        except Exception:
            watch = {}
        for t in watch.get("tracks", []):
            if not t.get("videoId"):
                continue
            artists_list = t.get("artists", [])
            album = t.get("album", {}) or {}
            results.append({
                "id": t.get("videoId", ""),
                "title": t.get("title", ""),
                "artist": ", ".join(a.get("name", "") for a in artists_list),
                "artist_id": artists_list[0].get("id", "") if artists_list else "",
                "album": album.get("name", ""),
                "album_id": album.get("id", ""),
                "duration": t.get("duration", ""),
                "duration_seconds": t.get("duration_seconds", 0),
                "thumbnail": _thumb_url(t.get("thumbnail", [])),
                "url": f"https://music.youtube.com/watch?v={t.get('videoId', '')}",
            })
    with _radio_lock:
        _radio_cache[browse_id] = (time.time(), results)
    return results[:limit]


def get_artist_shuffle(shuffle_id: str, limit: int = 100) -> list[dict]:
    """Shuffled artist song mix via the page's shuffleId (an RDAO watch playlist)."""
    with _radio_lock:
        cached = _radio_cache.get(("shuffle", shuffle_id))
        if cached and time.time() - cached[0] < RADIO_CACHE_TTL:
            return cached[1][:limit]

    results = []
    if shuffle_id:
        try:
            watch = _get_ytmusic().get_watch_playlist(playlistId=shuffle_id, limit=limit)
        except Exception:
            watch = {}
        for t in watch.get("tracks", []):
            if not t.get("videoId"):
                continue
            artists_list = t.get("artists", [])
            album = t.get("album", {}) or {}
            results.append({
                "id": t.get("videoId", ""),
                "title": t.get("title", ""),
                "artist": ", ".join(a.get("name", "") for a in artists_list),
                "artist_id": artists_list[0].get("id", "") if artists_list else "",
                "album": album.get("name", ""),
                "album_id": album.get("id", ""),
                "duration": t.get("duration", ""),
                "duration_seconds": t.get("duration_seconds", 0),
                "thumbnail": _thumb_url(t.get("thumbnail", [])),
                "url": f"https://music.youtube.com/watch?v={t.get('videoId', '')}",
            })
    with _radio_lock:
        _radio_cache[("shuffle", shuffle_id)] = (time.time(), results)
    return results[:limit]


def get_playlist(browse_id: str, limit: int = 500) -> dict:
    """Any playlist by browse id, cached."""
    with _playlist_lock:
        cached = _playlist_cache.get(browse_id)
        if cached and time.time() - cached[0] < PLAYLIST_CACHE_TTL:
            return cached[1]

    yt = _get_ytmusic()
    playlist = yt.get_playlist(browse_id, limit=limit)
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
    result = {
        "id": browse_id,
        "title": playlist.get("title", ""),
        "description": playlist.get("description", ""),
        "tracks": tracks,
    }
    with _playlist_lock:
        _playlist_cache[browse_id] = (time.time(), result)
    return result


def get_artist(browse_id: str, user_id: int | None = None) -> dict:
    cache_key = (browse_id, user_id)
    with _artist_cache_lock:
        cached = _artist_cache.get(cache_key)
        if cached and time.time() - cached[0] < ARTIST_CACHE_TTL:
            return cached[1]

    yt = _get_ytmusic()
    artist = yt.get_artist(browse_id)
    top_songs = []
    for s in artist.get("songs", {}).get("results", []):
        if s.get("videoId"):
            artists_list = s.get("artists", [])
            album = s.get("album", {}) or {}
            top_songs.append({
                "id": s.get("videoId", ""),
                "title": s.get("title", ""),
                "artist": ", ".join(a.get("name", "") for a in artists_list) if artists_list else artist.get("name", ""),
                "artist_id": artists_list[0].get("id", "") if artists_list else "",
                "album": album.get("name", ""),
                "album_id": album.get("id", ""),
                "duration": s.get("duration", ""),
                "duration_seconds": s.get("duration_seconds", 0),
                "thumbnail": _thumb_url(s.get("thumbnails", [])),
                "url": f"https://music.youtube.com/watch?v={s.get('videoId', '')}",
            })

    albums = []
    for a in artist.get("albums", {}).get("results", []):
        albums.append({
            "id": a.get("browseId", ""),
            "title": a.get("title", ""),
            "year": a.get("year", ""),
            "thumbnail": _thumb_url(a.get("thumbnails", [])),
        })

    singles = []
    for s in artist.get("singles", {}).get("results", []):
        singles.append({
            "id": s.get("browseId", ""),
            "title": s.get("title", ""),
            "year": s.get("year", ""),
            "type": s.get("type", ""),
            "thumbnail": _thumb_url(s.get("thumbnails", [])),
        })

    related_raw = artist.get("related", {}) or {}
    related = []
    if isinstance(related_raw, list):
        for r in related_raw:
            related.append({
                "id": r.get("browseId", ""),
                "name": r.get("title", ""),
                "subscribers": r.get("subscribers", ""),
                "thumbnail": "",
            })
    else:
        for r in related_raw.get("results", []) or []:
            related.append({
                "id": r.get("browseId", ""),
                "name": r.get("title", ""),
                "subscribers": r.get("subscribers", ""),
                "thumbnail": "",
            })

    fans = []
    try:
        page = get_artist_page(browse_id)
        fans = page.get("fans_also_like", []) or []
        fans_by_id = {f["id"]: f["thumbnail"] for f in fans}
        for r in related:
            if r["id"] in fans_by_id:
                r["thumbnail"] = fans_by_id[r["id"]]
    except Exception:
        pass

    result = {
        "id": browse_id,
        "name": artist.get("name", ""),
        "channel_id": artist.get("channelId", ""),
        "thumbnail": _thumb_url(artist.get("thumbnails", [])),
        "description": artist.get("description", "") or "",
        "subscribers": artist.get("subscribers", "") or "",
        "monthly_listeners": artist.get("monthlyListeners", "") or "",
        "radio_id": artist.get("radioId", "") or "",
        "shuffle_id": artist.get("shuffleId", "") or "",
        "top_songs": _attach_play_counts(top_songs, user_id),
        "albums": albums,
        "singles": singles,
        "songs_browse_id": artist.get("songs", {}).get("browseId", ""),
        "albums_params": artist.get("albums", {}).get("params", ""),
        "total_songs": artist.get("songs", {}).get("total", len(top_songs)),
        "total_albums": artist.get("albums", {}).get("total", len(albums)),
        "related": related,
    }
    with _artist_cache_lock:
        _artist_cache[cache_key] = (time.time(), result)
    return result


def get_artist_all_songs(browse_id: str, user_id: int | None = None) -> list[dict]:
    """Fetch ALL songs for an artist using the songs browseId as a playlist."""
    yt = _get_ytmusic()
    artist = yt.get_artist(browse_id)
    songs_browse_id = artist.get("songs", {}).get("browseId", "")
    if not songs_browse_id:
        return []

    playlist = yt.get_playlist(songs_browse_id, limit=500)
    songs = []
    for t in playlist.get("tracks", []):
        if not t.get("videoId"):
            continue
        artists_list = t.get("artists", [])
        album = t.get("album", {}) or {}
        songs.append({
            "id": t.get("videoId", ""),
            "title": t.get("title", ""),
            "artist": ", ".join(a.get("name", "") for a in artists_list) if artists_list else artist.get("name", ""),
            "artist_id": artists_list[0].get("id", "") if artists_list else "",
            "album": album.get("name", ""),
            "album_id": album.get("id", ""),
            "duration": t.get("duration", ""),
            "duration_seconds": t.get("duration_seconds", 0),
            "thumbnail": _thumb_url(t.get("thumbnails", [])),
            "url": f"https://music.youtube.com/watch?v={t.get('videoId', '')}",
        })
    return _attach_play_counts(songs, user_id)


def get_artist_all_albums(channel_id: str, params: str) -> list[dict]:
    """Fetch ALL releases for an artist (albums, singles, EPs) in YTM's order."""
    if not params or not channel_id:
        return []
    with _artist_page_lock:
        cached = _artist_page_cache.get(("albums", channel_id))
        if cached and time.time() - cached[0] < ARTIST_PAGE_CACHE_TTL:
            return cached[1]
    yt = _get_ytmusic()
    albums = []
    seen = set()

    def _parse_grid(grid: dict) -> str:
        """Parse musicTwoRowItemRenderer items from a grid; returns next continuation token or ''."""
        for item in grid.get("items", []):
            r = item.get("musicTwoRowItemRenderer") or {}
            title = ""
            truns = r.get("title", {}).get("runs") or []
            if truns:
                title = truns[0].get("text", "")
            bid = r.get("navigationEndpoint", {}).get("browseEndpoint", {}).get("browseId", "")
            if title and bid and bid not in seen:
                seen.add(bid)
                subtitle = " ".join(x.get("text", "") for x in (r.get("subtitle", {}).get("runs") or []) if x.get("text", "").strip())
                year = ""
                typ = ""
                for part in (p.strip() for p in subtitle.split("\u2022")):
                    if part.isdigit() and len(part) == 4:
                        year = part
                    elif part:
                        typ = part
                albums.append({
                    "id": bid,
                    "title": title,
                    "year": year,
                    "type": typ,
                    "thumbnail": _thumb_url(r.get("thumbnailRenderer", {}).get("musicThumbnailRenderer", {}).get("thumbnail", {}).get("thumbnails", [])),
                })
        conts = grid.get("continuations") or []
        if conts:
            return conts[0].get("nextContinuationData", {}).get("continuation", "")
        return ""

    try:
        raw = yt._send_request(endpoint="browse", body={"browseId": "MPAD" + channel_id, "params": params})
        grid = raw["contents"]["singleColumnBrowseResultsRenderer"]["tabs"][0]["tabRenderer"]["content"]["sectionListRenderer"]["contents"][0]["gridRenderer"]
        token = _parse_grid(grid)
        for _ in range(20):
            if not token or len(albums) >= 400:
                break
            cont_resp = yt._send_request(endpoint="browse", body={"continuation": token})
            cc = cont_resp.get("continuationContents", {})
            g2 = cc.get("gridContinuation") or cc.get("musicGridContinuation")
            if not g2:
                break
            token = _parse_grid(g2)
    except Exception:
        pass
    with _artist_page_lock:
        _artist_page_cache[("albums", channel_id)] = (time.time(), albums)
    return albums


def get_song_details(video_id: str) -> dict:
    """Get title/artist/duration for a single video (for cross-source matching).

    Results are cached in-memory: calling this synchronously on the stream
    path used to take 60-90s per song (ytmusicapi.get_song is slow), which
    made the first play of any song hang for minutes.
    """
    with _song_details_lock:
        cached = _song_details_cache.get(video_id)
        if cached is not None:
            return cached
    try:
        r = _get_ytmusic().get_song(video_id)
    except Exception:
        return {}
    vd = r.get("videoDetails", {}) or {}
    title = vd.get("title", "")
    artist = vd.get("author", "")
    duration_seconds = 0
    try:
        duration_seconds = int(vd.get("lengthSeconds") or 0)
    except (TypeError, ValueError):
        pass
    if not title:
        return {}
    result = {
        "id": video_id,
        "title": title,
        "artist": artist,
        "duration_seconds": duration_seconds,
    }
    with _song_details_lock:
        _song_details_cache[video_id] = result
    return result


def get_recommendations(video_id: str, limit: int = 25) -> list[dict]:
    """Get YouTube Music autoplay/recommended tracks for a given videoId.

    Cached for an hour: the home feed requests recommendations for every liked
    seed (up to 6 x 50 tracks) on every load, and each hit is a slow
    ytmusicapi watch-playlist call.
    """
    cache_key = f"{video_id}:{limit}"
    with _recommendations_lock:
        cached = _recommendations_cache.get(cache_key)
        if cached and (time.time() - cached[0]) < RECOMMENDATIONS_CACHE_TTL:
            return cached[1]

    try:
        watch = _get_ytmusic().get_watch_playlist(videoId=video_id, limit=limit)
    except Exception:
        return []
    tracks = []
    for t in watch.get("tracks", []):
        artists = t.get("artists", [])
        album = t.get("album", {}) or {}
        thumb = _thumb_url(t.get("thumbnail", []))
        tracks.append({
            "id": t.get("videoId", ""),
            "title": t.get("title", ""),
            "artist": ", ".join(a.get("name", "") for a in artists),
            "artist_id": artists[0].get("id", "") if artists else "",
            "album": album.get("name", ""),
            "album_id": album.get("id", ""),
            "duration": t.get("duration", ""),
            "duration_seconds": t.get("duration_seconds", 0),
            "thumbnail": thumb,
            "url": f"https://music.youtube.com/watch?v={t.get('videoId', '')}",
            "isExplicit": t.get("isExplicit", False),
        })

    with _recommendations_lock:
        _recommendations_cache[cache_key] = (time.time(), tracks)
    return tracks


def get_album(browse_id: str) -> dict:
    yt = _get_ytmusic()
    album = yt.get_album(browse_id)
    album_thumb = _thumb_url(album.get("thumbnails", []))
    tracks = []
    for t in album.get("tracks", []):
        artists_list = t.get("artists", [])
        track_thumb = _thumb_url(t.get("thumbnails", []))
        tracks.append({
            "id": t.get("videoId", ""),
            "title": t.get("title", ""),
            "artist": ", ".join(a.get("name", "") for a in artists_list),
            "artist_id": artists_list[0].get("id", "") if artists_list else "",
            "album": album.get("title", ""),
            "album_id": browse_id,
            "duration": t.get("duration", ""),
            "duration_seconds": t.get("duration_seconds", 0),
            "number": t.get("trackNumber", 0),
            "thumbnail": track_thumb or album_thumb,
            "url": f"https://music.youtube.com/watch?v={t.get('videoId', '')}",
        })

    return {
        "id": browse_id,
        "title": album.get("title", ""),
        "artist": album.get("artist", ""),
        "year": album.get("year", ""),
        "thumbnail": album_thumb,
        "tracks": tracks,
    }
