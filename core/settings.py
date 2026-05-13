"""
Gerenciador de configurações persistido em JSON.
"""

import json
import os
from typing import Any
from core.constants import CONFIG_PATH, prepare_runtime_environment


class Settings:
    """Singleton que carrega e salva configurações em disco."""

    _instance = None
    _defaults = {
        "github_token": "",
        "github_repo_url": "",
        "github_repo_name": "",
        "rawg_api_key": "",
        "steamgriddb_api_key": "",
        "save_sync_enabled": False,
        "save_watch_interval_s": 2,
        "theme": "dark",
        "language": "pt-BR",
        "auto_fetch_metadata": True,
        "minimize_to_tray": False,
        "start_with_windows": False,
        "save_sync_profiles_migrated": False,
        "pending_save_restore_game_ids": [],
        "user_state_last_synced_at": "",
        "last_selected_game_id": None,
        "window_geometry": None,
    }

    def __new__(cls):
        if cls._instance is None:
            prepare_runtime_environment()
            cls._instance = super().__new__(cls)
            cls._instance._data = dict(cls._defaults)
            cls._instance._load()
        return cls._instance

    def _load(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                self._data.update(stored)
            except (json.JSONDecodeError, IOError):
                pass

        if self._normalize_github_settings():
            self.save()

    def save(self):
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any):
        self._data[key] = value
        self.save()

    def update_many(self, values: dict[str, Any], persist: bool = True):
        self._data.update(values)
        self._normalize_github_settings()
        if persist:
            self.save()

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any):
        self.set(key, value)

    def _normalize_github_settings(self) -> bool:
        """Corrige configuracoes legadas ou preenchidas com os campos invertidos."""
        repo_url = str(self._data.get("github_repo_url", "") or "").strip()
        repo_name = str(self._data.get("github_repo_name", "") or "").strip()
        changed = False

        if self._looks_like_repo_url(repo_name) and not self._looks_like_repo_url(
            repo_url
        ):
            repo_url, repo_name = repo_name, repo_url
            changed = True

        if repo_url and not repo_name:
            derived_name = self._extract_repo_name(repo_url)
            if derived_name:
                repo_name = derived_name
                changed = True
        elif self._looks_like_repo_url(repo_name):
            derived_name = self._extract_repo_name(repo_name)
            if derived_name and derived_name != repo_name:
                repo_name = derived_name
                changed = True

        if changed:
            self._data["github_repo_url"] = repo_url
            self._data["github_repo_name"] = repo_name

        return changed

    @staticmethod
    def _looks_like_repo_url(value: str) -> bool:
        value = (value or "").strip()
        if not value:
            return False
        return (
            value.startswith("https://github.com/")
            or value.startswith("http://github.com/")
            or value.startswith("git@github.com:")
            or ("/" in value and "\\" not in value and " " not in value)
        )

    @staticmethod
    def _extract_repo_name(value: str) -> str:
        value = (value or "").strip().rstrip("/")
        if not value:
            return ""
        if value.endswith(".git"):
            value = value[:-4]
        if value.startswith("git@github.com:"):
            value = value.split(":", 1)[1]
        return value.rsplit("/", 1)[-1].strip()
