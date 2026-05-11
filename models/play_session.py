from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class PlaySessionData:
    id: int = 0
    game_id: int = 0
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: float = 0.0

    @property
    def duration_formatted(self) -> str:
        m = int(self.duration_seconds // 60)
        s = int(self.duration_seconds % 60)
        return f"{m}m {s}s"
