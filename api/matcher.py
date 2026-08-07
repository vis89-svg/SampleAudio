"""Cross-source matching — match a YouTube Music song to a JioSaavn result."""
import difflib
import re

from config import JIOSAAVN_DURATION_TOLERANCE

# Raw-title flags that mark non-studio versions (live recordings contain
# crowd noise / between-song chatter). Checked against the RAW title because
# normalize_title() strips parentheticals.
VERSION_FLAG_RE = re.compile(
    r"\b(live|concert|tour|unplugged|cover|karaoke|remix|acoustic|reprise|"
    r"session|performance|instrumental|lyrical)\b",
    re.IGNORECASE,
)

VERSION_PENALTY = 0.5


def _version_flagged(title: str) -> bool:
    return bool(VERSION_FLAG_RE.search(title))


def normalize_title(title: str) -> str:
    """Lowercase, strip parentheticals/punctuation, collapse whitespace."""
    title = title.lower()
    title = re.sub(r"\([^)]*\)", " ", title)  # drop (Official Audio), (feat. X), etc.
    title = re.sub(r"\b(official|original|music video|video|lyrics?|audio)\b", " ", title)
    title = re.sub(r"[^a-z0-9&]+", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def _artist_tokens(artist: str) -> set[str]:
    parts = re.split(r"[,&;]|\bf+\.?\b|\bft\.?\b", artist.lower())
    tokens = set()
    for p in parts:
        p = re.sub(r"[^a-z0-9]+", " ", p).strip()
        if len(p) >= 2:
            tokens.add(p)
    return tokens


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def match_song(yt_song: dict, candidates: list[dict]) -> dict | None:
    """Match a YouTube song to a JioSaavn candidate.

    yt_song needs: title, artist, duration_seconds.
    Returns the best candidate dict (with id/url) or None.
    """
    yt_title = normalize_title(yt_song.get("title", ""))
    yt_artists = _artist_tokens(yt_song.get("artist", ""))
    yt_dur = int(yt_song.get("duration_seconds") or 0)

    best = None
    best_score = 0.0

    for cand in candidates:
        c_title = normalize_title(cand.get("title", ""))
        if not c_title:
            continue

        title_score = _ratio(yt_title, c_title)
        if title_score < 0.8:
            continue

        c_artists = _artist_tokens(cand.get("artist", ""))
        artist_overlap = bool(yt_artists & c_artists)
        if not artist_overlap and title_score < 0.93:
            continue

        c_dur = int(cand.get("duration_seconds") or 0)
        if yt_dur and c_dur and abs(yt_dur - c_dur) > JIOSAAVN_DURATION_TOLERANCE:
            continue

        # Without a known duration we must be strict: a cover/karaoke track
        # can share a normalized title with the original, so require a near
        # exact title AND the same artist. Otherwise the first same-named
        # result (often a live/cover version with chatter) wins by tie.
        if not yt_dur and (title_score < 0.95 or not artist_overlap):
            continue

        # Duration closeness breaks ties between otherwise-equal versions
        # (e.g. remaster vs original vs live) when all pass the tolerance.
        dur_bonus = 0.0
        if yt_dur and c_dur:
            gap = abs(yt_dur - c_dur)
            dur_bonus = 0.05 * max(0.0, 1.0 - gap / JIOSAAVN_DURATION_TOLERANCE)

        score = (title_score + (0.2 if artist_overlap else 0.0)
                 + dur_bonus - (VERSION_PENALTY if _version_flagged(cand.get("title", "")) else 0.0))
        if score > best_score:
            best = cand
            best_score = score

    return best