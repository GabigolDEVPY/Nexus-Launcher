"""
Sincroniza o estado do launcher com o repositorio GitHub do usuario.
O SQLite local continua existindo, mas o repo passa a guardar a fonte de verdade
dos dados de usuario restauraveis.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from database.db_manager import DatabaseManager
from database.models import (
    Game as GameModel,
    PlaySession as SessionModel,
    SaveProfile as SaveProfileModel,
)
from utils.logger import get_logger

logger = get_logger("UserDataSync")


class UserDataSyncService:
    """Exporta e restaura o estado do launcher a partir do repositorio GitHub."""

    SNAPSHOT_PATH = "NexusLauncher/user_state.json"
    SNAPSHOT_VERSION = 1
    EXPORTED_SETTINGS_KEYS = [
        "github_repo_url",
        "github_repo_name",
        "save_sync_enabled",
        "save_watch_interval_s",
        "theme",
        "language",
        "auto_fetch_metadata",
        "minimize_to_tray",
        "start_with_windows",
        "save_sync_profiles_migrated",
        "pending_save_restore_game_ids",
        "last_selected_game_id",
        "window_geometry",
    ]

    def __init__(
        self, db: DatabaseManager, settings, sync_manager, notification_service
    ):
        self.db = db
        self.settings = settings
        self.sync_manager = sync_manager
        self.notification = notification_service

    def bootstrap(self) -> bool:
        """Puxa snapshot remoto quando necessario ou publica o estado local inicial."""
        if not self.sync_manager.is_configured():
            return False

        if not self.sync_manager.initialize():
            return False

        remote_snapshot = self.sync_manager.read_json(self.SNAPSHOT_PATH)
        local_has_state = self._local_has_state()
        local_marker = self._normalize_timestamp(
            self.settings.get("user_state_last_synced_at", "")
        )

        if remote_snapshot:
            remote_marker = self._normalize_timestamp(
                remote_snapshot.get("exported_at_utc", "")
            )

            if (not local_has_state) or (
                remote_marker and remote_marker > local_marker
            ):
                if self.restore_snapshot(remote_snapshot):
                    self.settings.update_many(
                        {
                            "user_state_last_synced_at": remote_snapshot.get(
                                "exported_at_utc", ""
                            )
                        }
                    )
                    logger.info("Estado do launcher restaurado do GitHub")
                    return True
            return False

        if local_has_state:
            self.sync_now("estado inicial do launcher", notify=False)

        return False

    def sync_now(self, reason: str, notify: bool = False) -> bool:
        """Exporta o estado atual do launcher para o repositorio do usuario."""
        if not self.sync_manager.is_configured():
            return False

        snapshot = self._build_snapshot()
        current_remote = self.sync_manager.read_json(self.SNAPSHOT_PATH)
        if current_remote and self._payload_changed(current_remote, snapshot) is False:
            self.settings.update_many(
                {"user_state_last_synced_at": current_remote.get("exported_at_utc", "")}
            )
            return True

        commit_message = self._build_commit_message(reason, snapshot["exported_at_utc"])
        success = self.sync_manager.write_json_and_sync(
            self.SNAPSHOT_PATH,
            snapshot,
            commit_message,
        )
        if success:
            self.settings.update_many(
                {"user_state_last_synced_at": snapshot["exported_at_utc"]}
            )
            if notify:
                self.notification.success(
                    "Dados do launcher sincronizados com o GitHub."
                )
        elif notify:
            self.notification.warning(
                "Nao foi possivel sincronizar os dados do launcher."
            )

        return success

    def restore_snapshot(self, snapshot: dict[str, Any]) -> bool:
        """Substitui o estado local do usuario pelo snapshot remoto."""
        if not snapshot or snapshot.get("schema_version") != self.SNAPSHOT_VERSION:
            logger.warning("Snapshot remoto ausente ou com versao invalida")
            return False

        games = snapshot.get("games", [])
        play_sessions = snapshot.get("play_sessions", [])
        save_profiles = snapshot.get("save_profiles", [])
        settings_payload = snapshot.get("settings", {})

        with self.db.session() as sess:
            sess.query(SessionModel).delete()
            sess.query(SaveProfileModel).delete()
            sess.query(GameModel).delete()

            for game_data in games:
                sess.add(
                    GameModel(
                        id=game_data.get("id"),
                        name=game_data.get("name", ""),
                        executable_path=game_data.get("executable_path", ""),
                        save_folder=game_data.get("save_folder", ""),
                        banner_path=game_data.get("banner_path", ""),
                        cover_path=game_data.get("cover_path", ""),
                        icon_path=game_data.get("icon_path", ""),
                        description=game_data.get("description", ""),
                        genre=game_data.get("genre", ""),
                        platform=game_data.get("platform", "PC"),
                        developer=game_data.get("developer", ""),
                        publisher=game_data.get("publisher", ""),
                        release_date=game_data.get("release_date", ""),
                        total_playtime_seconds=game_data.get(
                            "total_playtime_seconds", 0.0
                        ),
                        last_played=self._parse_datetime(game_data.get("last_played")),
                        is_favorite=bool(game_data.get("is_favorite", False)),
                        category=game_data.get("category", "Uncategorized"),
                        rawg_id=game_data.get("rawg_id"),
                        background_url=game_data.get("background_url", ""),
                        added_at=self._parse_datetime(game_data.get("added_at")),
                    )
                )

            for session_data in play_sessions:
                sess.add(
                    SessionModel(
                        id=session_data.get("id"),
                        game_id=session_data.get("game_id"),
                        started_at=self._parse_datetime(session_data.get("started_at")),
                        ended_at=self._parse_datetime(session_data.get("ended_at")),
                        duration_seconds=session_data.get("duration_seconds", 0.0),
                    )
                )

            for profile_data in save_profiles:
                sess.add(
                    SaveProfileModel(
                        id=profile_data.get("id"),
                        game_id=profile_data.get("game_id"),
                        save_folder=profile_data.get("save_folder", ""),
                        last_synced=self._parse_datetime(
                            profile_data.get("last_synced")
                        ),
                        sync_enabled=bool(profile_data.get("sync_enabled", False)),
                        file_count=profile_data.get("file_count", 0),
                        total_size_bytes=profile_data.get("total_size_bytes", 0),
                    )
                )

        filtered_settings = {
            key: settings_payload[key]
            for key in self.EXPORTED_SETTINGS_KEYS
            if key in settings_payload
        }
        self.settings.update_many(filtered_settings)
        return True

    def _local_has_state(self) -> bool:
        with self.db.session() as sess:
            game_count = sess.query(GameModel).count()
            return game_count > 0

    def _build_snapshot(self) -> dict[str, Any]:
        exported_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

        with self.db.session() as sess:
            games = sess.query(GameModel).order_by(GameModel.id).all()
            sessions = sess.query(SessionModel).order_by(SessionModel.id).all()
            save_profiles = (
                sess.query(SaveProfileModel).order_by(SaveProfileModel.id).all()
            )

        return {
            "schema_version": self.SNAPSHOT_VERSION,
            "exported_at_utc": exported_at,
            "settings": {
                key: self.settings.get(key) for key in self.EXPORTED_SETTINGS_KEYS
            },
            "games": [self._serialize_game(game) for game in games],
            "play_sessions": [self._serialize_session(session) for session in sessions],
            "save_profiles": [
                self._serialize_save_profile(profile) for profile in save_profiles
            ],
        }

    def _serialize_game(self, game: GameModel) -> dict[str, Any]:
        return {
            "id": game.id,
            "name": game.name,
            "executable_path": game.executable_path,
            "save_folder": game.save_folder or "",
            "banner_path": game.banner_path or "",
            "cover_path": game.cover_path or "",
            "icon_path": game.icon_path or "",
            "description": game.description or "",
            "genre": game.genre or "",
            "platform": game.platform or "PC",
            "developer": game.developer or "",
            "publisher": game.publisher or "",
            "release_date": game.release_date or "",
            "total_playtime_seconds": game.total_playtime_seconds or 0.0,
            "last_played": self._format_datetime(game.last_played),
            "is_favorite": bool(game.is_favorite),
            "category": game.category or "Uncategorized",
            "rawg_id": game.rawg_id,
            "background_url": game.background_url or "",
            "added_at": self._format_datetime(game.added_at),
        }

    def _serialize_session(self, session: SessionModel) -> dict[str, Any]:
        return {
            "id": session.id,
            "game_id": session.game_id,
            "started_at": self._format_datetime(session.started_at),
            "ended_at": self._format_datetime(session.ended_at),
            "duration_seconds": session.duration_seconds or 0.0,
        }

    def _serialize_save_profile(self, profile: SaveProfileModel) -> dict[str, Any]:
        return {
            "id": profile.id,
            "game_id": profile.game_id,
            "save_folder": profile.save_folder or "",
            "last_synced": self._format_datetime(profile.last_synced),
            "sync_enabled": bool(profile.sync_enabled),
            "file_count": profile.file_count or 0,
            "total_size_bytes": profile.total_size_bytes or 0,
        }

    def _build_commit_message(self, reason: str, exported_at: str) -> str:
        readable_timestamp = exported_at.replace("T", " ").replace("Z", " UTC")
        return f"Launcher state: {reason} ({readable_timestamp})"

    def _payload_changed(
        self, previous: dict[str, Any], current: dict[str, Any]
    ) -> bool:
        return self._without_exported_at(previous) != self._without_exported_at(current)

    @staticmethod
    def _without_exported_at(payload: dict[str, Any]) -> dict[str, Any]:
        clone = dict(payload)
        clone.pop("exported_at_utc", None)
        return clone

    @staticmethod
    def _normalize_timestamp(value: str) -> str:
        return str(value or "").strip()

    @staticmethod
    def _format_datetime(value: Optional[datetime]) -> Optional[str]:
        if value is None:
            return None
        return value.replace(microsecond=0).isoformat() + "Z"

    @staticmethod
    def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None

        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1]
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None
