"""SQLite database setup and connection management."""
import os
import sqlite3
from contextlib import contextmanager
from config import DATABASE_PATH


def init_db():
    """Create all tables if they don't exist."""
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE,
                password_hash TEXT NOT NULL,
                ytmusic_auth_file TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS listening_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                video_id TEXT NOT NULL,
                title TEXT,
                artist TEXT,
                album TEXT,
                thumbnail TEXT,
                duration TEXT,
                duration_seconds INTEGER DEFAULT 0,
                artist_id TEXT,
                album_id TEXT,
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                duration_played INTEGER DEFAULT 0,
                completed BOOLEAN DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_likes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                video_id TEXT NOT NULL,
                title TEXT,
                artist TEXT,
                album TEXT,
                thumbnail TEXT,
                duration TEXT,
                duration_seconds INTEGER DEFAULT 0,
                artist_id TEXT,
                album_id TEXT,
                liked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, video_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS followed_artists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                artist_id TEXT NOT NULL,
                artist_name TEXT,
                followed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, artist_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS followed_albums (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                album_id TEXT NOT NULL,
                album_title TEXT,
                album_artist TEXT,
                followed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, album_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id INTEGER PRIMARY KEY,
                preferred_quality TEXT DEFAULT 'normal',
                clean_audio BOOLEAN DEFAULT 1,
                daily_mix_count INTEGER DEFAULT 6,
                theme TEXT DEFAULT 'dark',
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_history_user ON listening_history(user_id, played_at DESC);
            CREATE INDEX IF NOT EXISTS idx_likes_user ON user_likes(user_id);
            CREATE INDEX IF NOT EXISTS idx_followed_artists_user ON followed_artists(user_id);
            CREATE INDEX IF NOT EXISTS idx_followed_albums_user ON followed_albums(user_id);

            -- =============================================
            -- Recommendation System v2 Tables
            -- =============================================

            CREATE TABLE IF NOT EXISTS listening_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                started_at TIMESTAMP NOT NULL,
                ended_at TIMESTAMP,
                songs_count INTEGER DEFAULT 0,
                fingerprint_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_user ON listening_sessions(user_id, started_at DESC);

            CREATE TABLE IF NOT EXISTS session_songs (
                session_id INTEGER NOT NULL,
                song_id TEXT NOT NULL,
                video_id TEXT NOT NULL,
                artist_id TEXT,
                album_id TEXT,
                play_order INTEGER NOT NULL,
                completed BOOLEAN DEFAULT 0,
                duration_played INTEGER DEFAULT 0,
                PRIMARY KEY (session_id, video_id),
                FOREIGN KEY (session_id) REFERENCES listening_sessions(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_session_songs_session ON session_songs(session_id, play_order);

            CREATE TABLE IF NOT EXISTS song_transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                from_video_id TEXT NOT NULL,
                to_video_id TEXT NOT NULL,
                from_artist_id TEXT,
                to_artist_id TEXT,
                transition_count INTEGER DEFAULT 1,
                completed_count INTEGER DEFAULT 0,
                skipped_count INTEGER DEFAULT 0,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, from_video_id, to_video_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_transitions_from ON song_transitions(user_id, from_video_id);
            CREATE INDEX IF NOT EXISTS idx_transitions_to ON song_transitions(user_id, to_video_id);

            CREATE TABLE IF NOT EXISTS taste_profiles (
                user_id INTEGER PRIMARY KEY,
                short_term_json TEXT NOT NULL DEFAULT '{}',
                long_term_json TEXT NOT NULL DEFAULT '{}',
                profile_version TEXT DEFAULT 'v2.0',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS recommendation_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                mix_type TEXT NOT NULL,
                mix_index INTEGER DEFAULT 0,
                video_id TEXT NOT NULL,
                position INTEGER DEFAULT 0,
                engine_version TEXT DEFAULT 'v2.0',
                shown_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                played BOOLEAN DEFAULT 0,
                completed BOOLEAN DEFAULT 0,
                liked BOOLEAN DEFAULT 0,
                skipped BOOLEAN DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_feedback_user ON recommendation_feedback(user_id, mix_type, shown_at);
        """)

        cols = [row[1] for row in db.execute("PRAGMA table_info(listening_history)").fetchall()]
        if 'skipped' not in cols:
            db.execute("ALTER TABLE listening_history ADD COLUMN skipped BOOLEAN DEFAULT 0")
        if 'skip_position' not in cols:
            db.execute("ALTER TABLE listening_history ADD COLUMN skip_position INTEGER DEFAULT 0")
        if 'session_id' not in cols:
            db.execute("ALTER TABLE listening_history ADD COLUMN session_id INTEGER REFERENCES listening_sessions(id)")
        if 'source' not in cols:
            db.execute("ALTER TABLE listening_history ADD COLUMN source TEXT DEFAULT 'search'")


@contextmanager
def get_db():
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
