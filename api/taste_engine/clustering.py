"""Clustering — behavioral session clustering with dynamic threshold."""
import logging
from collections import defaultdict
from api.database import get_db
from api.sessions import get_recent_sessions

logger = logging.getLogger(__name__)

INITIAL_THRESHOLD = 0.45
MIN_CLUSTERS = 3
MAX_CLUSTERS = 6
THRESHOLD_STEP = 0.05


def cluster_sessions(user_id: int) -> list[dict]:
    """Cluster user sessions using agglomerative clustering with dynamic threshold."""
    sessions = get_recent_sessions(user_id, limit=50)

    if len(sessions) < MIN_CLUSTERS:
        return _singleton_clusters(sessions)

    import json
    fingerprints = []
    for s in sessions:
        if s.get("fingerprint_json"):
            fp = json.loads(s["fingerprint_json"])
            fp["_session_id"] = s["id"]
            fingerprints.append(fp)

    if len(fingerprints) < MIN_CLUSTERS:
        return _singleton_clusters(sessions)

    threshold = INITIAL_THRESHOLD

    while True:
        clusters = _agglomerative_cluster(fingerprints, threshold)
        if MIN_CLUSTERS <= len(clusters) <= MAX_CLUSTERS:
            break
        if len(clusters) > MAX_CLUSTERS:
            threshold -= THRESHOLD_STEP
        else:
            threshold += THRESHOLD_STEP
        if threshold > 0.8 or threshold < 0.1:
            break

    result = []
    for i, cluster in enumerate(clusters):
        result.append({
            "id": i,
            "sessions": cluster,
            "centroid": _compute_centroid(cluster),
            "size": len(cluster),
        })

    return result


def _singleton_clusters(sessions: list[dict]) -> list[dict]:
    """One cluster per session (no meaningful grouping yet), each carrying a
    centroid so Daily-Mix generation can pull familiar tracks from it."""
    import json
    clusters = []
    for i, s in enumerate(sessions):
        fp = {}
        if s.get("fingerprint_json"):
            try:
                fp = json.loads(s["fingerprint_json"])
            except Exception:
                fp = {}
        fp["_session_id"] = s["id"]
        clusters.append({
            "id": i,
            "sessions": [s],
            "centroid": _compute_centroid([fp]),
            "size": 1,
        })
    return clusters


def _agglomerative_cluster(fingerprints: list[dict], threshold: float) -> list[list[dict]]:
    """Simple agglomerative clustering based on artist overlap similarity."""
    clusters = [[fp] for fp in fingerprints]

    while len(clusters) > 1:
        best_sim = -1
        best_pair = (0, 1)

        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                sim = _cluster_similarity(clusters[i], clusters[j])
                if sim > best_sim:
                    best_sim = sim
                    best_pair = (i, j)

        if best_sim < threshold:
            break

        i, j = best_pair
        clusters[i].extend(clusters[j])
        clusters.pop(j)

    return clusters


def _cluster_similarity(cluster_a: list[dict], cluster_b: list[dict]) -> float:
    """Average similarity between two clusters."""
    total = 0
    count = 0
    for a in cluster_a:
        for b in cluster_b:
            total += _session_similarity(a, b)
            count += 1
    return total / count if count else 0


def _session_similarity(a: dict, b: dict) -> float:
    """Compute similarity between two session fingerprints."""
    artist_sim = _jaccard_similarity(
        set(a.get("artist_ids", [])),
        set(b.get("artist_ids", [])),
    )

    era_a = _decade_from_length(a.get("avg_song_length", 0))
    era_b = _decade_from_length(b.get("avg_song_length", 0))
    era_sim = 1.0 if era_a == era_b else 0.5

    completion_diff = abs(a.get("completion_rate", 0) - b.get("completion_rate", 0))
    behavior_sim = 1.0 - completion_diff

    return 0.45 * artist_sim + 0.30 * behavior_sim + 0.15 * era_sim + 0.10 * behavior_sim


def _jaccard_similarity(set_a: set, set_b: set) -> float:
    """Jaccard index between two sets."""
    if not set_a and not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def _decade_from_length(avg_length: int) -> str:
    """Rough era proxy from average song length."""
    if avg_length < 210:
        return "modern"
    elif avg_length < 270:
        return "2000s"
    else:
        return "classic"


def _compute_centroid(cluster: list[dict]) -> dict:
    """Compute centroid of a cluster."""
    all_artists = defaultdict(int)
    total_completion = 0
    total_skip = 0
    count = len(cluster)

    for fp in cluster:
        for aid in fp.get("artist_ids", []):
            all_artists[aid] += 1
        total_completion += fp.get("completion_rate", 0)
        total_skip += fp.get("skip_rate", 0)

    top_artists = sorted(all_artists, key=all_artists.get, reverse=True)[:5]

    return {
        "top_artists": top_artists,
        "avg_completion_rate": round(total_completion / count, 2) if count else 0,
        "avg_skip_rate": round(total_skip / count, 2) if count else 0,
    }
