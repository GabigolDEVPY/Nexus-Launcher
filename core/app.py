"""
Ciclo de vida da aplicação NexusLauncher.
Inicializa banco, serviços, UI e encerra tudo de forma limpa.
"""

import os
from PySide6.QtWidgets import QSplashScreen
from PySide6.QtGui import QPixmap, QColor, QPainter, QFont
from PySide6.QtCore import Qt

from core.settings import Settings
from core.constants import (
    APP_DATA_DIR,
    CACHE_DIR,
    IMAGE_CACHE_DIR,
    ASSETS_DIR,
    LOG_DIR,
    APP_NAME,
    prepare_runtime_environment,
)
from core.single_instance import SingleInstanceGuard
from database.db_manager import DatabaseManager
from services.notification_service import NotificationService
from services.play_tracker import PlayTracker
from services.metadata_service import MetadataService
from services.image_service import ImageService
from services.startup_service import StartupService
from services.user_data_sync import UserDataSyncService
from save_monitor.watcher import SaveWatcher
from github_sync.sync_manager import SyncManager
from ui.main_window import MainWindow


class NexusApp:
    """Orquestra inicialização e encerramento de todos os subsistemas."""

    def __init__(self, qapp, guard: SingleInstanceGuard):
        self.qapp = qapp
        self.guard = guard
        prepare_runtime_environment()
        self.settings = Settings()
        self._ensure_dirs()
        self._splash = self._show_splash()

        # Banco de dados
        self.db = DatabaseManager()

        # Serviços globais
        self.notification_service = NotificationService()
        self.image_service = ImageService()
        self.metadata_service = MetadataService(self.settings)
        self.play_tracker = PlayTracker(self.db)
        self.startup_service = StartupService(self.settings)

        # Sync GitHub
        self.sync_manager = SyncManager(self.settings, self.notification_service)
        self.user_data_sync = UserDataSyncService(
            self.db,
            self.settings,
            self.sync_manager,
            self.notification_service,
        )
        self.user_data_sync.bootstrap()

        # Monitor de saves
        self.save_watcher = SaveWatcher(
            self.db, self.sync_manager, self.notification_service
        )

        # Janela principal
        self.main_window = MainWindow(
            db=self.db,
            settings=self.settings,
            metadata_service=self.metadata_service,
            image_service=self.image_service,
            play_tracker=self.play_tracker,
            save_watcher=self.save_watcher,
            sync_manager=self.sync_manager,
            user_data_sync=self.user_data_sync,
            notification_service=self.notification_service,
            startup_service=self.startup_service,
        )

        # Uma segunda instancia pede para mostrar a janela existente
        self.guard.activate_requested.connect(self._activate_main_window)

    def _ensure_dirs(self):
        for d in [APP_DATA_DIR, CACHE_DIR, IMAGE_CACHE_DIR, LOG_DIR, ASSETS_DIR]:
            os.makedirs(d, exist_ok=True)

    def _show_splash(self) -> QSplashScreen:
        """Splash screen enquanto carrega recursos."""
        pixmap = QPixmap(500, 300)
        pixmap.fill(QColor("#0d0d0d"))
        painter = QPainter(pixmap)
        painter.setPen(QColor("#1EA1FF"))
        font = QFont("Segoe UI", 28, QFont.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, APP_NAME)
        painter.end()
        splash = QSplashScreen(pixmap)
        splash.show()
        self.qapp.processEvents()
        return splash

    def start(self):
        """Mostra a janela principal e encerra o splash."""
        self.guard.start_listening()
        self.play_tracker.start()
        self.save_watcher.start_all()

        self.main_window.showMaximized()
        self._splash.finish(self.main_window)

    def _activate_main_window(self):
        self.main_window._restore_from_tray()

    def shutdown(self):
        """Encerra todos os serviços de forma limpa."""
        self.save_watcher.stop_all()
        self.play_tracker.stop()
        self.sync_manager.shutdown()
        self.settings.save()
        self.db.close()
