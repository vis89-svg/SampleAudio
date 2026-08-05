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
SPONSORBLOCK_MIN_TOTAL_SKIP = 6.0  # only pre-trim if at least this many seconds removed

# === Server ===
HOST = "0.0.0.0"
PORT = 8000
