"""Similarity — session and transition-based similarity computation."""
import json
import logging
from collections import defaultdict
from api.database import get_db

logger = logging.getLogger(__name__)


def compute_session_similarity_matrix(sessions: list[dict]) -> list[list[float]]:
    """Build similarity matrix for a list of sessions."""
    fingerprints = []
    for s in sessions:
        if s.get("fingerprint_json"):
            fingerprints.append(json.loads(s["fingerprint_json"]))
        else:
            fingerprints.append({})

    n = len(fingerprints)
    matrix = [[0.0] * n for _ in range(n)]

    for i in range(n):
        matrix[i][i] = 1.0
        for j in range(i + 1, n):
            sim = _weighted_similarity(fingerprints[i], fingerprints[j])
            matrix[i][j] = sim
            matrix[j][i] = sim

    return matrix


def _weighted_similarity(a: dict, b: dict) -> float:
    """Weighted similarity between two session fingerprints.

    Weights:
        Artist overlap: 45%
        Transition overlap: 30%
        Era similarity: 15%
        Time-of-day: 10%
    """
    artist_sim = _jaccard_similarity(
        set(a.get("artist_ids", [])),
        set(b.get("artist_ids", [])),
    )

    transition_sim = _transition_overlap(
        a.get("sequence", []),
        b.get("sequence", []),
    )

    era_sim = _era_similarity(
        a.get("avg_song_length", 0),
        b.get("avg_song_length", 0),
    )

    behavior_sim = 1.0 - abs(
        a.get("completion_rate", 0) - b.get("completion_rate", 0)
    )

    return (
        0.45 * artist_sim
        + 0.30 * transition_sim
        + 0.15 * era_sim
        + 0.10 * behavior_sim
    )


def _jaccard_similarity(set_a: set, set_b: set) -> float:
    """Jaccard index between two sets."""
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def _transition_overlap(seq_a: list, seq_b: list) -> float:
    """Compute transition overlap between two sequences."""
    if not seq_a or not seq_b:
        return 0.0

    transitions_a = set(zip(seq_a, seq_a[1:]))
    transitions_b = set(zip(seq_b, seq_b[1:]))

    if not transitions_a or not transitions_b:
        return 0.0

    return _jaccard_similarity(transitions_a, transitions_b)


def _era_similarity(len_a: int, len_b: int) -> float:
    """Similarity based on average song length as era proxy."""
    diff = abs(len_a - len_b)
    if diff < 30:
        return 1.0
    if diff < 60:
        return 0.7
    if diff < 120:
        return 0.4
    return 0.1


def get_artist_transitions(user_id: int, artist_id: str) -> list[dict]:
    """Get top next artists from transitions table."""
    with get_db() as db:
        rows = db.execute(
            """SELECT to_artist_id, transition_count, completed_count
               FROM song_transitions
               WHERE user_id = ? AND from_artist_id = ?
               ORDER BY transition_count DESC
               LIMIT 10""",
            (user_id, artist_id),
        ).fetchall()
        return [dict(r) for r in rows]
