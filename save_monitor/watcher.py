"""
Monitoramento de pastas de save em tempo real usando Watchdog.
Detecta alteracoes e atualiza as estatisticas locais de save.
Nao dispara sincronizacao com o GitHub: o sync acontece no maximo 1x por dia
ou pelo botao Sync da interface.
"""

import os
import threading
from typing import Dict

from PySide6.QtCore import QObject, Signal
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from core.constants import IGNORE_PATTERNS, SAVE_SYNC_DEBOUNCE_MS
from database.db_manager import DatabaseManager
from database.models import Game as GameModel, SaveProfile as SaveProfileModel
from github_sync.sync_manager import SyncManager
from services.notification_service import NotificationService
from utils.helpers import count_files, get_directory_size
from utils.logger import get_logger

logger = get_logger("SaveWatcher")


class _SaveEventHandler(FileSystemEventHandler):
    """Handler individual para uma pasta de save."""

    def __init__(self, game_id: int, game_name: str, debouncer: "_Debouncer"):
        super().__init__()
        self.game_id = game_id
        self.game_name = game_name
        self._debouncer = debouncer

    def on_any_event(self, event: FileSystemEvent):
        if event.is_directory:
            return

        basename = os.path.basename(event.src_path)
        for pattern in IGNORE_PATTERNS:
            pattern_clean = pattern.replace("*", "")
            if pattern_clean in basename:
                return

        self._debouncer.trigger(self.game_id, self.game_name)


class _Debouncer:
    """Agrupa varias alteracoes em um unico commit apos debounce."""

    def __init__(self, delay_ms: int):
        self._delay = delay_ms / 1000.0
        self._timers: Dict[int, threading.Timer] = {}
        self._lock = threading.Lock()
        self._callback = None

    def set_callback(self, callback):
        self._callback = callback

    def trigger(self, game_id: int, game_name: str):
        with self._lock:
            if game_id in self._timers:
                self._timers[game_id].cancel()

            timer = threading.Timer(
                self._delay,
                self._fire,
                args=[game_id, game_name],
            )
            timer.daemon = True
            self._timers[game_id] = timer
            timer.start()

    def _fire(self, game_id: int, game_name: str):
        with self._lock:
            self._timers.pop(game_id, None)
        if self._callback:
            self._callback(game_id, game_name)


class SaveWatcher(QObject):
    """Gerencia watchers de multiplas pastas de save."""

    sync_requested = Signal(int, str)
    sync_started = Signal(int)
    sync_completed = Signal(int)
    sync_error = Signal(int, str)

    def __init__(
        self,
        db: DatabaseManager,
        sync_manager: SyncManager,
        notification_service: NotificationService,
    ):
        super().__init__()
        self.db = db
        self.sync_manager = sync_manager
        self.notification = notification_service
        self._observer = Observer()
        self._watchers: Dict[int, object] = {}
        self._debouncer = _Debouncer(SAVE_SYNC_DEBOUNCE_MS)
        self._debouncer.set_callback(self._on_debounced_change)

    def start_all(self):
        """Inicia monitoramento para todos os jogos com sync habilitado."""
        self._observer.start()
        if not self.sync_manager.settings.get("save_sync_enabled", False):
            logger.info("SaveWatcher: sincronizacao global desativada")
            return

        with self.db.session() as sess:
            profiles = sess.query(SaveProfileModel).filter_by(sync_enabled=True).all()
            for profile in profiles:
                self._add_watch(profile.game_id, profile.save_folder)

        logger.info(f"SaveWatcher: monitorando {len(self._watchers)} pastas")

    def stop_all(self):
        """Para todos os watchers."""
        self._observer.stop()
        self._observer.join(timeout=5)
        self._watchers.clear()
        logger.info("SaveWatcher: todos os watchers parados")

    def add_game_watch(self, game_id: int, save_folder: str):
        """Adiciona monitoramento para um jogo especifico."""
        if game_id in self._watchers:
            return
        self._add_watch(game_id, save_folder)

    def remove_game_watch(self, game_id: int):
        """Remove monitoramento de um jogo."""
        if game_id in self._watchers:
            self._observer.unschedule(self._watchers[game_id])
            del self._watchers[game_id]
            logger.info(f"Watch removido para jogo {game_id}")

    def _add_watch(self, game_id: int, save_folder: str):
        if not os.path.isdir(save_folder):
            logger.warning(f"Pasta de save nao existe: {save_folder}")
            return

        with self.db.session() as sess:
            game = sess.get(GameModel, game_id)
            game_name = game.name if game else f"Game_{game_id}"

        handler = _SaveEventHandler(game_id, game_name, self._debouncer)
        watch = self._observer.schedule(handler, save_folder, recursive=True)
        self._watchers[game_id] = watch
        logger.debug(f"Watch adicionado: {game_name} -> {save_folder}")

    def _on_debounced_change(self, game_id: int, game_name: str):
        """Callback apos debonce para atualizar estatisticas de save."""
        logger.info(f"Alteracao detectada em saves de '{game_name}'")

        with self.db.session() as sess:
            profile = (
                sess.query(SaveProfileModel)
                .filter_by(
                    game_id=game_id,
                )
                .first()
            )
            if not profile or not profile.save_folder:
                return

            save_folder = profile.save_folder
            profile.file_count = count_files(save_folder)
            profile.total_size_bytes = get_directory_size(save_folder)

        # Apenas notifica que as estatisticas locais mudaram (para atualizar a UI)
        self.sync_completed.emit(game_id)
