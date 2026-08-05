"""Audio downloader using yt-dlp and SpotiFLAC"""
import os
import threading
import yt_dlp
from config import DOWNLOAD_DIR, SLEEP_BETWEEN_DOWNLOADS, MAX_DOWNLOAD_SPEED

# video_id -> dict(thread, event, file_path, error)
active_downloads: dict[str, dict] = {}
_active_lock = threading.Lock()


def _get_ydl_opts(output_template: str = None) -> dict:
    return {
        "format": "ba[acodec^=opus]/ba[acodec^=mp4a]/ba",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "opus",
            "preferredquality": "0",
        }, {
            "key": "FFmpegMetadata",
            "add_metadata": True,
        }, {
            "key": "EmbedThumbnail",
        }],
        "writethumbnail": True,
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


def find_audio_file(video_id: str) -> str | None:
    """Find any audio file for this video (raw or normalized).
    Prefers the loudness-normalized version when available."""
    for ext in ["opus", "m4a", "mp3", "ogg", "wav", "webm"]:
        norm = os.path.join(DOWNLOAD_DIR, f"{video_id}_norm.{ext}")
        if os.path.exists(norm) and os.path.getsize(norm) > 0:
            return norm
    for ext in ["opus", "m4a", "mp3", "ogg", "wav", "webm"]:
        path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
        if os.path.exists(path) and os.path.getsize(path) > 0:
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
