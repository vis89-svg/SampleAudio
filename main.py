"""SampleAudio — FastAPI Backend"""
import os
import time
import threading
import mimetypes
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from api.search import search_songs, search_artists, search_albums, search_all
from api.search import get_artist, get_album, get_song_details, get_recommendations
from api.search import get_artist_all_songs, get_artist_all_albums, get_artist_shuffle
from api.downloader import (download_audio, get_audio_path, download_flac,
                            find_audio_file, start_streaming_download,
                            active_downloads, get_saavn_id,
                            start_saavn_streaming_download, MIN_AUDIO_SIZE)
from api.audio import get_audio_duration, normalize_audio, trim_audio
from api.sponsorblock import get_skip_segments, total_skipped
from api.jiosaavn import search_songs as search_saavn_songs
from api.matcher import match_song
from api.auth import register_user, authenticate_user, create_token, get_user_profile, get_current_user, get_optional_user
from api.user_profile import router as user_router
from api.charts import get_all_charts, get_hot_hits
from api.discover import get_discover, get_discover_category
from api.search import (get_artist_page, get_artist_featuring, get_artist_radio,
                        get_playlist as get_playlist_tracks)
from api.database import init_db
from config import (DOWNLOAD_DIR, HOST, PORT, STREAM_POLL_INTERVAL,
                    STREAM_WAIT_TIMEOUT, SPONSORBLOCK_MIN_TOTAL_SKIP,
                    JIOSAAVN_ENABLED, JIOSAAVN_QUALITY,
                    JIOSAAVN_PREFER_ON_NO_SB,
                    JIOSAAVN_STREAM_START_TIMEOUT)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="SampleAudio", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class NoCacheMiddleware(BaseHTTPMiddleware):
    """Stop browsers from caching responses: API responses are no-store (GET
    caching made the Discover page show stale content) and static HTML/JS/CSS
    is no-cache so new frontend versions always ship."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        elif path.endswith((".html", ".js", ".css")):
            response.headers["Cache-Control"] = "no-cache"
        return response


app.add_middleware(NoCacheMiddleware)


@app.get("/api/search")
def api_search(q: str = Query(..., min_length=1), limit: int = Query(10, ge=1, le=50)):
    try:
        return search_all(q, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/search/songs")
def api_search_songs(q: str = Query(..., min_length=1), limit: int = Query(10, ge=1, le=50)):
    try:
        return {"songs": search_songs(q, limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/artist/{browse_id}")
def api_artist(browse_id: str, user: dict | None = Depends(get_optional_user)):
    try:
        return get_artist(browse_id, user["user_id"] if user else None)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/artist/{browse_id}/songs")
def api_artist_songs(browse_id: str, user: dict | None = Depends(get_optional_user)):
    try:
        songs = get_artist_all_songs(browse_id, user["user_id"] if user else None)
        return {"songs": songs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/artist/{browse_id}/albums")
def api_artist_albums(browse_id: str):
    try:
        artist = get_artist(browse_id)
        albums = get_artist_all_albums(browse_id, artist.get("albums_params", ""))
        return {"albums": albums, "total": len(albums)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/artist/{browse_id}/playlists")
def api_artist_playlists(browse_id: str):
    try:
        page = get_artist_page(browse_id)
        return {"featured": page.get("featured", []), "by_artist": page.get("by_artist", [])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/artist/{browse_id}/radio")
def api_artist_radio(browse_id: str):
    try:
        return {"tracks": get_artist_radio(browse_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/artist/{browse_id}/shuffle")
def api_artist_shuffle(browse_id: str):
    try:
        artist = get_artist(browse_id)
        tracks = get_artist_shuffle(artist.get("shuffle_id", ""))
        return {"tracks": tracks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/artist/{browse_id}/featuring")
def api_artist_featuring(browse_id: str):
    try:
        return {"tracks": get_artist_featuring(browse_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/playlist/{playlist_id}")
def api_playlist(playlist_id: str):
    try:
        return get_playlist_tracks(playlist_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/album/{browse_id}")
def api_album(browse_id: str):
    try:
        return get_album(browse_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/recommendations")
def api_recommendations(videoId: str = Query(..., min_length=1),
                         limit: int = Query(25, ge=1, le=50)):
    try:
        tracks = get_recommendations(videoId, limit)
        return {"tracks": tracks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/charts")
def api_charts():
    try:
        return {"charts": get_all_charts()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/hot-hits")
def api_hot_hits():
    try:
        return {"hits": get_hot_hits()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/discover")
def api_discover():
    try:
        return get_discover()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/discover/category/{key}")
def api_discover_category(key: str):
    try:
        return get_discover_category(key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Auth Routes ===

@app.post("/api/auth/register")
def api_register(request: dict):
    try:
        user = register_user(
            username=request.get("username", ""),
            password=request.get("password", ""),
            email=request.get("email"),
        )
        token = create_token(user["user_id"], user["username"])
        return {"access_token": token, "token_type": "bearer", "username": user["username"]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/login")
def api_login(request: dict):
    try:
        user = authenticate_user(
            username=request.get("username", ""),
            password=request.get("password", ""),
        )
        token = create_token(user["user_id"], user["username"])
        return {"access_token": token, "token_type": "bearer", "username": user["username"]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/auth/me")
def api_me(user: dict = Depends(get_current_user)):
    return get_user_profile(user["user_id"])


# === User Profile Routes ===

app.include_router(user_router)

MIME_MAP = {
    ".opus": "audio/ogg",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".webm": "audio/webm",
}


def iter_file_progressive(file_path: str | None, completion_event: threading.Event,
                          max_stall: int = 120, first_byte_timeout: int = 90):
    """Yield file chunks while the file is being written by a background download.

    If the file doesn't exist yet (download hasn't produced bytes), poll for up
    to `first_byte_timeout` seconds so the HTTP response starts immediately
    instead of blocking the request for minutes. Then read from the file as it
    grows. Returns once the completion event is set and EOF is reached. Gives
    up after `max_stall` empty polls (~60s) to avoid hanging forever if the
    download dies silently.
    """
    waited = 0
    while file_path is None or not os.path.exists(file_path):
        if completion_event.is_set():
            return
        waited += STREAM_POLL_INTERVAL
        if waited > first_byte_timeout:
            return
        time.sleep(STREAM_POLL_INTERVAL)

    stalled = 0
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if chunk:
                yield chunk
                stalled = 0
                continue

            if completion_event.is_set():
                return

            stalled += 1
            if stalled > max_stall:
                return
            time.sleep(STREAM_POLL_INTERVAL)


def _normalize_in_background(raw_path: str, segments: list | None = None) -> None:
    def run():
        try:
            normalize_audio(raw_path, segments)
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


def _normalize_when_done(video_id: str, completion_event: threading.Event,
                         segments: list | None) -> None:
    def run():
        completion_event.wait()
        raw_path = find_audio_file(video_id, "normal")
        if not raw_path:
            return
        with _normalize_lock:
            if raw_path in _normalize_queued:
                return
            _normalize_queued.add(raw_path)
        _normalize_in_background(raw_path, segments)
    threading.Thread(target=run, daemon=True).start()


_normalize_queued: set[str] = set()
_normalize_lock = threading.Lock()


def _hints_to_details(title: str | None, artist: str | None,
                      dur: int | None) -> dict | None:
    """Build a song-details dict from the frontend's query params, when given."""
    if not title or not artist:
        return None
    return {
        "title": title,
        "artist": artist,
        "duration_seconds": int(dur or 0),
    }


