"""SampleAudio Configuration"""
import os

# === Quality Settings ===
# "normal" = YouTube Music 128kbps (free, instant)
# "lossless" = Tidal/Qobuz FLAC via SpotiFLAC (download first)
QUALITY = os.getenv("QUALITY", "normal")

# === Storage ===
DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "downloads")
CACHE_ENABLED = True

# === Anti-Detection ===
SLEEP_BETWEEN_REQUESTS = 2
SLEEP_BETWEEN_DOWNLOADS = 5
MAX_DOWNLOAD_SPEED = 1048576  # 1 MB/s

# === Audio Processing ===
NORMALIZE_AUDIO = True
TARGET_LUFS = -16
TRUE_PEAK = -1.5
LOUDNESS_RANGE = 11

# === Progressive Streaming ===
STREAM_POLL_INTERVAL = 0.5  # seconds between file-growth checks
STREAM_WAIT_TIMEOUT = 45    # max seconds to wait for download to start

# === SponsorBlock Clean Audio ===
SPONSORBLOCK_ENABLED = True
SPONSORBLOCK_CATEGORIES = ["music_offtopic", "intro", "outro", "filler"]
SPONSORBLOCK_MIN_TOTAL_SKIP = 6.0  # only skip if at least this many seconds removed

# === JioSaavn Fallback Source ===
# When YouTube fails or has no SponsorBlock data, fall back to JioSaavn's
# official clean audio (free, up to 320kbps).
JIOSAAVN_ENABLED = True
JIOSAAVN_QUALITY = "320"  # "320" or "128"
JIOSAAVN_SEARCH_LIMIT = 5
JIOSAAVN_DURATION_TOLERANCE = 5  # seconds tolerance when matching durations
JIOSAAVN_PREFER_ON_NO_SB = True   # use JioSaavn when SponsorBlock has no data

# === Server ===
HOST = "0.0.0.0"
PORT = 8000
