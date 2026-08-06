"""Pydantic models for request/response validation."""
from pydantic import BaseModel, Field
from typing import Optional


class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6, max_length=128)
    email: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


class UserProfile(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    ytmusic_connected: bool = False
    created_at: str


class HistoryEntry(BaseModel):
    video_id: str
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    thumbnail: Optional[str] = None
    duration: Optional[str] = None
    duration_seconds: Optional[int] = 0
    artist_id: Optional[str] = None
    album_id: Optional[str] = None
    played_at: Optional[str] = None
    duration_played: int = 0
    completed: bool = False


class LikeEntry(BaseModel):
    video_id: str
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    thumbnail: Optional[str] = None
    duration: Optional[str] = None
    duration_seconds: Optional[int] = 0
    artist_id: Optional[str] = None
    album_id: Optional[str] = None
    liked_at: Optional[str] = None


class FollowedArtist(BaseModel):
    artist_id: str
    artist_name: Optional[str] = None
    followed_at: Optional[str] = None


class FollowedAlbum(BaseModel):
    album_id: str
    album_title: Optional[str] = None
    album_artist: Optional[str] = None
    followed_at: Optional[str] = None


class UserPreferences(BaseModel):
    preferred_quality: str = "normal"
    clean_audio: bool = True
    daily_mix_count: int = 6
    theme: str = "dark"
