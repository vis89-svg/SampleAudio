"""SampleAudio — FastAPI Backend"""
import os
import time
import threading
import mimetypes
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from api.search import search_songs, search_artists, search_albums, search_all
from api.search import get_artist, get_album, get_song_details
from api.downloader import (download_audio, get_audio_path, download_flac,
                            find_audio_file, start_streaming_download,
                            active_downloads, get_saavn_id,
                            start_saavn_streaming_download)
from api.audio import get_audio_duration, normalize_audio, trim_audio
from api.sponsorblock import get_skip_segments, total_skipped
from api.jiosaavn import search_songs as search_saavn_songs
from api.matcher import match_song
from config import (DOWNLOAD_DIR, HOST, PORT, STREAM_POLL_INTERVAL,
                    STREAM_WAIT_TIMEOUT, SPONSORBLOCK_MIN_TOTAL_SKIP,
                    JIOSAAVN_ENABLED, JIOSAAVN_QUALITY,
                    JIOSAAVN_PREFER_ON_NO_SB)

app = FastAPI(title="SampleAudio")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
def api_artist(browse_id: str):
    try:
        return get_artist(browse_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/album/{browse_id}")
def api_album(browse_id: str):
    try:
        return get_album(browse_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


MIME_MAP = {
    ".opus": "audio/ogg",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".webm": "audio/webm",
}


def iter_file_progressive(file_path: str, completion_event: threading.Event,
                          max_stall: int = 120):
    """Yield file chunks while the file is being written by a background download.

    Reads from the file as it grows. Returns once the completion event is set
    and EOF is reached. Gives up after `max_stall` empty polls (~60s) to avoid
    hanging forever if the download dies silently.
    """
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


def _normalize_when_done(raw_path: str, completion_event: threading.Event,
                         segments: list | None) -> None:
    def run():
        with _normalize_lock:
            if raw_path in _normalize_queued:
                return
            _normalize_queued.add(raw_path)
        completion_event.wait()
        _normalize_in_background(raw_path, segments)
    threading.Thread(target=run, daemon=True).start()


_normalize_queued: set[str] = set()
_normalize_lock = threading.Lock()


def _try_jiosaavn_stream(video_id: str):
    """Try to stream this song from JioSaavn (clean 320kbps fallback).

    Matches the YouTube video to a JioSaavn result by title/artist/duration,
    then starts a progressive saavn download. Returns (file_path, event) or None.
    """
    if not JIOSAAVN_ENABLED:
        return None

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

    deadline = time.time() + STREAM_WAIT_TIMEOUT
    while time.time() < deadline:
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            break
        if entry["event"].is_set():
            break
        time.sleep(STREAM_POLL_INTERVAL)
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return None
    return (file_path, entry["event"])


@app.get("/api/stream/{video_id}")
def api_stream(video_id: str, quality: str = Query("normal"),
               clean: bool = Query(True)):
    try:
        # If a download is still in progress for this video, reuse its event so
        # seek/reload requests continue streaming instead of treating a partial
        # file as complete.
        entry = active_downloads.get(video_id)
        active_event = entry["event"] if entry and not entry["event"].is_set() else None

        if active_event:
            file_path = find_audio_file(video_id) or entry["file_path"]
            event = active_event
        else:
            cached = find_audio_file(video_id)
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
                saavn = _try_jiosaavn_stream(video_id)
                if saavn:
                    file_path, event = saavn
                else:
                    segments = get_skip_segments(video_id) if clean else []
                    active = start_streaming_download(video_id)
                    event = active["event"]
                    deadline = time.time() + STREAM_WAIT_TIMEOUT
                    while time.time() < deadline:
                        file_path = find_audio_file(video_id)
                        if file_path or event.is_set():
                            break
                        time.sleep(STREAM_POLL_INTERVAL)
                    if not file_path:
                        raise HTTPException(status_code=500, detail="Download failed to start")
                    if event.is_set():
                        _normalize_in_background(file_path, segments)
                    else:
                        _normalize_when_done(file_path, event, segments)
            else:
                # Check SponsorBlock first: if this song has significant
                # non-music content, wait for the full download and serve the
                # trimmed clean version instead of streaming raw audio.
                segments = get_skip_segments(video_id) if clean else []
                needs_trim = total_skipped(segments) >= SPONSORBLOCK_MIN_TOTAL_SKIP

                if needs_trim:
                    active = start_streaming_download(video_id)
                    active["event"].wait(STREAM_WAIT_TIMEOUT)
                    raw_path = find_audio_file(video_id)
                    if not raw_path:
                        raise HTTPException(status_code=500, detail="Download failed to start")
                    file_path = trim_audio(raw_path, segments)
                    event = threading.Event()
                    event.set()
                    # Full trim + loudness normalization runs in background from
                    # the RAW file (segment timestamps reference raw timeline)
                    # so future plays serve the fully processed _norm file.
                    _normalize_in_background(raw_path, segments)
                else:
                    # No SponsorBlock data: prefer JioSaavn's clean 320kbps
                    # source over raw YouTube audio (which may contain chatter).
                    # Saavn files are already clean + mastered, so no trim or
                    # loudness re-encode is needed. (Re-encoding 320k AAC to
                    # 128k opus would only degrade quality.)
                    saavn = None
                    if clean and JIOSAAVN_PREFER_ON_NO_SB:
                        saavn = _try_jiosaavn_stream(video_id)
                    if saavn:
                        file_path, event = saavn
                    else:
                        active = start_streaming_download(video_id)
                        event = active["event"]

                        deadline = time.time() + STREAM_WAIT_TIMEOUT
                        while time.time() < deadline:
                            file_path = find_audio_file(video_id)
                            if file_path:
                                break
                            if event.is_set():
                                break
                            time.sleep(STREAM_POLL_INTERVAL)

                        if not file_path:
                            raise HTTPException(status_code=500, detail="Download failed to start")

                        if event.is_set():
                            _normalize_in_background(file_path, segments)
                        else:
                            _normalize_when_done(file_path, event, segments)

        ext = os.path.splitext(file_path)[1].lower()
        mime = MIME_MAP.get(ext) or mimetypes.guess_type(file_path)[0] or "audio/ogg"

        if event.is_set():
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


@app.get("/api/thumbnail/{video_id}")
def api_thumbnail(video_id: str):
    try:
        from ytmusicapi import YTMusic
        yt = YTMusic()
        result = yt.get_song(video_id)
        thumbnails = result.get("videoDetails", {}).get("thumbnail", {}).get("thumbnails", [])
        if not thumbnails:
            raise HTTPException(status_code=404, detail="No thumbnail")
        best = max(thumbnails, key=lambda t: t.get("width", 0) * t.get("height", 0))
        url = best.get("url", "")

        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
        return StreamingResponse(iter([data]), media_type="image/jpeg")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