def _try_jiosaavn_stream(video_id: str,
                         details: dict | None = None,
                         fetch_details: bool = True):
    """Try to stream this song from JioSaavn (clean 320kbps fallback).

    Matches the YouTube video to a JioSaavn result by title/artist/duration,
    then starts a progressive saavn download. Returns (file_path, event) or None.

    `details` (from the frontend's title/artist/dur query params) avoids the
    slow ytmusicapi.get_song call that used to stall playback for minutes.
    Only fetched as a last resort when no hints are available.
    """
    if not JIOSAAVN_ENABLED:
        return None

    if not details and fetch_details:
        details = get_song_details(video_id)
    if not details:
        return None

    query = f"{details['title']} {details['artist']}".strip()
    if not query:
        return None

    if JIOSAAVN_QUALITY == "320":
        results = [r for r in search_saavn_songs(query) if r.get("bitrate_320")]
    else:
        results = search_saavn_songs(query)
    if not results:
        return None

    match = match_song(details, results)
    if not match:
        return None

    entry = start_saavn_streaming_download(
        video_id, match["url"], match["id"], JIOSAAVN_QUALITY)
    file_path = entry["file_path"]

    deadline = time.time() + JIOSAAVN_STREAM_START_TIMEOUT
    while time.time() < deadline:
        if os.path.exists(file_path) and os.path.getsize(file_path) >= MIN_AUDIO_SIZE:
            break
        if entry["event"].is_set():
            break
        time.sleep(STREAM_POLL_INTERVAL)
    if not os.path.exists(file_path) or os.path.getsize(file_path) < MIN_AUDIO_SIZE:
        return None
    return (file_path, entry["event"])


