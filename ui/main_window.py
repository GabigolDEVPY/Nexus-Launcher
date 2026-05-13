"""
Janela principal do NexusLauncher.
Layout: carrossel de jogos + painel de detalhes + background dinamico.
"""

import hashlib
from datetime import datetime
import os
from typing import Optional

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QThread,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from core.constants import APP_NAME
from database.models import Game as GameModel, SaveProfile as SaveProfileModel
from models.game import GameData
from ui.styles.theme import STYLESHEET
from ui.widgets.add_game_dialog import AddGameDialog
from ui.widgets.game_carousel import GameCarousel
from ui.widgets.game_detail_panel import GameDetailPanel
from ui.widgets.game_settings_dialog import GameSettingsDialog
from ui.widgets.loading_screen import LoadingScreen
from ui.widgets.settings_dialog import SettingsDialog
from ui.widgets.toast_widget import ToastWidget
from utils.helpers import (
    count_files,
    get_directory_size,
    human_readable_size,
    sanitize_filename,
)
from utils.logger import get_logger

logger = get_logger("MainWindow")


def _lerp_color(left: QColor, right: QColor, factor: float) -> QColor:
    return QColor(
        int(left.red() + (right.red() - left.red()) * factor),
        int(left.green() + (right.green() - left.green()) * factor),
        int(left.blue() + (right.blue() - left.blue()) * factor),
        int(left.alpha() + (right.alpha() - left.alpha()) * factor),
    )


def _palette_for_game(game: GameData) -> tuple[QColor, QColor, QColor]:
    seed = f"{game.name}|{game.genre}|{game.platform}|{game.id}".encode("utf-8")
    digest = hashlib.sha1(seed).hexdigest()
    hue = int(digest[:2], 16) * 359 // 255
    primary = QColor.fromHsv(hue, 175, 210)
    secondary = QColor.fromHsv((hue + 24) % 360, 155, 130)
    tertiary = QColor.fromHsv((hue + 42) % 360, 110, 60)
    return primary, secondary, tertiary


class _LaunchOverlay(QWidget):
    def __init__(self, game: GameData, accent: QColor, parent=None):
        super().__init__(parent)
        self._accent = accent
        self._dot_count = 0

        self.setGeometry(parent.rect())
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(18)

        title = QLabel(game.name)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "color: white;"
            "font-family: 'Segoe UI';"
            "font-size: 38px;"
            "font-weight: 700;"
            "background: transparent;"
        )
        layout.addWidget(title)

        self._status_label = QLabel("Iniciando jogo...")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setStyleSheet(
            "color: rgba(255,255,255,0.52);"
            "font-family: 'Segoe UI';"
            "font-size: 16px;"
            "background: transparent;"
        )
        layout.addWidget(self._status_label)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick_dots)
        self._timer.start(380)

    def _tick_dots(self):
        self._dot_count = (self._dot_count + 1) % 4
        self._status_label.setText("Iniciando jogo" + "." * self._dot_count)

    def stop(self):
        self._timer.stop()

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 224))

        glow = QRadialGradient(self.width() / 2, self.height() / 2, self.width() * 0.34)
        glow.setColorAt(
            0.0,
            QColor(self._accent.red(), self._accent.green(), self._accent.blue(), 100),
        )
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(self.rect(), glow)
        painter.end()


def _game_model_to_data(game: GameModel) -> GameData:
    return GameData(
        id=game.id,
        name=game.name,
        executable_path=game.executable_path,
        save_folder=game.save_folder or "",
        banner_path=game.banner_path or "",
        cover_path=game.cover_path or "",
        icon_path=game.icon_path or "",
        description=game.description or "",
        genre=game.genre or "",
        platform=game.platform or "PC",
        developer=game.developer or "",
        publisher=game.publisher or "",
        release_date=game.release_date or "",
        total_playtime_seconds=game.total_playtime_seconds or 0,
        last_played=game.last_played,
        is_favorite=game.is_favorite or False,
        category=game.category or "Uncategorized",
        rawg_id=game.rawg_id,
        background_url=game.background_url or "",
        added_at=game.added_at,
    )


