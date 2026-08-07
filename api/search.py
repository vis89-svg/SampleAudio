"""YouTube Music search via ytmusicapi"""
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from ytmusicapi import YTMusic

_yt: Optional[YTMusic] = None

_song_details_cache: dict[str, dict] = {}
_song_details_lock = threading.Lock()


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


def get_artist(browse_id: str) -> dict:
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

    return {
        "id": browse_id,
        "name": artist.get("name", ""),
        "thumbnail": _thumb_url(artist.get("thumbnails", [])),
        "top_songs": top_songs,
        "albums": albums,
    }


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
    """Get YouTube Music autoplay/recommended tracks for a given videoId."""
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
