"""
Dataclass que representa um jogo — usada como DTO entre camadas.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


@dataclass
class GameData:
    id: int = 0
    name: str = ""
    executable_path: str = ""
    save_folder: str = ""
    banner_path: str = ""
    cover_path: str = ""
    icon_path: str = ""
    description: str = ""
    genre: str = ""
    platform: str = "PC"
    developer: str = ""
    publisher: str = ""
    release_date: str = ""
    total_playtime_seconds: float = 0.0
    last_played: Optional[datetime] = None
    is_favorite: bool = False
    category: str = "Uncategorized"
    rawg_id: Optional[int] = None
    background_url: str = ""
    added_at: Optional[datetime] = None

    @property
    def total_playtime_formatted(self) -> str:
        hours = int(self.total_playtime_seconds // 3600)
        minutes = int((self.total_playtime_seconds % 3600) // 60)
        if hours > 0:
            return f"{hours}h {minutes}min"
        return f"{minutes}min"

    @property
    def last_played_formatted(self) -> str:
        if self.last_played is None:
            return "Nunca jogado"
        return self.last_played.strftime("%d/%m/%Y %H:%M")
