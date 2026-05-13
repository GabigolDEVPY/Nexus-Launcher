"""
Definição das tabelas do banco usando SQLAlchemy declarativo.
"""

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False)
    executable_path = Column(String(1024), nullable=False, unique=True)
    save_folder = Column(String(1024), default="")
    banner_path = Column(String(1024), default="")
    cover_path = Column(String(1024), default="")
    icon_path = Column(String(1024), default="")
    description = Column(Text, default="")
    genre = Column(String(256), default="")
    platform = Column(String(128), default="PC")
    developer = Column(String(256), default="")
    publisher = Column(String(256), default="")
    release_date = Column(String(64), default="")
    total_playtime_seconds = Column(Float, default=0.0)
    last_played = Column(DateTime, nullable=True)
    is_favorite = Column(Boolean, default=False)
    category = Column(String(128), default="Uncategorized")
    rawg_id = Column(Integer, nullable=True)
    background_url = Column(String(1024), default="")
    added_at = Column(DateTime, default=datetime.utcnow)

    sessions = relationship(
        "PlaySession", back_populates="game", cascade="all, delete-orphan"
    )
    save_profiles = relationship(
        "SaveProfile", back_populates="game", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Game id={self.id} name='{self.name}'>"


class PlaySession(Base):
    __tablename__ = "play_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, default=0.0)

    game = relationship("Game", back_populates="sessions")

    def __repr__(self):
        return f"<PlaySession game_id={self.game_id} duration={self.duration_seconds:.0f}s>"


class SaveProfile(Base):
    __tablename__ = "save_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    save_folder = Column(String(1024), nullable=False)
    last_synced = Column(DateTime, nullable=True)
    sync_enabled = Column(Boolean, default=True)
    file_count = Column(Integer, default=0)
    total_size_bytes = Column(Integer, default=0)

    game = relationship("Game", back_populates="save_profiles")

    def __repr__(self):
        return f"<SaveProfile game_id={self.game_id} folder='{self.save_folder}'>"


class ImageCache(Base):
    __tablename__ = "image_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String(2048), nullable=False, unique=True)
    local_path = Column(String(1024), nullable=False)
    cached_at = Column(DateTime, default=datetime.utcnow)


class MetadataCache(Base):
    __tablename__ = "metadata_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query = Column(String(512), nullable=False, unique=True)
    result_json = Column(Text, nullable=False)
    cached_at = Column(DateTime, default=datetime.utcnow)
