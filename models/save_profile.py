from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class SaveProfileData:
    id: int = 0
    game_id: int = 0
    save_folder: str = ""
    last_synced: Optional[datetime] = None
    sync_enabled: bool = True
    file_count: int = 0
    total_size_bytes: int = 0

    @property
    def size_formatted(self) -> str:
        if self.total_size_bytes < 1024:
            return f"{self.total_size_bytes} B"
        elif self.total_size_bytes < 1024**2:
            return f"{self.total_size_bytes / 1024:.1f} KB"
        else:
            return f"{self.total_size_bytes / (1024**2):.1f} MB"
