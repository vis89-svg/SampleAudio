"""Taste Engine — scoring, profiling, clustering, similarity."""
from api.taste_engine.scoring import compute_song_score, get_scored_songs
from api.taste_engine.profile import update_taste_profile, get_taste_profile, compute_profile_drift
from api.taste_engine.clustering import cluster_sessions
from api.taste_engine.similarity import compute_session_similarity_matrix, get_artist_transitions
