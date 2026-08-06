"""Per-user YTMusic instance management with OAuth support."""
import os
import threading
from typing import Optional
from ytmusicapi import YTMusic, OAuthCredentials
from config import OAUTH_CREDENTIALS_PATH, OAUTH_TOKENS_DIR

_yt_instances: dict[int, YTMusic] = {}
_yt_lock = threading.Lock()

_default_yt: Optional[YTMusic] = None


def _get_default_yt() -> YTMusic:
    """Get the default unauthenticated YTMusic instance (fallback)."""
    global _default_yt
    if _default_yt is None:
        _default_yt = YTMusic()
    return _default_yt


def load_oauth_credentials() -> Optional[OAuthCredentials]:
    """Load OAuth credentials from config file."""
    if not os.path.exists(OAUTH_CREDENTIALS_PATH):
        return None
    import json
    with open(OAUTH_CREDENTIALS_PATH) as f:
        creds = json.load(f)
    if creds.get("client_id") and creds.get("client_secret"):
        return OAuthCredentials(creds["client_id"], creds["client_secret"])
    return None


def get_ytmusic_for_user(user_id: int, auth_file: Optional[str] = None) -> YTMusic:
    """Get a YTMusic instance for a specific user.
    
    If auth_file is provided and exists, creates an authenticated instance.
    Otherwise, returns the default unauthenticated instance.
    """
    with _yt_lock:
        if user_id in _yt_instances:
            return _yt_instances[user_id]

        yt = _create_ytmusic(user_id, auth_file)
        _yt_instances[user_id] = yt
        return yt


def _create_ytmusic(user_id: int, auth_file: Optional[str] = None) -> YTMusic:
    """Create a new YTMusic instance."""
    if auth_file and os.path.exists(auth_file):
        creds = load_oauth_credentials()
        if creds:
            return YTMusic(auth=auth_file, oauth_credentials=creds)
        return YTMusic(auth=auth_file)
    return _get_default_yt()


def invalidate_user_instance(user_id: int):
    """Remove a user's cached YTMusic instance (e.g., after OAuth connect)."""
    with _yt_lock:
        _yt_instances.pop(user_id, None)


def get_user_auth_path(user_id: int, username: str) -> str:
    """Get the OAuth token file path for a user."""
    os.makedirs(OAUTH_TOKENS_DIR, exist_ok=True)
    return os.path.join(OAUTH_TOKENS_DIR, f"{user_id}_{username}_oauth.json")
