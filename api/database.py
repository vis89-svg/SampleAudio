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
        """)


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