class _MetadataEnrichmentThread(QThread):
    metadata_ready = Signal(dict)
    error = Signal(str)

    def __init__(self, metadata_service, image_service, game: GameData):
        super().__init__()
        self.metadata_service = metadata_service
        self.image_service = image_service
        self.game = game

    def run(self):
        try:
            payload = {"game_id": self.game.id, "name": self.game.name}
            details = None

            if self.game.rawg_id:
                details = self.metadata_service.get_game_details(
                    rawg_id=self.game.rawg_id
                )

            if not details:
                results = self.metadata_service.search_game(self.game.name)
                if results:
                    payload.update(results[0])
                    details = self.metadata_service.get_game_details(
                        rawg_id=results[0].get("rawg_id"),
                        steam_appid=results[0].get("steam_appid"),
                    )

            if details:
                payload.update(details)

            name = payload.get("name") or self.game.name
            cache_key = sanitize_filename(f"{name}_{self.game.id}".lower())

            extra_images = self.metadata_service.get_images(name)
            banner_url = (
                extra_images.get("hero")
                or extra_images.get("banner")
                or payload.get("background_url", "")
            )
            cover_url = (
                extra_images.get("cover") or payload.get("cover_url", "") or banner_url
            )

            payload["banner_path"] = ""
            payload["cover_path"] = ""
            payload["background_path"] = ""

            if banner_url:
                payload["banner_path"] = (
                    self.image_service.get_or_download(
                        f"banner_{cache_key}",
                        banner_url,
                    )
                    or ""
                )
            if cover_url:
                payload["cover_path"] = (
                    self.image_service.get_or_download(
                        f"cover_{cache_key}",
                        cover_url,
                    )
                    or ""
                )

            payload["background_path"] = (
                payload["banner_path"] or payload["cover_path"] or ""
            )
            self.metadata_ready.emit(payload)
        except Exception as e:
            logger.exception("Falha ao enriquecer metadados")
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    """Janela principal do launcher."""

    def __init__(
        self,
        db,
        settings,
        metadata_service,
        image_service,
        play_tracker,
        save_watcher,
        sync_manager,
        user_data_sync,
        notification_service,
        startup_service,
    ):
        super().__init__()
        self.db = db
        self.settings = settings
        self.metadata_service = metadata_service
        self.image_service = image_service
        self.play_tracker = play_tracker
        self.save_watcher = save_watcher
        self.sync_manager = sync_manager
        self.user_data_sync = user_data_sync
        self.notification_service = notification_service
        self.startup_service = startup_service

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1024, 700)
        self.setStyleSheet(STYLESHEET)

        self._current_game: Optional[GameData] = None
        self._all_games: list[GameData] = []
        self._metadata_thread = None
        self._metadata_target_game_id: Optional[int] = None
        self._metadata_attempted_ids: set[int] = set()
        self._startup_sync_game_ids: list[int] = []
        self._user_state_dirty = False
        self._allow_exit = False
        self._tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        self._tray_icon = None
        self._tray_message_shown = False
        self._bg_from = [QColor("#0A1020")] * 3
        self._bg_to = [QColor("#0A1020")] * 3
        self._bg_t = 1.0
        self._overlay_ref = None
        self._overlay_anim_in = None
        self._overlay_anim_out = None

        self._bg_anim = QPropertyAnimation(self, b"bgProgress")
        self._bg_anim.setDuration(850)
        self._bg_anim.setEasingCurve(QEasingCurve.InOutCubic)

        self._user_state_timer = QTimer(self)
        self._user_state_timer.setInterval(30 * 60 * 1000)
        self._user_state_timer.timeout.connect(self._flush_user_state_periodic)

        self._migrate_legacy_save_sync_profiles()
        self._build_ui()
        self._build_menu()
        self._setup_tray()
        self._connect_signals()
        self._load_games()
        self._restore_missing_local_saves_from_repo()
        self._run_startup_syncs()
        self._user_state_timer.start()
        self._flush_user_state("abertura do launcher", notify=True, force=True)

    def _get_bg_progress(self):
        return self._bg_t

    def _set_bg_progress(self, value):
        self._bg_t = value
        self.update()

    bgProgress = Property(float, _get_bg_progress, _set_bg_progress)

    def _build_ui(self):
        central = QWidget()
        central.setStyleSheet("background: transparent;")
        self.setCentralWidget(central)

        self._bg_label = QLabel(central)
        self._bg_label.setScaledContents(True)
        self._bg_label.setStyleSheet("background: transparent;")

        self._overlay = QFrame(central)
        self._overlay.setStyleSheet(
            """
            QFrame {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(8,12,24,214),
                    stop:0.36 rgba(8,12,24,168),
                    stop:0.72 rgba(8,12,24,188),
                    stop:1 rgba(8,12,24,242)
                );
                border: none;
            }
            """
        )

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        top_bar = QFrame()
        top_bar.setFixedHeight(54)
        top_bar.setStyleSheet(
            "background: rgba(0,0,0,0.34);"
            "border-bottom: 1px solid rgba(255,255,255,0.06);"
        )
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(22, 0, 22, 0)
        top_layout.setSpacing(12)

        emblem = QLabel("NX")
        emblem.setStyleSheet(
            "color: #1EA1FF;"
            "font-family: 'Segoe UI';"
            "font-size: 18px;"
            "font-weight: 700;"
            "background: transparent;"
        )
        top_layout.addWidget(emblem)

        logo = QLabel(APP_NAME.upper())
        logo.setStyleSheet(
            "color: rgba(255,255,255,0.62);"
            "font-family: 'Segoe UI';"
            "font-size: 13px;"
            "font-weight: 600;"
            "letter-spacing: 4px;"
            "background: transparent;"
        )
        top_layout.addWidget(logo)
        top_layout.addStretch()

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Buscar jogos...")
        self._search_input.setFixedWidth(280)
        self._search_input.setFixedHeight(38)
        self._search_input.setStyleSheet(
            """
            QLineEdit {
                background: rgba(255,255,255,0.08);
                color: white;
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 19px;
                padding: 0 16px;
                font-family: 'Segoe UI';
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: rgba(33,150,243,0.80);
                background: rgba(255,255,255,0.11);
            }
            QLineEdit::placeholder {
                color: rgba(255,255,255,0.34);
            }
            """
        )
        self._search_input.textChanged.connect(self._on_search)
        top_layout.addWidget(self._search_input)

        add_btn = QPushButton("+  Adicionar")
        add_btn.setFixedSize(132, 38)
        add_btn.clicked.connect(self._add_game)
        add_btn.setStyleSheet(
            """
            QPushButton {
                background: rgba(255,255,255,0.08);
                color: white;
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 19px;
                font-family: 'Segoe UI';
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 1px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.14);
                border-color: rgba(255,255,255,0.22);
            }
            QPushButton:pressed {
                background: rgba(255,255,255,0.20);
            }
            """
        )
        top_layout.addWidget(add_btn)

        config_btn = QPushButton("Config")
        config_btn.setFixedSize(106, 38)
        config_btn.clicked.connect(self._open_settings)
        config_btn.setStyleSheet(add_btn.styleSheet())
        top_layout.addWidget(config_btn)

        self._clock_label = QLabel()
        self._clock_label.setStyleSheet(
            "color: rgba(255,255,255,0.42);"
            "font-family: 'Segoe UI';"
            "font-size: 12px;"
            "background: transparent;"
        )
        top_layout.addWidget(self._clock_label)

        main_layout.addWidget(top_bar)

        self._stack = QStackedWidget()
        self._loading = LoadingScreen(self, "Carregando biblioteca")
        self._stack.addWidget(self._loading)

        content_widget = QWidget()
        content_widget.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self._detail_panel = GameDetailPanel()
        content_layout.addWidget(self._detail_panel, 1)

        self._carousel = GameCarousel()
        self._carousel.setFixedHeight(312)
        content_layout.addWidget(self._carousel)

        self._stack.addWidget(content_widget)
        self._stack.setCurrentIndex(1)
        main_layout.addWidget(self._stack, 1)

        bottom_bar = QFrame()
        bottom_bar.setFixedHeight(38)
        bottom_bar.setStyleSheet(
            "background: rgba(0,0,0,0.42);border-top: 1px solid rgba(255,255,255,0.06);"
        )
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(26, 0, 26, 0)
        bottom_layout.setSpacing(18)

        for hint_text in [
            "< >  Navegar",
            "ENTER  Jogar",
            "ESC  Sair",
        ]:
            hint = QLabel(hint_text)
            hint.setStyleSheet(
                "color: rgba(255,255,255,0.32);"
                "font-family: 'Segoe UI';"
                "font-size: 11px;"
                "background: transparent;"
            )
            bottom_layout.addWidget(hint)

        bottom_layout.addStretch()

        self._library_summary_label = QLabel("Biblioteca: 0 jogos")
        self._library_summary_label.setStyleSheet(
            "color: rgba(255,255,255,0.28);"
            "font-family: 'Segoe UI';"
            "font-size: 11px;"
            "background: transparent;"
        )
        bottom_layout.addWidget(self._library_summary_label)

        main_layout.addWidget(bottom_bar)

        self._toast = ToastWidget(self)

        self._fade_fx = QGraphicsOpacityEffect(self._detail_panel)
        self._fade_fx.setOpacity(1.0)
        self._detail_panel.setGraphicsEffect(self._fade_fx)

        self._fade_anim = QPropertyAnimation(self._fade_fx, b"opacity")
        self._fade_anim.setDuration(220)
        self._fade_anim.setEasingCurve(QEasingCurve.OutQuad)

        self._clock = QTimer(self)
        self._clock.timeout.connect(self._update_clock)
        self._clock.start(1000)
        self._update_clock()

    def _setup_tray(self):
        if not self._tray_available:
            return

        self._tray_icon = QSystemTrayIcon(self)
        self._tray_icon.setIcon(self._build_app_icon())
        self._tray_icon.setToolTip(APP_NAME)

        tray_menu = QMenu(self)
        show_action = tray_menu.addAction("Abrir Launcher")
        show_action.triggered.connect(self._restore_from_tray)

        hide_action = tray_menu.addAction("Ocultar")
        hide_action.triggered.connect(self.hide)

        tray_menu.addSeparator()

        quit_action = tray_menu.addAction("Sair")
        quit_action.triggered.connect(self._request_quit)

        self._tray_icon.setContextMenu(tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()

    def _build_app_icon(self) -> QIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor("#08111f"))
        painter = QPainter(pixmap)
        painter.setPen(QColor("#1EA1FF"))
        painter.setBrush(QColor("#0D1628"))
        painter.drawRoundedRect(2, 2, 60, 60, 12, 12)
        painter.setFont(QFont("Segoe UI", 28, QFont.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "N")
        painter.end()
        return QIcon(pixmap)

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._toggle_visibility_from_tray()

    def _toggle_visibility_from_tray(self):
        if self.isVisible():
            self.hide()
        else:
            self._restore_from_tray()

    def _restore_from_tray(self):
        if self.isMaximized():
            self.showMaximized()
        else:
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def _request_quit(self):
        self._allow_exit = True
        QApplication.quit()

    def _build_menu(self):
        menu_bar = self.menuBar()
        menu_bar.setStyleSheet(
            """
            QMenuBar {
                background: rgba(0,0,0,0.26);
                color: rgba(255,255,255,0.68);
                font-size: 12px;
                border-bottom: 1px solid rgba(255,255,255,0.04);
            }
            QMenuBar::item:selected {
                background: rgba(255,255,255,0.09);
                color: #fff;
            }
            """
        )

        games_menu = menu_bar.addMenu("Jogos")

        add_action = QAction("Adicionar Jogo", self)
        add_action.setShortcut("Ctrl+N")
        add_action.triggered.connect(self._add_game)
        games_menu.addAction(add_action)

        games_menu.addSeparator()

        refresh_action = QAction("Atualizar Biblioteca", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self._load_games)
        games_menu.addAction(refresh_action)

        games_menu.addSeparator()

        quit_action = QAction("Sair", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self._request_quit)
        games_menu.addAction(quit_action)

        settings_menu = menu_bar.addMenu("Configuracoes")
        prefs_action = QAction("Preferencias", self)
        prefs_action.triggered.connect(self._open_settings)
        settings_menu.addAction(prefs_action)

        help_menu = menu_bar.addMenu("Ajuda")
        about_action = QAction("Sobre", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _connect_signals(self):
        self._carousel.game_selected.connect(self._on_game_selected)

        self._detail_panel.play_requested.connect(self._on_play)
        self._detail_panel.favorite_toggled.connect(self._on_toggle_favorite)
        self._detail_panel.settings_requested.connect(self._on_game_settings)

        self.notification_service.toast_requested.connect(self._toast.show_toast)

        self.play_tracker.game_launched.connect(self._on_game_launched)
        self.play_tracker.game_closed.connect(self._on_game_closed)
        self.play_tracker.playtime_updated.connect(self._on_playtime_updated)

        self.save_watcher.sync_requested.connect(self._on_watcher_sync_requested)
        self.save_watcher.sync_completed.connect(self._on_sync_done)

    def _load_games(self):
        self._all_games.clear()

        with self.db.session() as sess:
            games = (
                sess.query(GameModel)
                .order_by(
                    GameModel.is_favorite.desc(),
                    GameModel.last_played.desc().nullslast(),
                    GameModel.name,
                )
                .all()
            )
            for game in games:
                self._all_games.append(_game_model_to_data(game))

        self._refresh_library_summary()
        self._carousel.set_games(self._all_games)

        if not self._all_games:
            self._current_game = None
            self._bg_label.clear()
            self._transition_background(None)
            self._detail_panel.set_metadata_status(
                "Nenhum jogo na biblioteca. Adicione um executavel para comecar.",
                "info",
            )
            return

        last_id = self.settings.get("last_selected_game_id")
        if last_id:
            for game in self._all_games:
                if game.id == last_id:
                    self._carousel.select_game_by_id(game.id, emit_signal=False)
                    self._on_game_selected(game)
                    return

        self._carousel.select_game_by_id(self._all_games[0].id, emit_signal=False)
        self._on_game_selected(self._all_games[0])

    def _load_game_data_by_id(self, game_id: int) -> Optional[GameData]:
        with self.db.session() as sess:
            game = sess.get(GameModel, game_id)
            if not game:
                return None
            return _game_model_to_data(game)

    def _on_game_selected(self, game: GameData):
        same_game = self._current_game and self._current_game.id == game.id
        self._current_game = game
        self._carousel.select_game_by_id(game.id, emit_signal=False)

        if same_game:
            return

        self._fade_anim.stop()
        self._fade_fx.setOpacity(0.0)
        self._detail_panel.set_game(game)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()

        self.settings.set("last_selected_game_id", game.id)
        self._refresh_play_button_state()

        status = self.sync_manager.get_sync_status(game.name, game.id)
        if status["synced"]:
            self._detail_panel.update_sync_status(
                True,
                f"{status['files']} arquivos ({human_readable_size(status['size'])})",
            )
        else:
            self._detail_panel.update_sync_status(False, "Nao sincronizado")

        self._update_background(game)
        self._maybe_enrich_game_metadata(game)

    def _update_background(self, game: GameData):
        self._transition_background(game)
        self._bg_label.clear()
        self._bg_label.lower()
        self._overlay.setGeometry(0, 0, self.width(), self.height())
        self._overlay.lower()

    def _on_play(self, game_id: int):
        self._detail_panel.set_play_button_state("ABRINDO...", False)

        with self.db.session() as sess:
            game = sess.get(GameModel, game_id)
            if not game:
                self.notification_service.error("Jogo nao encontrado no banco.")
                self._refresh_play_button_state()
                return

            exe = game.executable_path
            if not os.path.isfile(exe):
                self.notification_service.error(f"Executavel nao encontrado:\n{exe}")
                self._refresh_play_button_state()
                return

            success, message = self.play_tracker.launch_game(game_id, exe)

        if success:
            self.notification_service.success(f"{game.name}: {message}")
            current_data = self._current_game
            if current_data and current_data.id == game_id:
                self._show_launch_overlay(current_data)
            if self.play_tracker.is_running(game_id):
                self._refresh_play_button_state()
            else:
                self._detail_panel.set_play_button_state("ABERTO", True)
        else:
            self.notification_service.error(f"{game.name}: {message}")
            self._detail_panel.set_metadata_status(message, "error")
            self._refresh_play_button_state()

    def _on_game_launched(self, game_id: int):
        if self._current_game and self._current_game.id == game_id:
            if self.play_tracker.is_running(game_id):
                self._detail_panel.set_play_button_state("EM EXECUCAO", False)
            else:
                self._detail_panel.set_play_button_state("ABERTO", True)
            self._detail_panel.set_metadata_status(
                "Jogo iniciado. Se o Windows abriu por compatibilidade, o rastreamento pode variar.",
                "success",
            )

    def _on_game_closed(self, game_id: int, duration: float):
        from utils.helpers import format_playtime

        self._load_games()
        self.notification_service.info(
            f"Sessao encerrada - {format_playtime(duration)}"
        )
        self._refresh_play_button_state()
        self._try_apply_pending_restore_after_game_close(game_id)
        self._sync_user_state(f"sessao encerrada do jogo {game_id}")

    def _on_playtime_updated(self, game_id: int, total_seconds: float):
        if self._current_game and self._current_game.id == game_id:
            self._current_game.total_playtime_seconds = total_seconds
            self._detail_panel.update_playtime(total_seconds)

    def _on_toggle_favorite(self, game_id: int):
        with self.db.session() as sess:
            game = sess.get(GameModel, game_id)
            if game:
                game.is_favorite = not (game.is_favorite or False)
        self._load_games()
        self._sync_user_state(f"favorito alterado para o jogo {game_id}")

    def _on_game_settings(self, game_id: int):
        global_sync_enabled = self.settings.get("save_sync_enabled", False)
        with self.db.session() as sess:
            game = sess.get(GameModel, game_id)
            if not game:
                return

            game_data = _game_model_to_data(game)
            previous_name = game.name
            profile = sess.query(SaveProfileModel).filter_by(game_id=game_id).first()
            previous_save_folder = (
                profile.save_folder if profile else (game.save_folder or "")
            )
            previous_sync_enabled = profile.sync_enabled if profile else False
            sync_enabled = profile.sync_enabled if profile else global_sync_enabled

        dialog = GameSettingsDialog(
            game_data,
            sync_enabled,
            global_sync_enabled,
            self,
        )
        if dialog.exec() != GameSettingsDialog.Accepted or not dialog.result_data:
            return

        data = dialog.result_data
        name_changed = previous_name != data["name"]
        save_folder_changed = previous_save_folder != data["save_folder"]
        has_remote_save = False
        if self.sync_manager.is_configured():
            has_remote_save = self.sync_manager.get_sync_status(previous_name, game_id)[
                "synced"
            ]

        with self.db.session() as sess:
            duplicate = (
                sess.query(GameModel)
                .filter(
                    GameModel.executable_path == data["executable_path"],
                    GameModel.id != game_id,
                )
                .first()
            )
            if duplicate:
                self.notification_service.error(
                    "Ja existe outro jogo cadastrado com este executavel."
                )
                return

            game = sess.get(GameModel, game_id)
            if not game:
                return

            game.name = data["name"]
            game.executable_path = data["executable_path"]
            game.save_folder = data["save_folder"]

            profile = sess.query(SaveProfileModel).filter_by(game_id=game_id).first()
            if data["save_folder"]:
                if not profile:
                    profile = SaveProfileModel(
                        game_id=game_id,
                        save_folder=data["save_folder"],
                        sync_enabled=data["sync_enabled"],
                    )
                    sess.add(profile)
                else:
                    profile.save_folder = data["save_folder"]
                    profile.sync_enabled = data["sync_enabled"]
            elif profile:
                profile.save_folder = ""
                profile.sync_enabled = False
                profile.file_count = 0
                profile.total_size_bytes = 0
                profile.last_synced = None

        if name_changed and self.sync_manager.is_configured():
            self.sync_manager.migrate_game_repo_reference(
                game_id,
                previous_name,
                data["name"],
            )

        self._refresh_save_watch(
            game_id,
            data["save_folder"],
            data["sync_enabled"],
        )

        self.settings.set("last_selected_game_id", game_id)
        self._load_games()
        self.notification_service.success(
            f"Configuracoes de '{data['name']}' atualizadas."
        )

        should_sync_after_save = (
            bool(data["save_folder"])
            and data["sync_enabled"]
            and global_sync_enabled
            and not save_folder_changed
            and (
                previous_save_folder != data["save_folder"] or not previous_sync_enabled
            )
        )

        if save_folder_changed and has_remote_save:
            self._mark_pending_restore(game_id)
            self.notification_service.info(
                "Novo caminho de save salvo. Abra o jogo uma vez para ele criar a estrutura nova; "
                "depois o launcher aplica o save do GitHub nessa pasta."
            )
        else:
            self._clear_pending_restore(game_id)

        if dialog.sync_now_requested:
            self._sync_game_now(game_id, force=True)
        elif should_sync_after_save:
            self._sync_game_now(game_id)

        self._sync_user_state(f"configuracoes atualizadas do jogo {game_id}")
        if name_changed:
            refreshed_game = self._load_game_data_by_id(game_id)
            if refreshed_game:
                self._metadata_attempted_ids.discard(game_id)
                self._maybe_enrich_game_metadata(refreshed_game, force=True)

    def _on_sync_done(self, game_id: int):
        if self._current_game and self._current_game.id == game_id:
            status = self.sync_manager.get_sync_status(
                self._current_game.name,
                self._current_game.id,
            )
            if status["synced"]:
                self._detail_panel.update_sync_status(
                    True,
                    f"{status['files']} arquivos ({human_readable_size(status['size'])})",
                )
        self._sync_user_state(f"save sync concluido para o jogo {game_id}")

    def _on_watcher_sync_requested(self, game_id: int, game_name: str):
        success = self._sync_game_now(
            game_id,
            notify=False,
            allow_conflict_prompt=True,
        )
        if success:
            self.save_watcher.sync_completed.emit(game_id)
        else:
            self.save_watcher.sync_error.emit(game_id, "Falha na sincronizacao")
            self.notification_service.error(
                f"Erro ao sincronizar saves de '{game_name}'"
            )

    def _add_game(self):
        dialog = AddGameDialog(self.metadata_service, self.image_service, self)
        if dialog.exec() == AddGameDialog.Accepted and dialog.result_data:
            self._save_new_game(dialog.result_data)

    def _save_new_game(self, data: dict):
        with self.db.session() as sess:
            existing = (
                sess.query(GameModel)
                .filter_by(executable_path=data["executable_path"])
                .first()
            )
            if existing:
                self.notification_service.warning("Este jogo ja esta na biblioteca.")
                return

            game = GameModel(
                name=data["name"],
                executable_path=data["executable_path"],
                save_folder=data.get("save_folder", ""),
                genre=data.get("genre", ""),
                platform=data.get("platform", "PC"),
                developer=data.get("developer", ""),
                publisher=data.get("publisher", ""),
                release_date=data.get("release_date", ""),
                description=data.get("description", ""),
                rawg_id=data.get("rawg_id"),
                cover_path=data.get("cover_path", ""),
                banner_path=data.get("banner_path", ""),
                background_url=data.get("background_path", "")
                or data.get("banner_path", ""),
            )
            sess.add(game)
            sess.flush()
            game_id = game.id

            if data.get("save_folder"):
                profile = SaveProfileModel(
                    game_id=game_id,
                    save_folder=data["save_folder"],
                    sync_enabled=self.settings.get("save_sync_enabled", False),
                )
                sess.add(profile)

        if data.get("save_folder"):
            self._refresh_save_watch(
                game_id,
                data["save_folder"],
                self.settings.get("save_sync_enabled", False),
            )

        self.settings.set("last_selected_game_id", game_id)
        self._metadata_attempted_ids.discard(game_id)
        self._load_games()
        self.notification_service.success(f"'{data['name']}' adicionado a biblioteca!")

        if data.get("save_folder") and self.settings.get("save_sync_enabled", False):
            self._sync_game_now(game_id)

        self._sync_user_state(f"novo jogo adicionado: {data['name']}")

    def _on_search(self, text: str):
        query = text.strip().lower()
        if not query:
            self._carousel.set_games(self._all_games)
            if self._current_game:
                self._carousel.select_game_by_id(
                    self._current_game.id, emit_signal=False
                )
            return

        filtered = [game for game in self._all_games if query in game.name.lower()]
        self._carousel.set_games(filtered)
        if filtered:
            self._carousel.select_game_by_id(filtered[0].id, emit_signal=False)
            self._on_game_selected(filtered[0])

    def _open_settings(self):
        previous_sync_enabled = self.settings.get("save_sync_enabled", False)
        dialog = SettingsDialog(
            self.settings,
            self.sync_manager,
            self.startup_service,
            self._tray_available,
            self,
        )
        if dialog.exec() != SettingsDialog.Accepted:
            return

        restored_from_repo = self.user_data_sync.bootstrap()
        if restored_from_repo:
            self._load_games()

        current_sync_enabled = self.settings.get("save_sync_enabled", False)
        if current_sync_enabled != previous_sync_enabled:
            self._apply_global_sync_setting(current_sync_enabled)

        if self._current_game:
            self._metadata_attempted_ids.discard(self._current_game.id)
            self._maybe_enrich_game_metadata(self._current_game)

        self._sync_user_state("configuracoes do launcher atualizadas")

    def _migrate_legacy_save_sync_profiles(self):
        if not self.settings.get("save_sync_enabled", False):
            return

        if self.settings.get("save_sync_profiles_migrated", False):
            return

        with self.db.session() as sess:
            profiles = sess.query(SaveProfileModel).all()
            for profile in profiles:
                if profile.save_folder and not profile.sync_enabled:
                    profile.sync_enabled = True
                    self._startup_sync_game_ids.append(profile.game_id)

        self.settings.set("save_sync_profiles_migrated", True)

    def _run_startup_syncs(self):
        if not self._startup_sync_game_ids:
            return

        pending_ids = self._get_pending_restore_ids()
        synced_count = 0
        for game_id in self._startup_sync_game_ids:
            if game_id in pending_ids:
                continue
            if self._sync_game_now(game_id, notify=False):
                synced_count += 1

        self._startup_sync_game_ids.clear()
        self.notification_service.info(
            f"Sync inicial executado para {synced_count} jogo(s) legado(s) com saves configurados."
        )

    def _refresh_save_watch(self, game_id: int, save_folder: str, sync_enabled: bool):
        self.save_watcher.remove_game_watch(game_id)
        if (
            self.settings.get("save_sync_enabled", False)
            and sync_enabled
            and save_folder
        ):
            self.save_watcher.add_game_watch(game_id, save_folder)

    def _sync_game_now(
        self,
        game_id: int,
        force: bool = False,
        notify: bool = True,
        allow_conflict_prompt: bool = True,
    ) -> bool:
        save_folder = ""
        game_name = ""
        sync_enabled = False
        last_synced = None

        with self.db.session() as sess:
            game = sess.get(GameModel, game_id)
            profile = sess.query(SaveProfileModel).filter_by(game_id=game_id).first()

            if not game or not profile or not profile.save_folder:
                if notify:
                    self.notification_service.warning(
                        "Configure uma pasta de saves antes de sincronizar este jogo."
                    )
                return False

            save_folder = profile.save_folder
            game_name = game.name
            sync_enabled = profile.sync_enabled
            last_synced = profile.last_synced

        if not os.path.isdir(save_folder):
            os.makedirs(save_folder, exist_ok=True)

        if not self.settings.get("github_repo_url") or not self.settings.get(
            "github_token"
        ):
            if notify:
                self.notification_service.warning(
                    "Configure a URL do repositorio e o token do GitHub antes de sincronizar."
                )
            return False

        if not force and (
            not self.settings.get("save_sync_enabled", False) or not sync_enabled
        ):
            return False

        if not self.sync_manager.refresh_from_remote():
            return False

        comparison = self.sync_manager.compare_game_saves(
            game_id,
            game_name,
            save_folder,
            last_synced,
        )

        if comparison["repo_exists"] and not comparison["local_exists"]:
            return self._restore_game_saves_locally(
                game_id,
                game_name,
                save_folder,
                sync_enabled,
                notify=notify,
            )

        if not comparison["local_exists"] and not comparison["repo_exists"]:
            if notify:
                self.notification_service.warning(
                    f"Nao encontrei save local nem remoto para '{game_name}'."
                )
            return False

        if (
            comparison["repo_exists"]
            and comparison["local_exists"]
            and not comparison["identical"]
            and not comparison["can_upload_without_prompt"]
            and allow_conflict_prompt
        ):
            decision = self._ask_save_conflict_resolution(game_name, comparison)
            if decision == "remote":
                return self._restore_game_saves_locally(
                    game_id,
                    game_name,
                    save_folder,
                    sync_enabled,
                    notify=notify,
                )
            if decision == "cancel":
                if notify:
                    self.notification_service.info(
                        f"Sincronizacao de '{game_name}' adiada por enquanto."
                    )
                return True

        file_count = count_files(save_folder)
        if file_count == 0:
            if notify:
                self.notification_service.warning(
                    f"A pasta de saves de '{game_name}' esta vazia no momento."
                )
            return False

        if notify:
            self.notification_service.info(f"Sincronizando saves de '{game_name}'...")

        success = self.sync_manager.sync_game_saves(game_id, game_name, save_folder)
        if not success:
            if notify:
                self.notification_service.error(
                    f"Falha ao sincronizar saves de '{game_name}'."
                )
            return False

        self._update_profile_sync_stats(
            game_id,
            save_folder,
            fallback_timestamp=datetime.utcnow(),
        )

        self._on_sync_done(game_id)
        if notify:
            self.notification_service.success(
                f"Saves de '{game_name}' sincronizados com o GitHub."
            )
        return True

    def _restore_missing_local_saves_from_repo(self):
        if not self.settings.get("save_sync_enabled", False):
            return
        if not self.sync_manager.is_configured():
            return
        if not self.sync_manager.refresh_from_remote():
            return

        restored_count = 0
        with self.db.session() as sess:
            rows = (
                sess.query(GameModel, SaveProfileModel)
                .join(SaveProfileModel, SaveProfileModel.game_id == GameModel.id)
                .filter(SaveProfileModel.sync_enabled.is_(True))
                .all()
            )

        pending_ids = self._get_pending_restore_ids()
        for game, profile in rows:
            if not profile.save_folder:
                continue
            if game.id in pending_ids:
                continue

            comparison = self.sync_manager.compare_game_saves(
                game.id,
                game.name,
                profile.save_folder,
                profile.last_synced,
            )
            if comparison["repo_exists"] and not comparison["local_exists"]:
                if self._restore_game_saves_locally(
                    game.id,
                    game.name,
                    profile.save_folder,
                    profile.sync_enabled,
                    notify=False,
                    reload_after=False,
                ):
                    restored_count += 1

        if restored_count:
            self._load_games()
            self.notification_service.success(
                f"{restored_count} save(s) foram restaurados automaticamente do GitHub."
            )

    def _restore_game_saves_locally(
        self,
        game_id: int,
        game_name: str,
        save_folder: str,
        sync_enabled: bool,
        notify: bool = True,
        reload_after: bool = True,
    ) -> bool:
        self.save_watcher.remove_game_watch(game_id)

        if not self.sync_manager.restore_game_saves(game_id, game_name, save_folder):
            self._refresh_save_watch(game_id, save_folder, sync_enabled)
            if notify:
                self.notification_service.error(
                    f"Nao foi possivel restaurar os saves de '{game_name}' a partir do GitHub."
                )
            return False

        self._update_profile_sync_stats(
            game_id,
            save_folder,
            fallback_timestamp=datetime.utcnow(),
        )
        self._refresh_save_watch(game_id, save_folder, sync_enabled)

        if reload_after:
            self._load_games()
            self._on_sync_done(game_id)

        if notify:
            self.notification_service.success(
                f"Saves de '{game_name}' restaurados do GitHub para esta maquina."
            )
        return True

    def _try_apply_pending_restore_after_game_close(self, game_id: int):
        if game_id not in self._get_pending_restore_ids():
            return

        with self.db.session() as sess:
            game = sess.get(GameModel, game_id)
            profile = sess.query(SaveProfileModel).filter_by(game_id=game_id).first()
            if not game or not profile or not profile.save_folder:
                return

            if count_files(profile.save_folder) == 0:
                return

            restored = self._restore_game_saves_locally(
                game_id,
                game.name,
                profile.save_folder,
                profile.sync_enabled,
                notify=True,
                reload_after=True,
            )
            if restored:
                self._clear_pending_restore(game_id)

    def _update_profile_sync_stats(
        self,
        game_id: int,
        save_folder: str,
        fallback_timestamp: datetime,
    ):
        metadata = None
        if self.sync_manager.is_configured():
            with self.db.session() as sess:
                game = sess.get(GameModel, game_id)
                if game:
                    metadata = self.sync_manager.get_game_sync_metadata(
                        game_id, game.name
                    )

        last_synced = fallback_timestamp
        if metadata and metadata.get("synced_at_utc"):
            try:
                last_synced = datetime.fromisoformat(
                    metadata["synced_at_utc"].replace("Z", "")
                )
            except ValueError:
                last_synced = fallback_timestamp

        with self.db.session() as sess:
            profile = sess.query(SaveProfileModel).filter_by(game_id=game_id).first()
            if profile:
                profile.file_count = count_files(save_folder)
                profile.total_size_bytes = get_directory_size(save_folder)
                profile.last_synced = last_synced

    def _get_pending_restore_ids(self) -> set[int]:
        values = self.settings.get("pending_save_restore_game_ids", []) or []
        result = set()
        for value in values:
            try:
                result.add(int(value))
            except (TypeError, ValueError):
                continue
        return result

    def _mark_pending_restore(self, game_id: int):
        values = self._get_pending_restore_ids()
        values.add(game_id)
        self.settings.set("pending_save_restore_game_ids", sorted(values))

    def _clear_pending_restore(self, game_id: int):
        values = self._get_pending_restore_ids()
        if game_id in values:
            values.remove(game_id)
            self.settings.set("pending_save_restore_game_ids", sorted(values))

    def _ask_save_conflict_resolution(self, game_name: str, comparison: dict) -> str:
        msg = QMessageBox(self)
        msg.setWindowTitle("Conflito de Save")
        msg.setIcon(QMessageBox.Warning)
        msg.setText(f"Encontrei saves diferentes para '{game_name}'.")
        msg.setInformativeText(
            "Local: "
            f"{comparison['local_files']} arquivo(s), {human_readable_size(comparison['local_size'])}\n"
            "GitHub: "
            f"{comparison['repo_files']} arquivo(s), {human_readable_size(comparison['repo_size'])}\n\n"
            "Escolha se quer enviar o save local para sobrescrever o GitHub, "
            "ou baixar o save do GitHub para esta maquina."
        )

        upload_btn = msg.addButton("Sobrescrever GitHub", QMessageBox.AcceptRole)
        download_btn = msg.addButton("Baixar do GitHub", QMessageBox.DestructiveRole)
        cancel_btn = msg.addButton("Cancelar", QMessageBox.RejectRole)
        msg.setDefaultButton(upload_btn)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == download_btn:
            return "remote"
        if clicked == cancel_btn:
            return "cancel"
        return "local"

    def _apply_global_sync_setting(self, enabled: bool):
        profiles_data = []
        game_ids_to_sync = []

        with self.db.session() as sess:
            profiles = sess.query(SaveProfileModel).all()
            for profile in profiles:
                has_save_folder = bool((profile.save_folder or "").strip())
                profile.sync_enabled = enabled and has_save_folder
                profiles_data.append(
                    (profile.game_id, profile.save_folder, profile.sync_enabled)
                )
                if enabled and has_save_folder:
                    game_ids_to_sync.append(profile.game_id)

        for game_id, save_folder, sync_enabled in profiles_data:
            self._refresh_save_watch(game_id, save_folder, sync_enabled)

        if not enabled or not game_ids_to_sync:
            return

        synced_count = 0
        for game_id in game_ids_to_sync:
            if self._sync_game_now(game_id, notify=False):
                synced_count += 1

        self.notification_service.info(
            f"Sync inicial executado para {synced_count} de {len(game_ids_to_sync)} jogos configurados."
        )
        self._sync_user_state("sync global atualizado")

    def _sync_user_state(self, reason: str) -> bool:
        del reason
        self._user_state_dirty = True
        return True

    def _flush_user_state_periodic(self):
        self._flush_user_state("sincronizacao periodica do launcher", notify=True)

    def _flush_user_state(
        self,
        reason: str,
        notify: bool = False,
        force: bool = False,
    ) -> bool:
        if not force and not self._user_state_dirty:
            return True
        try:
            success = self.user_data_sync.sync_now(reason, notify=notify)
            if success:
                self._user_state_dirty = False
            return success
        except Exception as e:
            logger.error(f"Falha ao sincronizar estado do launcher: {e}")
            if notify:
                self.notification_service.warning(
                    "Nao foi possivel sincronizar os dados do launcher."
                )
            return False

    def _show_about(self):
        QMessageBox.about(
            self,
            "Sobre",
            f"<h2 style='color: #1EA1FF;'>{APP_NAME}</h2>"
            f"<p>Versao 1.0.0</p>"
            f"<p>Game Launcher profissional com sincronizacao automatica "
            f"de saves via GitHub.</p>"
            f"<p>Desenvolvido com Python + PySide6</p>",
        )

    def _update_clock(self):
        self._clock_label.setText(datetime.now().strftime("%H:%M  .  %d/%m/%Y"))

    def _refresh_library_summary(self):
        total = len(self._all_games)
        favorites = sum(1 for game in self._all_games if game.is_favorite)
        sync_state = "ON" if self.settings.get("save_sync_enabled", False) else "OFF"
        self._library_summary_label.setText(
            f"Biblioteca: {total} jogos  .  Favoritos: {favorites}  .  Sync: {sync_state}"
        )

    def _transition_background(self, game: Optional[GameData]):
        if game is None:
            target = [QColor("#0A1020"), QColor("#111B2E"), QColor("#060910")]
        else:
            target = list(_palette_for_game(game))

        if self._bg_t < 1.0:
            self._bg_from = [
                _lerp_color(self._bg_from[index], self._bg_to[index], self._bg_t)
                for index in range(3)
            ]
        else:
            self._bg_from = list(self._bg_to)

        self._bg_to = target
        self._bg_anim.stop()
        self._bg_anim.setStartValue(0.0)
        self._bg_anim.setEndValue(1.0)
        self._bg_anim.start()

    def _show_launch_overlay(self, game: GameData):
        if self._overlay_ref is not None:
            self._overlay_ref.close()

        accent = _palette_for_game(game)[0]
        overlay = _LaunchOverlay(game, accent, self)
        overlay.show()
        overlay.raise_()

        fx = QGraphicsOpacityEffect(overlay)
        overlay.setGraphicsEffect(fx)
        anim_in = QPropertyAnimation(fx, b"opacity")
        anim_in.setDuration(280)
        anim_in.setStartValue(0.0)
        anim_in.setEndValue(1.0)
        anim_in.start()

        self._overlay_ref = overlay
        self._overlay_anim_in = anim_in
        QTimer.singleShot(2200, lambda: self._close_launch_overlay(overlay))

    def _close_launch_overlay(self, overlay):
        if overlay is None:
            return
        overlay.stop()
        fx = overlay.graphicsEffect()
        if fx:
            anim_out = QPropertyAnimation(fx, b"opacity")
            anim_out.setDuration(320)
            anim_out.setStartValue(1.0)
            anim_out.setEndValue(0.0)
            anim_out.finished.connect(overlay.close)
            anim_out.start()
            self._overlay_anim_out = anim_out
        else:
            overlay.close()
        if self._overlay_ref is overlay:
            self._overlay_ref = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._bg_label.setGeometry(0, 0, self.width(), self.height())
        self._overlay.setGeometry(0, 0, self.width(), self.height())
        self._toast.setGeometry(self.width() - 380, 20, 360, 56)
        if self._overlay_ref is not None:
            self._overlay_ref.setGeometry(self.rect())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.width()
        height = self.height()
        progress = self._bg_t
        first = _lerp_color(self._bg_from[0], self._bg_to[0], progress)
        second = _lerp_color(self._bg_from[1], self._bg_to[1], progress)
        third = _lerp_color(self._bg_from[2], self._bg_to[2], progress)

        painter.fillRect(self.rect(), QColor("#060A14"))

        base_gradient = QLinearGradient(0, 0, 0, height)
        base_gradient.setColorAt(0.0, QColor("#0A1020"))
        base_gradient.setColorAt(1.0, QColor("#05070E"))
        painter.fillRect(self.rect(), base_gradient)

        painter.setPen(QPen(QColor(255, 255, 255, 5), 1))
        for x_pos in range(0, width, 64):
            painter.drawLine(x_pos, 0, x_pos, height)
        for y_pos in range(0, height, 64):
            painter.drawLine(0, y_pos, width, y_pos)

        left_glow = QRadialGradient(width * 0.18, height * 0.34, width * 0.52)
        left_glow.setColorAt(0.0, QColor(first.red(), first.green(), first.blue(), 88))
        left_glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(self.rect(), left_glow)

        right_glow = QRadialGradient(width * 0.84, height * 0.58, width * 0.42)
        right_glow.setColorAt(
            0.0, QColor(second.red(), second.green(), second.blue(), 60)
        )
        right_glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(self.rect(), right_glow)

        center_wash = QRadialGradient(width * 0.56, height * 0.24, width * 0.30)
        center_wash.setColorAt(
            0.0, QColor(third.red(), third.green(), third.blue(), 42)
        )
        center_wash.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(self.rect(), center_wash)

        vignette = QRadialGradient(width / 2, height / 2, max(width, height) * 0.74)
        vignette.setColorAt(0.0, QColor(0, 0, 0, 0))
        vignette.setColorAt(1.0, QColor(0, 0, 0, 145))
        painter.fillRect(self.rect(), vignette)
        painter.end()

        super().paintEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Right:
            self._carousel.move_selection(1)
            return
        if event.key() == Qt.Key_Left:
            self._carousel.move_selection(-1)
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self._current_game:
                self._on_play(self._current_game.id)
            return
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if self._metadata_thread and self._metadata_thread.isRunning():
            self._metadata_thread.wait(3000)
        if (
            self.settings.get("minimize_to_tray", False)
            and self._tray_available
            and not self._allow_exit
        ):
            event.ignore()
            self.hide()
            if self._tray_icon and not self._tray_message_shown:
                self._tray_icon.showMessage(
                    APP_NAME,
                    "O launcher continua em segundo plano na bandeja do sistema.",
                    QSystemTrayIcon.Information,
                    3000,
                )
                self._tray_message_shown = True
            return

        if self._tray_icon:
            self._tray_icon.hide()
        super().closeEvent(event)

    def _maybe_enrich_game_metadata(self, game: GameData, force: bool = False):
        if not self.settings.get("auto_fetch_metadata", True):
            return
        if not force and not self._game_needs_metadata(game):
            return
        if self._metadata_thread and self._metadata_thread.isRunning():
            return
        if not force and game.id in self._metadata_attempted_ids:
            return

        self._metadata_attempted_ids.add(game.id)
        self._metadata_target_game_id = game.id
        self._detail_panel.set_metadata_status(
            "Buscando metadados online para este jogo...",
            "info",
        )
        self.notification_service.info(f"Buscando metadados de {game.name}...")

        self._metadata_thread = _MetadataEnrichmentThread(
            self.metadata_service,
            self.image_service,
            game,
        )
        self._metadata_thread.metadata_ready.connect(self._on_metadata_enriched)
        self._metadata_thread.error.connect(self._on_metadata_enrichment_error)
        self._metadata_thread.finished.connect(self._on_metadata_enrichment_finished)
        self._metadata_thread.start()

    def _on_metadata_enriched(self, payload: dict):
        game_id = payload.get("game_id")
        if not game_id:
            return

        useful = any(
            payload.get(key)
            for key in [
                "description",
                "genre",
                "developer",
                "publisher",
                "release_date",
                "banner_path",
                "cover_path",
            ]
        )
        if not useful:
            if self._current_game and self._current_game.id == game_id:
                self._detail_panel.set_metadata_status(
                    "Nao encontrei detalhes adicionais para este jogo.",
                    "warning",
                )
            return

        with self.db.session() as sess:
            game = sess.get(GameModel, game_id)
            if not game:
                return

            if payload.get("description"):
                game.description = payload["description"]
            if payload.get("genre"):
                game.genre = payload["genre"]
            if payload.get("developer"):
                game.developer = payload["developer"]
            if payload.get("publisher"):
                game.publisher = payload["publisher"]
            if payload.get("release_date"):
                game.release_date = payload["release_date"]
            if payload.get("platforms"):
                game.platform = payload["platforms"]
            if payload.get("rawg_id"):
                game.rawg_id = payload["rawg_id"]
            if payload.get("banner_path"):
                game.banner_path = payload["banner_path"]
            if payload.get("cover_path"):
                game.cover_path = payload["cover_path"]
            if payload.get("background_path"):
                game.background_url = payload["background_path"]

        self.settings.set("last_selected_game_id", game_id)
        self._load_games()

        if self._current_game and self._current_game.id == game_id:
            self._detail_panel.set_metadata_status(
                "Metadados atualizados automaticamente.",
                "success",
            )
        self.notification_service.success("Metadados atualizados com sucesso.")
        self._sync_user_state(f"metadados atualizados do jogo {game_id}")

    def _on_metadata_enrichment_error(self, message: str):
        if (
            self._current_game
            and self._current_game.id == self._metadata_target_game_id
        ):
            self._detail_panel.set_metadata_status(
                f"Falha ao buscar metadados: {message}",
                "error",
            )
        self.notification_service.warning(f"Falha ao buscar metadados: {message}")

    def _on_metadata_enrichment_finished(self):
        self._metadata_target_game_id = None
        self._metadata_thread = None

    def _refresh_play_button_state(self):
        if not self._current_game:
            return
        if self.play_tracker.is_running(self._current_game.id):
            self._detail_panel.set_play_button_state("EM EXECUCAO", False)
        else:
            self._detail_panel.set_play_button_state("JOGAR", True)

    def _game_needs_metadata(self, game: GameData) -> bool:
        return any(
            not value
            for value in [
                game.description,
                game.genre,
                game.developer,
            ]
        ) or not self._resolve_display_image(game)

    def _resolve_display_image(self, game: GameData) -> str:
        for candidate in [game.banner_path, game.cover_path, game.background_url]:
            if candidate and os.path.exists(candidate):
                return candidate
        return ""
