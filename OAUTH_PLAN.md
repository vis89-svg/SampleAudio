# OAuth Implementation Plan — SampleAudio

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Architecture](#architecture)
4. [Database Schema](#database-schema)
5. [New Files](#new-files)
6. [Files to Modify](#files-to-modify)
7. [Implementation Phases](#implementation-phases)
8. [OAuth Device Flow](#oauth-device-flow)
9. [Dependencies](#dependencies)
10. [Security Considerations](#security-considerations)

---

## Overview

Implement full user authentication and per-user YouTube Music OAuth to enable personalized recommendations, listening history, Daily Mixes, taste profiles, and library management.

**Current state:** Single unauthenticated `YTMusic()` instance shared by all users.

**Target state:** Per-user authenticated `YTMusic()` instances with full OAuth, local user profiles, listening history, and personalized features.

---

## Prerequisites (Manual Setup by User)

| Step | Action | Where |
|---|---|---|
| 1 | Create a Google Cloud project | [console.cloud.google.com](https://console.cloud.google.com) |
| 2 | Enable YouTube Data API v3 | Google Cloud Console → APIs & Services → Enable APIs |
| 3 | Create OAuth 2.0 credentials (Desktop type) | Google Cloud Console → APIs & Services → Credentials → Create OAuth Client ID |
| 4 | Note down `client_id` and `client_secret` | Shown once after creation |

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   Frontend                       │
│  Login/Register → JWT Token → All API calls     │
└──────────────┬──────────────────────────────────┘
               │ Authorization: Bearer <jwt>
┌──────────────▼──────────────────────────────────┐
│              FastAPI Backend                     │
│  Auth middleware validates JWT → extracts user   │
│  Each request gets user-specific YTMusic instance│
└──────────────┬──────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────┐
│              SQLite Database                     │
│  users, user_tokens, listening_history,          │
│  followed_artists, followed_albums, preferences  │
└──────────────┬──────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────┐
│          Per-User YTMusic Instances              │
│  Each user has their own OAuth token file        │
│  Auto-refresh handled by ytmusicapi              │
└─────────────────────────────────────────────────┘
```

---

## Database Schema (SQLite)

### `users` table

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Auto-increment |
| `username` | TEXT UNIQUE NOT NULL | Login name |
| `email` | TEXT UNIQUE | Optional |
| `password_hash` | TEXT NOT NULL | bcrypt hash |
| `ytmusic_auth_file` | TEXT | Path to OAuth JSON file |
| `created_at` | TIMESTAMP | Default: now |
| `last_login` | TIMESTAMP | Updated on login |

### `listening_history` table

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Auto-increment |
| `user_id` | INTEGER FK | → users.id |
| `video_id` | TEXT NOT NULL | YouTube video ID |
| `title` | TEXT | |
| `artist` | TEXT | |
| `album` | TEXT | |
| `played_at` | TIMESTAMP | Default: now |
| `duration_played` | INTEGER | Seconds listened |
| `completed` | BOOLEAN | Finished full song |

### `user_likes` table

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Auto-increment |
| `user_id` | INTEGER FK | → users.id |
| `video_id` | TEXT NOT NULL | |
| `liked_at` | TIMESTAMP | Default: now |
| UNIQUE(user_id, video_id) | | Prevents duplicates |

### `followed_artists` table

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Auto-increment |
| `user_id` | INTEGER FK | → users.id |
| `artist_id` | TEXT NOT NULL | YouTube Music browse ID |
| `artist_name` | TEXT | Cached name |
| `followed_at` | TIMESTAMP | Default: now |
| UNIQUE(user_id, artist_id) | | |

### `followed_albums` table

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Auto-increment |
| `user_id` | INTEGER FK | → users.id |
| `album_id` | TEXT NOT NULL | YouTube Music browse ID |
| `album_title` | TEXT | Cached title |
| `album_artist` | TEXT | Cached artist |
| `followed_at` | TIMESTAMP | Default: now |
| UNIQUE(user_id, album_id) | | |

### `user_preferences` table

| Column | Type | Notes |
|---|---|---|
| `user_id` | INTEGER FK | → users.id (PK) |
| `preferred_quality` | TEXT | Default: "normal" |
| `clean_audio` | BOOLEAN | Default: true |
| `daily_mix_count` | INTEGER | Default: 6 |
| `theme` | TEXT | Default: "dark" |

---

## New Files

| File | Purpose |
|---|---|
| `api/database.py` | SQLite connection, table creation, migrations |
| `api/auth.py` | Registration, login, JWT token generation/validation, password hashing |
| `api/models.py` | Pydantic schemas for request/response |
| `api/user_profile.py` | User profile routes, listening history, likes, followed artists |
| `api/ytmusic_manager.py` | Per-user YTMusic instance management, OAuth file handling |
| `api/daily_mix.py` | Daily Mix playlist generation algorithm |
| `oauth_config.json` | OAuth credentials config (gitignored) |
| `static/login.html` | Login/register page |

---

## Files to Modify

| File | Changes |
|---|---|
| `config.py` | Add DB path, JWT secret, OAuth config path |
| `main.py` | Add auth middleware, new route includes, login page serving |
| `api/search.py` | Replace singleton YTMusic with per-user instances |
| `static/app.js` | Add auth state, login/register flow, JWT token management |
| `static/index.html` | Add login/register UI, user profile section |
| `static/style.css` | Login/register page styles |
| `requirements.txt` | Add: `bcrypt`, `PyJWT`, `python-jose[cryptography]` |

---

## Implementation Phases

### Phase 1: Auth System (Core)

1. `config.py` — Add `DATABASE_PATH`, `JWT_SECRET`, `JWT_EXPIRY_HOURS`, `OAUTH_CREDENTIALS_PATH`
2. `requirements.txt` — Add `bcrypt`, `PyJWT`
3. `api/database.py` — SQLite setup, `users` table creation
4. `api/auth.py` — `register()`, `login()`, `generate_token()`, `validate_token()`, `get_current_user()`
5. `api/models.py` — `UserRegister`, `UserLogin`, `TokenResponse` Pydantic models
6. `main.py` — Add `POST /api/auth/register`, `POST /api/auth/login`, auth middleware dependency
7. `static/login.html` — Login/register page
8. `static/app.js` — Auth state management, token storage, protected API calls
9. `static/index.html` — Login/register link, user menu

**Deliverable:** Users can register and login. JWT tokens authenticate all API requests.

### Phase 2: Listening History & Profile

1. `api/database.py` — Add `listening_history`, `user_likes`, `followed_artists`, `followed_albums` tables
2. `api/user_profile.py` — Routes:
   - `POST /api/user/history` — Log a play
   - `GET /api/user/history` — Get listening history
   - `POST /api/user/like` — Like a song
   - `DELETE /api/user/like/{video_id}` — Unlike a song
   - `GET /api/user/likes` — Get liked songs
   - `GET /api/user/followed-artists` — Get followed artists
   - `POST /api/user/follow-artist` — Follow an artist
   - `DELETE /api/user/follow-artist/{artist_id}` — Unfollow artist
   - `GET /api/user/followed-albums` — Get followed albums
   - `POST /api/user/follow-album` — Follow an album
3. `main.py` — Integrate history tracking: auto-log plays on stream completion
4. `static/app.js` — Auto-log listening history, like button, follow artist button

**Deliverable:** Full listening history, likes, and follows tracked per user.

### Phase 3: OAuth Integration

1. `api/ytmusic_manager.py` — Per-user `YTMusic(auth=oauth_file, oauth_credentials=creds)` instances, cached per user
2. `config.py` — Add `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`
3. `main.py` — Add:
   - `POST /api/user/connect-ytmusic` — Initiates device code flow
   - `GET /api/user/ytmusic-status` — Check connection status
4. Frontend — "Connect YouTube Music" button, device code flow UI

**Deliverable:** Users can connect their YouTube Music account via OAuth. Per-user authenticated YTMusic instances enable library access.

### Phase 4: Personalized Recommendations

1. `api/daily_mix.py` — Generate Daily Mix 01-06 by:
   - Fetching user's listening history
   - Clustering listened artists into groups (by genre, frequency, recency)
   - For each cluster, fetching related tracks via `get_watch_playlist()` or `get_song_related()`
   - Returning 6 playlists of ~25 tracks each
2. `main.py` — Add:
   - `GET /api/user/daily-mix` — Generate Daily Mix playlists
   - `GET /api/user/for-you` — Personalized recommendations based on taste profile
   - `GET /api/user/recently-played` — Last 50 played tracks
3. `static/app.js` — Daily Mix cards on home page, "For You" section, recently played list
4. `static/index.html` — Daily Mix grid, For You section

**Deliverable:** Spotify-like Daily Mixes and personalized recommendations.

---

## OAuth Device Flow (User-Facing)

```
1. User clicks "Connect YouTube Music"
2. Backend calls ytmusicapi's setup_oauth() flow:
   - POST to youtube.com/o/oauth2/device/code
   - Gets: user_code ("XXX-XXX-XXX"), verification_url
3. Backend returns verification_url + user_code to frontend
4. Frontend shows: "Go to youtube.com/activate and enter code: XXX-XXX-XXX"
5. User authorizes on their phone/laptop
6. Backend polls oauth2.googleapis.com/token until authorized
7. Gets access_token + refresh_token
8. Saves to oauth/{username}_oauth.json
9. Creates YTMusic(auth=file, oauth_credentials=creds) instance
10. Frontend shows "Connected ✓"
```

---

## Dependencies

```bash
pip install bcrypt PyJWT
```

| Package | Purpose |
|---|---|
| `bcrypt` | Password hashing |
| `PyJWT` | JWT token generation/validation |
| `python-jose[cryptography]` | Alternative JWT library (optional) |

---

## Security Considerations

| Concern | Solution |
|---|---|
| Password storage | bcrypt hash, never plain text |
| JWT tokens | Short-lived (24h), stored in localStorage |
| OAuth files | Stored in `oauth/` directory, gitignored |
| OAuth secrets | In `oauth_config.json`, gitignored |
| CORS | Restrict to `localhost:8000` in production |
| Rate limiting | Add slowapi for auth endpoints |
| SQL injection | Use parameterized queries (never string interpolation) |
| Token refresh | ytmusicapi handles automatically (triggers at <60s to expiry) |

---

## ytmusicapi Methods Available After Auth

| Feature | Method | Description |
|---|---|---|
| Listening history | `get_history()` | Play history (reverse chronological) |
| Taste profile | `get_tasteprofile()` | Suggested artists for taste selection |
| Set taste | `set_tasteprofile(artists)` | Select favorite artists |
| Library songs | `get_library_songs()` | User's saved songs |
| Library artists | `get_library_artists()` | User's followed artists |
| Library albums | `get_library_albums()` | User's saved albums |
| Rate songs | `rate_song(videoId, rating)` | Thumbs up/down |
| Personalized home | `get_home()` | "Your morning music", "Quick picks" rows |
| Subscribe | `subscribe_artists(channelIds)` | Follow artists |
| Unsubscribe | `unsubscribe_artists(channelIds)` | Unfollow artists |

---

## Notes

- A token can only be refreshed by the same OAuth credentials that created it
- Each user's auth file must match the credentials used during `setup_oauth()`
- Without OAuth auth, we're limited to `UNAUTHORIZED` mode (search/browse only)
- All library/playlist/history/rating features require authentication
