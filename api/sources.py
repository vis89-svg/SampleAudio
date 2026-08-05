"""Source filtering — ensure we only get official clean audio"""

SKIP_TITLE_WORDS = [
    "lyric", "live", "cover", "remix", "karaoke",
    "instrumental", "acoustic", "unplugged", "concert",
    "interview", "behind the scenes", "making of",
    "reaction", "parody", "mashup", " slowed", " spreed",
]


def is_official_source(video_info: dict) -> tuple[bool, str]:
    """Check if source is an official clean audio track.
    Returns (pass, reason)."""
    title = video_info.get("title", "").lower()
    artist = video_info.get("artist", "").lower()

    for word in SKIP_TITLE_WORDS:
        if word in title:
            return False, f"title contains '{word}'"

    if "topic" in artist:
        return True, "topic channel"

    return True, "pass"


def matches_expected_duration(downloaded_seconds: int, expected_seconds: int,
                               tolerance: float = 0.3) -> bool:
    """Check if downloaded duration matches expected song length."""
    if expected_seconds <= 0:
        return True
    diff = abs(downloaded_seconds - expected_seconds) / expected_seconds
    return diff <= tolerance
