"""Audio downloader using yt-dlp and SpotiFLAC"""
import glob
import json
import os
import threading
import yt_dlp
from config import DOWNLOAD_DIR, SLEEP_BETWEEN_DOWNLOADS, MAX_DOWNLOAD_SPEED

# Files smaller than this are almost certainly failed-download stubs
# (e.g. error pages), never real audio. Skip them and delete them.
MIN_AUDIO_SIZE = 50 * 1024


def _delete_stubs(pattern: str) -> None:
    for path in glob.glob(pattern):
        try:
            if os.path.getsize(path) < MIN_AUDIO_SIZE:
                os.remove(path)
        except OSError:
            pass

# video_id -> dict(thread, event, file_path, error)
active_downloads: dict[str, dict] = {}
_active_lock = threading.Lock()

# youtube video_id -> jiosaavn song id (persisted so cached saavn files are reused)
_saavn_map: dict[str, str] = {}
_saavn_map_lock = threading.Lock()
_saavn_map_path = os.path.join(DOWNLOAD_DIR, ".saavn_map.json")


def _load_saavn_map() -> None:
    global _saavn_map
    try:
        with open(_saavn_map_path, "r", encoding="utf-8") as f:
            _saavn_map = json.load(f)
    except Exception:
        _saavn_map = {}


def _save_saavn_map() -> None:
    try:
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        with open(_saavn_map_path, "w", encoding="utf-8") as f:
            json.dump(_saavn_map, f)
    except Exception:
        pass


def remember_saavn_id(video_id: str, saavn_id: str) -> None:
    with _saavn_map_lock:
        _saavn_map[video_id] = saavn_id
        _save_saavn_map()


def get_saavn_id(video_id: str) -> str | None:
    with _saavn_map_lock:
        return _saavn_map.get(video_id)


_load_saavn_map()


def _get_ydl_opts(output_template: str = None) -> dict:
    return {
        "format": "ba[acodec^=mp4a]/ba[acodec^=opus]/ba",
        "outtmpl": output_template or os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
        "ratelimit": MAX_DOWNLOAD_SPEED,
        "sleep_interval_requests": 2,
        "sleep_interval": 3,
        "max_sleep_interval": 7,
        "retries": 10,
        "extractor_retries": 3,
        "throttled_rate": 100000,
        "extractor_args": {
            "youtube": {
                "player_client": ["android_music"],
            }
        },
        "quiet": True,
        "no_warnings": True,
    }


def _get_stream_opts(output_template: str) -> dict:
    """Options for progressive streaming: raw download, direct write, no postprocessors."""
    return {
        "format": "ba[acodec^=opus]/ba[acodec^=mp4a]/ba",
        "outtmpl": output_template,
        "nopart": True,
        "ratelimit": MAX_DOWNLOAD_SPEED,
        "sleep_interval": 0,
        "sleep_interval_requests": 0,
        "retries": 10,
        "extractor_retries": 3,
        "throttled_rate": 100000,
        "extractor_args": {
            "youtube": {
                "player_client": ["android_music"],
            }
        },
        "quiet": True,
        "no_warnings": True,
    }


def download_audio(video_id: str) -> str:
    """Download audio from YouTube Music. Returns path to downloaded file."""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    url = f"https://music.youtube.com/watch?v={video_id}"
    output_path = os.path.join(DOWNLOAD_DIR, f"{video_id}")

    opts = _get_ydl_opts(output_path + ".%(ext)s")

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info is None:
            raise Exception("Failed to extract info")

    for ext in ["opus", "m4a", "mp3", "ogg", "wav"]:
        path = f"{output_path}.{ext}"
        if os.path.exists(path):
            return path

    raise Exception("Download completed but file not found")


def get_audio_path(video_id: str) -> str | None:
    """Check if audio is already cached. Returns path or None."""
    for ext in ["opus", "m4a", "mp3", "ogg", "wav"]:
        path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
        if os.path.exists(path):
            return path
    return None


