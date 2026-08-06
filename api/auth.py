"""Authentication — registration, login, JWT tokens."""
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import bcrypt
import jwt
from config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRY_HOURS
from api.database import get_db

security = HTTPBearer()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_token(user_id: int, username: str) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
    """Extract user from JWT token. Returns dict with user_id and username."""
    payload = decode_token(credentials.credentials)
    user_id = int(payload["sub"])
    username = payload["username"]
    return {"user_id": user_id, "username": username}


def register_user(username: str, password: str, email: str | None) -> dict:
    """Register a new user. Returns {user_id, username}."""
    with get_db() as db:
        existing = db.execute(
            "SELECT id FROM users WHERE username = ? OR email = ?",
            (username, email),
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Username or email already exists")

        password_hash = hash_password(password)
        cursor = db.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
            (username, email, password_hash),
        )
        user_id = cursor.lastrowid

        # Create default preferences
        db.execute(
            "INSERT INTO user_preferences (user_id) VALUES (?)",
            (user_id,),
        )

        return {"user_id": user_id, "username": username}


def authenticate_user(username: str, password: str) -> dict:
    """Validate credentials. Returns {user_id, username}."""
    with get_db() as db:
        user = db.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if not user or not verify_password(password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid username or password")

        db.execute(
            "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
            (user["id"],),
        )

        return {"user_id": user["id"], "username": user["username"]}


def get_user_profile(user_id: int) -> dict:
    """Get user profile info."""
    with get_db() as db:
        user = db.execute(
            "SELECT id, username, email, ytmusic_auth_file, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "ytmusic_connected": user["ytmusic_auth_file"] is not None,
            "created_at": user["created_at"],
        }
