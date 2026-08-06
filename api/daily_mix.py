"""Daily Mix v2 — recommendation products powered by Taste Engine."""
import random
import logging
from api.search import get_recommendations, get_artist, get_album
from api.database import get_db
from api.taste_engine.scoring import get_scored_songs
from api.taste_engine.clustering import cluster_sessions
from api.taste_engine.profile import get_taste_profile, compute_profile_drift
from api.taste_engine.similarity import get_artist_transitions

logger = logging.getLogger(__name__)

MIX_SIZE = 25
DAILY_MIX_COUNT = 3


def get_top_artists(user_id: int, limit: int = 20) -> list[dict]:
    """Get most played artists from listening history."""
    with get_db() as db:
        rows = db.execute(
            """SELECT artist, artist_id, COUNT(*) as play_count
               FROM listening_history
               WHERE user_id = ? AND artist IS NOT NULL AND artist != ''
               GROUP BY artist
               ORDER BY play_count DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
        return [{"artist": r["artist"], "artist_id": r["artist_id"], "play_count": r["play_count"]} for r in rows]


def get_top_albums(user_id: int, limit: int = 10) -> list[dict]:
    """Get most played albums from listening history."""
    with get_db() as db:
        rows = db.execute(
            """SELECT album, album_id, artist, COUNT(*) as play_count
               FROM listening_history
               WHERE user_id = ? AND album IS NOT NULL AND album != ''
               GROUP BY album
               ORDER BY play_count DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
        return [{"album": r["album"], "album_id": r["album_id"], "artist": r["artist"], "play_count": r["play_count"]} for r in rows]


def get_recently_played(user_id: int, limit: int = 20) -> list[dict]:
    """Get recently played tracks with full data."""
    with get_db() as db:
        rows = db.execute(
            """SELECT video_id, title, artist, album, thumbnail, duration, duration_seconds, artist_id, album_id
               FROM listening_history
               WHERE user_id = ?
               ORDER BY played_at DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def get_liked_songs(user_id: int) -> list[dict]:
    """Get liked songs with full data."""
    with get_db() as db:
        rows = db.execute(
            """SELECT video_id, title, artist, album, thumbnail, duration, duration_seconds, artist_id, album_id
               FROM user_likes
               WHERE user_id = ?
               ORDER BY liked_at DESC""",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def generate_daily_mix(user_id: int, num_mixes: int = DAILY_MIX_COUNT) -> list[dict]:
    """Generate Daily Mix playlists using behavioral clusters.

    Composition per mix:
        80% Familiar — top-scored songs from cluster's artists
        10% Related — artists adjacent to cluster's top artists
         5% Emerging — new artists in affinity space
         5% Wildcard — high-scored songs outside primary cluster
    """
    clusters = cluster_sessions(user_id)
    scored_songs = get_scored_songs(user_id)
    profile = get_taste_profile(user_id)

    if not clusters:
        return _fallback_mix(user_id)

    scored_by_artist = _index_songs_by_artist(scored_songs)
    recently_played_ids = {s["video_id"] for s in get_recently_played(user_id, limit=50)}
    mixes = []

    for i, cluster in enumerate(clusters[:num_mixes]):
        centroid = cluster.get("centroid", {})
        cluster_artists = centroid.get("top_artists", [])

        familiar = _get_familiar_tracks(cluster_artists, scored_by_artist, recently_played_ids, limit=20)
        related = _get_related_tracks(user_id, cluster_artists, recently_played_ids, limit=3)
        emerging = _get_emerging_tracks(user_id, cluster_artists, scored_by_artist, limit=2)

        tracks = _deduplicate_tracks(familiar + related + emerging)
        tracks = tracks[:MIX_SIZE]

        if tracks:
            mixes.append({
                "name": f"Daily Mix {i + 1}",
                "based_on": cluster_artists[:3],
                "tracks": [_format_track(t) for t in tracks],
                "engine_version": "v2.0",
            })

    if not mixes:
        return _fallback_mix(user_id)

    return mixes


def generate_discovery_mix(user_id: int) -> dict:
    """Generate Discovery Mix with more adventurous composition.

    Composition:
        40% Familiar — anchors from top-scored songs
        25% Similar session songs — from behaviorally similar sessions
        20% Related artists — affinity expansion
        10% Taste-trending — popular within user's taste
         5% Wildcards — exploration outside comfort zone
    """
    scored_songs = get_scored_songs(user_id)
    clusters = cluster_sessions(user_id)
    recently_played_ids = {s["video_id"] for s in get_recently_played(user_id, limit=50)}

    scored_by_artist = _index_songs_by_artist(scored_songs)
    all_cluster_artists = []
    for c in clusters:
        all_cluster_artists.extend(c.get("centroid", {}).get("top_artists", []))

    familiar = _get_familiar_tracks(all_cluster_artists[:10], scored_by_artist, recently_played_ids, limit=18)
    related = _get_related_tracks(user_id, all_cluster_artists[:10], recently_played_ids, limit=10)

    tracks = _deduplicate_tracks(familiar + related)
    tracks = tracks[:MIX_SIZE]

    return {
        "name": "Discovery Mix",
        "tracks": [_format_track(t) for t in tracks],
        "engine_version": "v2.0",
    }


def generate_because_you_liked(user_id: int) -> list[dict]:
    """Generate 'Because You Liked' suggestions."""
    liked = get_liked_songs(user_id)
    if not liked:
        return []

    seeds = liked[:3]
    results = []

    for seed in seeds:
        try:
            recs = get_recommendations(seed["video_id"], limit=10)
            tracks = []
            for t in recs:
                tracks.append({
                    "id": t.get("id", ""),
                    "title": t.get("title", ""),
                    "artist": t.get("artist", ""),
                    "artist_id": t.get("artist_id", ""),
                    "album": t.get("album", ""),
                    "album_id": t.get("album_id", ""),
                    "duration": t.get("duration", ""),
                    "duration_seconds": t.get("duration_seconds", 0),
                    "thumbnail": t.get("thumbnail", ""),
                    "url": t.get("url", ""),
                })
            if tracks:
                results.append({
                    "seed_title": seed.get("title", ""),
                    "seed_artist": seed.get("artist", ""),
                    "seed_video_id": seed["video_id"],
                    "tracks": tracks,
                })
        except Exception as e:
            logger.warning(f"Recommendation fetch failed for {seed['video_id']}: {e}")

    return results


def generate_album_suggestions(user_id: int) -> list[dict]:
    """Suggest albums user has partially played but not completed."""
    with get_db() as db:
        rows = db.execute(
            """SELECT album, album_id, artist, artist_id,
                      COUNT(*) as play_count,
                      COUNT(DISTINCT video_id) as unique_tracks
               FROM listening_history
               WHERE user_id = ? AND album IS NOT NULL AND album_id IS NOT NULL
               GROUP BY album_id
               HAVING play_count >= 2
               ORDER BY play_count DESC
               LIMIT 10""",
            (user_id,),
        ).fetchall()

    suggestions = []
    for row in rows:
        try:
            album_data = get_album(row["album_id"])
            total_tracks = len(album_data.get("tracks", []))
            if total_tracks > 0:
                completion = row["unique_tracks"] / total_tracks
                if completion < 0.8:
                    suggestions.append({
                        "album": row["album"],
                        "album_id": row["album_id"],
                        "artist": row["artist"],
                        "artist_id": row["artist_id"],
                        "play_count": row["play_count"],
                        "completion": round(completion, 2),
                        "total_tracks": total_tracks,
                        "thumbnail": album_data.get("thumbnail", ""),
                    })
        except Exception as e:
            logger.warning(f"Album fetch failed for {row['album_id']}: {e}")

    return suggestions


def generate_new_artist_suggestions(user_id: int) -> list[dict]:
    """Suggest new artists based on related artists of favorites."""
    top_artists = get_top_artists(user_id, limit=10)
    if not top_artists:
        return []

    with get_db() as db:
        followed = {r[0] for r in db.execute(
            "SELECT artist_id FROM followed_artists WHERE user_id = ?",
            (user_id,),
        ).fetchall()}

    suggestions = []
    seen_ids = set()

    for artist in top_artists[:5]:
        if not artist.get("artist_id"):
            continue
        try:
            artist_data = get_artist(artist["artist_id"])
            related = artist_data.get("related", {}).get("browseId", [])
            for rel_id in related[:5]:
                if rel_id not in followed and rel_id not in seen_ids:
                    seen_ids.add(rel_id)
                    rel_data = get_artist(rel_id)
                    suggestions.append({
                        "artist_id": rel_id,
                        "artist_name": rel_data.get("name", ""),
                        "thumbnail": rel_data.get("thumbnail", ""),
                        "based_on": artist["artist"],
                    })
        except Exception as e:
            logger.warning(f"Related artist fetch failed for {artist['artist_id']}: {e}")

    return suggestions[:10]


def generate_suggestions(user_id: int) -> dict:
    """Generate personalized suggestions (legacy compatibility)."""
    liked = get_liked_songs(user_id)
    top_artists = get_top_artists(user_id, limit=5)
    top_albums = get_top_albums(user_id, limit=5)

    suggestions = {
        "based_on_likes": [],
        "top_artists": top_artists,
        "top_albums": top_albums,
    }

    if liked:
        seed = random.choice(liked)
        try:
            recs = get_recommendations(seed["video_id"], limit=10)
            for t in recs:
                suggestions["based_on_likes"].append({
                    "id": t.get("id", ""),
                    "title": t.get("title", ""),
                    "artist": t.get("artist", ""),
                    "artist_id": t.get("artist_id", ""),
                    "album": t.get("album", ""),
                    "album_id": t.get("album_id", ""),
                    "duration": t.get("duration", ""),
                    "duration_seconds": t.get("duration_seconds", 0),
                    "thumbnail": t.get("thumbnail", ""),
                    "url": t.get("url", ""),
                })
        except Exception:
            pass

    return suggestions


def is_mix_stale(user_id: int, max_age_hours: int = 12) -> bool:
    """Check if mixes need recomputation based on profile drift or new plays."""
    profile = get_taste_profile(user_id)
    if not profile:
        return True

    drift = compute_profile_drift(user_id)
    if drift > 0.20:
        return True

    updated_at = profile.get("updated_at", "1970-01-01")
    with get_db() as db:
        row = db.execute(
            """SELECT COUNT(*) FROM listening_history
               WHERE user_id = ? AND played_at > ?""",
            (user_id, updated_at),
        ).fetchone()
        if row and row[0] > 30:
            return True

    return False


# === Internal Helpers ===

def _get_familiar_tracks(artist_ids: list, scored_by_artist: dict,
                         exclude_ids: set, limit: int = 20) -> list[dict]:
    """Get top-scored familiar tracks from specified artists."""
    tracks = []
    for aid in artist_ids:
        artist_songs = scored_by_artist.get(aid, [])
        for song in artist_songs:
            if song["video_id"] not in exclude_ids:
                tracks.append(song)
                if len(tracks) >= limit:
                    return tracks
    return tracks


def _get_related_tracks(user_id: int, artist_ids: list,
                        exclude_ids: set, limit: int = 10) -> list[dict]:
    """Get tracks from related artists using transition data."""
    tracks = []
    for aid in artist_ids:
        transitions = get_artist_transitions(user_id, aid)
        for t in transitions:
            if t["to_artist_id"] and t["to_artist_id"] not in [a for a in artist_ids]:
                tracks.append({
                    "video_id": f"transition_{t['to_artist_id']}",
                    "artist_id": t["to_artist_id"],
                    "score": t["transition_count"],
                    "source": "transition",
                })
                if len(tracks) >= limit:
                    return tracks
    return tracks


def _get_emerging_tracks(user_id: int, cluster_artists: list,
                         scored_by_artist: dict, limit: int = 5) -> list[dict]:
    """Get tracks from artists not in cluster but with high scores."""
    cluster_set = set(cluster_artists)
    emerging = []
    for aid, songs in scored_by_artist.items():
        if aid not in cluster_set:
            emerging.extend(songs)
    emerging.sort(key=lambda x: x.get("score", 0), reverse=True)
    return emerging[:limit]


def _index_songs_by_artist(scored_songs: list[dict]) -> dict[str, list[dict]]:
    """Index scored songs by artist_id for fast lookup."""
    index: dict[str, list[dict]] = {}
    for song in scored_songs:
        aid = song.get("artist_id")
        if aid:
            if aid not in index:
                index[aid] = []
            index[aid].append(song)
    return index


def _deduplicate_tracks(tracks: list[dict]) -> list[dict]:
    """Remove duplicate tracks by video_id."""
    seen = set()
    result = []
    for t in tracks:
        vid = t.get("video_id", "")
        if vid and vid not in seen:
            seen.add(vid)
            result.append(t)
    return result


def _format_track(track: dict) -> dict:
    """Format track for API response."""
    return {
        "id": track.get("video_id", ""),
        "title": track.get("title", ""),
        "artist": track.get("artist", ""),
        "artist_id": track.get("artist_id", ""),
        "album": track.get("album", ""),
        "album_id": track.get("album_id", ""),
        "duration": track.get("duration", ""),
        "duration_seconds": track.get("duration_seconds", 0),
        "thumbnail": track.get("thumbnail", ""),
        "url": f"https://music.youtube.com/watch?v={track.get('video_id', '')}",
    }


def _fallback_mix(user_id: int) -> list[dict]:
    """Fallback: use top artists when no clusters exist."""
    top_artists = get_top_artists(user_id, limit=5)
    if not top_artists:
        return []

    tracks = []
    for artist in top_artists[:3]:
        if artist.get("artist_id"):
            try:
                artist_data = get_artist(artist["artist_id"])
                top_songs = artist_data.get("top_songs", [])[:8]
                for s in top_songs:
                    vid = s.get("id", s.get("videoId", ""))
                    tracks.append({
                        "id": vid,
                        "title": s.get("title", ""),
                        "artist": s.get("artist", artist["artist"]),
                        "artist_id": s.get("artist_id", ""),
                        "album": s.get("album", ""),
                        "album_id": s.get("album_id", ""),
                        "duration": s.get("duration", ""),
                        "duration_seconds": s.get("duration_seconds", 0),
                        "thumbnail": s.get("thumbnail", ""),
                        "url": f"https://music.youtube.com/watch?v={vid}",
                    })
            except Exception:
                pass
        if len(tracks) >= MIX_SIZE:
            break

    if tracks:
        tracks = tracks[:MIX_SIZE]
        return [{
            "name": "Daily Mix 1",
            "based_on": [a["artist"] for a in top_artists[:3]],
            "tracks": tracks,
            "engine_version": "v2.0",
        }]
    return []