def find_audio_file(video_id: str, quality: str = "normal") -> str | None:
    """Find any audio file for this video.

    When quality=="saavn": prefer raw saavn .m4a (320kbps AAC), skip _norm/_trim.
    When quality=="normal": prefer _norm > _trim > raw (normalized YouTube audio).
    Skips files still being written by an FFmpeg pass."""
    from api.audio import is_processing

    saavn_id = get_saavn_id(video_id)

    if quality == "saavn":
        if saavn_id:
            path = os.path.join(DOWNLOAD_DIR, f"{saavn_id}.m4a")
            if os.path.exists(path) and os.path.getsize(path) >= MIN_AUDIO_SIZE:
                if not is_processing(path):
                    return path
        for suffix in ["_trim", ""]:
            for ext in ["m4a", "opus", "mp3", "ogg", "wav", "webm"]:
                path = os.path.join(DOWNLOAD_DIR, f"{video_id}{suffix}.{ext}")
                if os.path.exists(path) and os.path.getsize(path) >= MIN_AUDIO_SIZE:
                    if not is_processing(path):
                        return path
        for ext in ["opus", "m4a", "mp3", "ogg", "wav", "webm"]:
            path = os.path.join(DOWNLOAD_DIR, f"{video_id}_norm.{ext}")
            if os.path.exists(path) and os.path.getsize(path) >= MIN_AUDIO_SIZE:
                if not is_processing(path):
                    return path
        return None

    # quality == "normal": only search YouTube video_id files.
    # Saavn files must NOT be returned here — they have different timelines
    # and would be trimmed with wrong SponsorBlock timestamps.
    for suffix in ["_norm", "_trim", ""]:
        for ext in ["opus", "m4a", "mp3", "ogg", "wav", "webm"]:
            path = os.path.join(DOWNLOAD_DIR, f"{video_id}{suffix}.{ext}")
            if os.path.exists(path) and os.path.getsize(path) >= MIN_AUDIO_SIZE:
                if not is_processing(path):
                    return path
    return None


def _run_stream_download(video_id: str, output_template: str,
                         completion_event: threading.Event) -> None:
    url = f"https://music.youtube.com/watch?v={video_id}"
    opts = _get_stream_opts(output_template)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    except Exception:
        pass
    finally:
        completion_event.set()
        _delete_stubs(os.path.join(DOWNLOAD_DIR, f"{video_id}.*"))


def start_streaming_download(video_id: str) -> dict:
    """Start a background download for progressive streaming.
    Returns dict with (event, file_path) or an existing in-progress download."""
    with _active_lock:
        existing = active_downloads.get(video_id)
        if existing and not existing["event"].is_set():
            return existing

        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        output_template = os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s")
        completion_event = threading.Event()

        entry = {
            "event": completion_event,
            "file_path": None,
            "error": None,
        }
        active_downloads[video_id] = entry

        thread = threading.Thread(
            target=_run_stream_download,
            args=(video_id, output_template, completion_event),
            daemon=True,
        )
        entry["thread"] = thread
        thread.start()
        return entry


def _run_saavn_download(saavn_url: str, song_id: str, quality: str,
                        completion_event: threading.Event) -> None:
    opts = {
        "format": quality,  # "128" or "320"
        "outtmpl": os.path.join(DOWNLOAD_DIR, f"{song_id}.%(ext)s"),
        "nopart": True,
        "retries": 5,
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([saavn_url])
    except Exception:
        pass
    finally:
        completion_event.set()
        _delete_stubs(os.path.join(DOWNLOAD_DIR, f"{song_id}.*"))


def start_saavn_streaming_download(video_id: str, saavn_url: str,
                                   song_id: str,
                                   quality: str = "320") -> dict:
    """Start a background JioSaavn download for progressive streaming.
    Dedup keyed on song_id so concurrent requests share one download."""
    key = f"saavn:{song_id}"
    with _active_lock:
        existing = active_downloads.get(key)
        if existing and not existing["event"].is_set():
            return existing

        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        completion_event = threading.Event()
        entry = {
            "event": completion_event,
            "file_path": os.path.join(DOWNLOAD_DIR, f"{song_id}.m4a"),
            "error": None,
        }
        active_downloads[key] = entry

        thread = threading.Thread(
            target=_run_saavn_download,
            args=(saavn_url, song_id, quality, completion_event),
            daemon=True,
        )
        entry["thread"] = thread
        thread.start()
        remember_saavn_id(video_id, song_id)
        return entry


def download_flac(spotify_url: str) -> str | None:
    """Download FLAC from Tidal via SpotiFLAC. Returns path or None."""
    try:
        from SpotiFLAC import SpotiFLAC
    except ImportError:
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    try:
        dl = SpotiFLAC(
            url=spotify_url,
            output_dir=DOWNLOAD_DIR,
            services=["tidal"],
            quality="LOSSLESS",
        )
        result = dl.download()
        if result and hasattr(result, "path"):
            return result.path
        for f in os.listdir(DOWNLOAD_DIR):
            if f.endswith(".flac"):
                return os.path.join(DOWNLOAD_DIR, f)
    except Exception:
        pass

    return None
