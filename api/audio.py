"""Audio processing — loudness normalization via FFmpeg"""
import subprocess
import os
from config import NORMALIZE_AUDIO, TARGET_LUFS, TRUE_PEAK, LOUDNESS_RANGE


def normalize_audio(input_path: str) -> str:
    """Apply EBU R128 loudness normalization. Returns output path."""
    if not NORMALIZE_AUDIO:
        return input_path

    base, ext = os.path.splitext(input_path)
    output_path = f"{base}_norm{ext}"

    if os.path.exists(output_path):
        return output_path

    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-af", f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA={LOUDNESS_RANGE}",
        "-c:a", "libopus", "-b:a", "128k",
        output_path,
    ]

    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=60)
        return output_path
    except (subprocess.CalledProcessError, FileNotFoundError):
        return input_path


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
