"""SponsorBlock API client — finds non-music segments in YouTube videos."""
import json
import threading
import urllib.parse
import urllib.request

from config import SPONSORBLOCK_ENABLED, SPONSORBLOCK_CATEGORIES

API_BASE = "https://sponsor.ajay.app/api/skipSegments"
_cache: dict[str, list[dict]] = {}
_cache_lock = threading.Lock()


def get_skip_segments(video_id: str) -> list[dict]:
    """Return non-music segments for a video, cached.
    Each segment: {category, start, end}."""
    if not SPONSORBLOCK_ENABLED:
        return []

    with _cache_lock:
        if video_id in _cache:
            return _cache[video_id]

    segments = _fetch(video_id)

    with _cache_lock:
        _cache[video_id] = segments
    return segments


def total_skipped(segments: list[dict]) -> float:
    """Total seconds removed across all segments."""
    return sum(s["end"] - s["start"] for s in segments)


def merged_segments(segments: list[dict]) -> list[dict]:
    """Sort by start and merge overlapping/adjacent segments."""
    if not segments:
        return []
    ordered = sorted(segments, key=lambda s: s["start"])
    merged = []
    for seg in ordered:
        if merged and seg["start"] <= merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], seg["end"])
        else:
            merged.append({"category": seg["category"], "start": seg["start"], "end": seg["end"]})
    return merged


def _fetch(video_id: str) -> list[dict]:
    cats = json.dumps(SPONSORBLOCK_CATEGORIES)
    url = f"{API_BASE}?videoID={video_id}&categories={urllib.parse.quote(cats)}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "SampleAudio/1.0",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []

    # Response is an array of segments; tolerate dict wrapper just in case
    raw = data if isinstance(data, list) else data.get("segments", [])

    segments = []
    for seg in raw:
        category = seg.get("category", "")
        if category not in SPONSORBLOCK_CATEGORIES:
            continue
        span = seg.get("segment") or [0, 0]
        start, end = float(span[0]), float(span[1])
        if end - start < 1.0:
            continue
        segments.append({"category": category, "start": start, "end": end})

    return merged_segments(segments)