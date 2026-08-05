"""YouTube Music search via ytmusicapi"""
import time
from typing import Optional
from ytmusicapi import YTMusic

_yt: Optional[YTMusic] = None


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
    time.sleep(1)
    results = yt.search(query, filter="songs", limit=limit)
    songs = []
    for r in results:
        if r.get("resultType") != "song":
            continue
        artists = [a["name"] for a in r.get("artists", [])]
        album = r.get("album", {})
        songs.append({
            "id": r.get("videoId", ""),
            "title": r.get("title", ""),
            "artist": ", ".join(artists),
            "album": album.get("name", "") if album else "",
            "duration": r.get("duration", ""),
            "duration_seconds": r.get("duration_seconds", 0),
            "thumbnail": _thumb_url(r.get("thumbnails", [])),
            "url": f"https://music.youtube.com/watch?v={r.get('videoId', '')}",
            "isExplicit": r.get("isExplicit", False),
        })
    return songs


def search_artists(query: str, limit: int = 10) -> list[dict]:
    yt = _get_ytmusic()
    time.sleep(1)
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
    time.sleep(1)
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
    return {
        "songs": search_songs(query, limit),
        "artists": search_artists(query, limit),
        "albums": search_albums(query, limit),
    }


def get_artist(browse_id: str) -> dict:
    yt = _get_ytmusic()
    time.sleep(1)
    artist = yt.get_artist(browse_id)
    top_songs = []
    for s in artist.get("top", {}).get("results", []):
        if s.get("videoId"):
            artists_list = [a["name"] for a in s.get("artists", [])]
            top_songs.append({
                "id": s.get("videoId", ""),
                "title": s.get("title", ""),
                "artist": ", ".join(artists_list) if artists_list else artist.get("name", ""),
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
    """Get title/artist/duration for a single video (for cross-source matching)."""
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
    return {
        "id": video_id,
        "title": title,
        "artist": artist,
        "duration_seconds": duration_seconds,
    }


def get_album(browse_id: str) -> dict:
    yt = _get_ytmusic()
    time.sleep(1)
    album = yt.get_album(browse_id)
    tracks = []
    for t in album.get("tracks", []):
        artists_list = [a["name"] for a in t.get("artists", [])]
        tracks.append({
            "id": t.get("videoId", ""),
            "title": t.get("title", ""),
            "artist": ", ".join(artists_list),
            "duration": t.get("duration", ""),
            "duration_seconds": t.get("duration_seconds", 0),
            "number": t.get("trackNumber", 0),
            "thumbnail": _thumb_url(t.get("thumbnails", [])),
            "url": f"https://music.youtube.com/watch?v={t.get('videoId', '')}",
        })

    return {
        "id": browse_id,
        "title": album.get("title", ""),
        "artist": album.get("artist", ""),
        "year": album.get("year", ""),
        "thumbnail": _thumb_url(album.get("thumbnails", [])),
        "tracks": tracks,
    }