@app.get("/api/stream/{video_id}")
def api_stream(video_id: str, quality: str = Query("normal"),
               clean: bool = Query(True),
               title: str | None = Query(None),
               artist: str | None = Query(None),
               dur: int | None = Query(None)):
    try:
        details = _hints_to_details(title, artist, dur)

        # If a download is still in progress for this video, reuse its event so
        # seek/reload requests continue streaming instead of treating a partial
        # file as complete.
        entry = active_downloads.get(video_id)
        active_event = entry["event"] if entry and not entry["event"].is_set() else None

        if active_event:
            file_path = find_audio_file(video_id, quality) or entry["file_path"]
            event = active_event
        else:
            cached = find_audio_file(video_id, quality)
            if cached:
                # If this file is the target of an in-progress JioSaavn
                # download, reuse its event for progressive streaming instead
                # of serving a partial file as complete.
                saavn_id = get_saavn_id(video_id)
                saavn_entry = active_downloads.get(f"saavn:{saavn_id}") if saavn_id else None
                if saavn_entry and not saavn_entry["event"].is_set():
                    file_path = saavn_entry["file_path"]
                    event = saavn_entry["event"]
                else:
                    file_path = cached
                    event = threading.Event()
                    event.set()
            elif quality == "lossless":
                file_path = download_flac(f"https://open.spotify.com/track/{video_id}")
                if not file_path:
                    file_path = download_audio(video_id)
                event = threading.Event()
                event.set()
            elif quality == "saavn":
                # Explicit JioSaavn 320kbps: always clean, no chatter, no trim.
                # If JioSaavn has no match, silently fall back to YouTube audio.
                saavn = _try_jiosaavn_stream(video_id, details)
                if saavn:
                    file_path, event = saavn
                else:
                    segments = get_skip_segments(video_id) if clean else []
                    active = start_streaming_download(video_id)
                    event = active["event"]
                    file_path = None
                    _normalize_when_done(video_id, event, segments)
            else:
                # Normal quality. Prefer clean sources in order:
                # 1) JioSaavn 320kbps — already clean + mastered, no trim or
                #    re-encode needed, and no SponsorBlock lookup required
                #    (it also streams progressively, so first bytes arrive fast).
                # 2) YouTube audio — check SponsorBlock for significant
                #    non-music content; if present, wait for the full download
                #    and serve the trimmed clean version.
                saavn = None
                if clean and JIOSAAVN_PREFER_ON_NO_SB:
                    saavn = _try_jiosaavn_stream(video_id, details)
                if saavn:
                    file_path, event = saavn
                else:
                    segments = get_skip_segments(video_id) if clean else []
                    _needs_trim = total_skipped(segments) >= SPONSORBLOCK_MIN_TOTAL_SKIP

                    if _needs_trim:
                        active = start_streaming_download(video_id)
                        active["event"].wait(STREAM_WAIT_TIMEOUT)
                        raw_path = find_audio_file(video_id, "normal")
                        if not raw_path:
                            raise HTTPException(status_code=500, detail="Download failed to start")
                        # Safety: ensure we only trim YouTube files, never saavn files
                        # (saavn files have different timestamps and would be corrupted)
                        if not os.path.basename(raw_path).startswith(video_id):
                            raise HTTPException(status_code=500, detail="Audio source mismatch — refusing to trim")
                        file_path = trim_audio(raw_path, segments)
                        event = threading.Event()
                        event.set()
                        # Full trim + loudness normalization runs in background from
                        # the RAW file (segment timestamps reference raw timeline)
                        # so future plays serve the fully processed _norm file.
                        _normalize_in_background(raw_path, segments)
                    else:
                        active = start_streaming_download(video_id)
                        event = active["event"]
                        file_path = None
                        _normalize_when_done(video_id, event, segments)

        ext = ""
        # Unknown extension: the YouTube progressive stream (stream opts) prefers
        # opus, which lands in a .webm container. Serve as webm, which players
        # accept broadly.
        mime = "audio/webm"
        if file_path:
            ext = os.path.splitext(file_path)[1].lower()
            mime = MIME_MAP.get(ext) or mimetypes.guess_type(file_path)[0] or "audio/ogg"

        if event.is_set() and file_path and os.path.exists(file_path):
            headers = {
                "Content-Length": str(os.path.getsize(file_path)),
                "Accept-Ranges": "bytes",
            }
        else:
            headers = {"Accept-Ranges": "bytes"}

        return StreamingResponse(
            iter_file_progressive(file_path, event),
            media_type=mime,
            headers=headers,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sponsorblock/{video_id}/segments")
def api_sponsorblock(video_id: str):
    try:
        segments = get_skip_segments(video_id)
        return {
            "video_id": video_id,
            "segments": segments,
            "total_skipped": round(total_skipped(segments), 1),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _fetch_best_thumbnail(yt, media_id: str) -> list[dict]:
    # Try video ID first, then album or artist browse IDs.
    try:
        result = yt.get_song(media_id)
        thumbnails = result.get("videoDetails", {}).get("thumbnail", {}).get("thumbnails", [])
        if thumbnails:
            return thumbnails
    except Exception:
        pass

    try:
        album = yt.get_album(media_id)
        thumbnails = album.get("thumbnails", [])
        if thumbnails:
            return thumbnails
    except Exception:
        pass

    try:
        artist = yt.get_artist(media_id)
        thumbnails = artist.get("thumbnails", [])
        if thumbnails:
            return thumbnails
    except Exception:
        pass

    raise HTTPException(status_code=404, detail="No thumbnail")


@app.get("/api/thumbnail/{media_id}")
def api_thumbnail(media_id: str):
    import hashlib
    import urllib.request
    cache_dir = os.path.join(os.path.dirname(__file__), "cache", "thumbnails")
    os.makedirs(cache_dir, exist_ok=True)
    cache_key = hashlib.sha256(media_id.encode()).hexdigest()
    cache_path = os.path.join(cache_dir, f"{cache_key}.img")

    if os.path.exists(cache_path):
        from fastapi.responses import FileResponse
        return FileResponse(cache_path, media_type="image/jpeg")

    try:
        from api.search import _get_ytmusic
        yt = _get_ytmusic()
        thumbnails = _fetch_best_thumbnail(yt, media_id)
        best = max(thumbnails, key=lambda t: t.get("width", 0) * t.get("height", 0))
        url = best.get("url", "")

        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()

        with open(cache_path, "wb") as f:
            f.write(data)

        content_type = resp.headers.get_content_type() or "image/jpeg"
        return StreamingResponse(iter([data]), media_type=content_type)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
