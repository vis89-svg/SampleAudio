"""Audio processing — segment trimming and loudness normalization via FFmpeg"""
import subprocess
import os
import threading
from config import NORMALIZE_AUDIO, TARGET_LUFS, TRUE_PEAK, LOUDNESS_RANGE

OPUS_COMPRESSION_LEVEL = "5"  # lower = faster encode, default 10 is very slow

# Output paths currently being written by an in-progress FFmpeg pass.
_in_progress: set[str] = set()
_in_progress_lock = threading.Lock()


def is_processing(path: str) -> bool:
    """True if the given output path is currently being written."""
    with _in_progress_lock:
        return path in _in_progress


def _mark_processing(path: str) -> bool:
    with _in_progress_lock:
        if path in _in_progress:
            return False
        _in_progress.add(path)
        return True


def _unmark_processing(path: str) -> None:
    with _in_progress_lock:
        _in_progress.discard(path)


def _aselect_expression(skip_segments: list) -> str:
    """Build an aselect expression keeping everything EXCEPT skip segments."""
    expr_parts = []
    cursor = 0.0
    for seg in sorted(skip_segments, key=lambda s: s["start"]):
        start, end = float(seg["start"]), float(seg["end"])
        if start > cursor:
            expr_parts.append(f"between(t,{cursor},{start})")
        cursor = max(cursor, end)
    expr_parts.append(f"between(t,{cursor},86400)")
    return "+".join(expr_parts)


def trim_audio(input_path: str, segments: list) -> str:
    """Remove skip segments only (fast, no loudness normalization).
    Returns output path. Falls back to input path on failure."""
    if not segments:
        return input_path

    base, ext = os.path.splitext(input_path)
    output_path = f"{base}_trim{ext}"

    if os.path.exists(output_path):
        return output_path

    if not _mark_processing(output_path):
        return input_path

    expr = _aselect_expression(segments)
    af = f"aselect='{expr}',asetpts=N/SR/TB"

    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-af", af,
        "-c:a", "libopus", "-b:a", "128k",
        "-compression_level", OPUS_COMPRESSION_LEVEL,
        output_path,
    ]

    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=120)
        return output_path
    except (subprocess.CalledProcessError, FileNotFoundError):
        return input_path
    finally:
        _unmark_processing(output_path)


def normalize_audio(input_path: str, skip_segments: list | None = None) -> str:
    """Apply EBU R128 loudness normalization, optionally trimming non-music
    segments first. Returns output path."""
    if not NORMALIZE_AUDIO:
        return input_path

    base, ext = os.path.splitext(input_path)
    output_path = f"{base}_norm{ext}"

    if os.path.exists(output_path):
        return output_path

    if not _mark_processing(output_path):
        return input_path

    af_parts = []
    if skip_segments:
        expr = _aselect_expression(skip_segments)
        af_parts.append(f"aselect='{expr}',asetpts=N/SR/TB")

    af_parts.append(f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA={LOUDNESS_RANGE}")

    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-af", ",".join(af_parts),
        "-c:a", "libopus", "-b:a", "128k",
        "-compression_level", OPUS_COMPRESSION_LEVEL,
        output_path,
    ]

    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=180)
        return output_path
    except (subprocess.CalledProcessError, FileNotFoundError):
        return input_path
    finally:
        _unmark_processing(output_path)


def get_audio_duration(file_path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", file_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        import json
        data = json.loads(result.stdout)
        return float(data.get("format", {}).get("duration", 0))
    except Exception:
        return 0
