"""
Painel de detalhes do jogo exibido quando um jogo e selecionado no carrossel.
Mostra banner, descricao, play button, horas jogadas e status de sync.
"""
import os

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from models.game import GameData
from utils.helpers import format_playtime


class GameDetailPanel(QWidget):
    """Painel lateral que mostra detalhes do jogo selecionado."""

    play_requested = Signal(int)
    favorite_toggled = Signal(int)
    settings_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_game: GameData | None = None

        self.setStyleSheet("background: transparent;")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 40, 40, 40)
        main_layout.setSpacing(0)

        self._bg_label = QLabel(self)
        self._bg_label.setGeometry(0, 0, 900, 450)
        self._bg_label.setScaledContents(True)
        self._bg_label.setStyleSheet("background: transparent;")
        self._bg_label.lower()

        self._overlay = QFrame(self)
        self._overlay.setGeometry(0, 0, 900, 450)
        self._overlay.setStyleSheet(
            """
            QFrame {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(13,13,13,100),
                    stop:0.4 rgba(13,13,13,180),
                    stop:1 rgba(13,13,13,255)
                );
            }
            """
        )
        self._overlay.lower()
        self._bg_label.raise_()
        self._overlay.raise_()

        self._content = QWidget(self)
        self._content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 120, 0, 0)
        content_layout.setSpacing(12)

        self._genre_label = QLabel()
        self._genre_label.setObjectName("gameGenre")
        content_layout.addWidget(self._genre_label)

        self._title_label = QLabel()
        self._title_label.setObjectName("gameTitle")
        self._title_label.setWordWrap(True)
        content_layout.addWidget(self._title_label)

        self._dev_label = QLabel()
        self._dev_label.setStyleSheet(
            "color: #777; font-size: 12px; background: transparent;"
        )
        content_layout.addWidget(self._dev_label)

        self._meta_status_label = QLabel("")
        self._meta_status_label.setWordWrap(True)
        self._meta_status_label.setStyleSheet(
            "color: #9aa4b2; font-size: 12px; background: transparent;"
        )
        self._meta_status_label.hide()
        content_layout.addWidget(self._meta_status_label)

        self._desc_label = QLabel()
        self._desc_label.setObjectName("gameDescription")
        self._desc_label.setWordWrap(True)
        self._desc_label.setMaximumHeight(80)
        content_layout.addWidget(self._desc_label)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(30)

        playtime_container = QVBoxLayout()
        pt_title = QLabel("TEMPO DE JOGO")
        pt_title.setStyleSheet(
            "color: #555; font-size: 10px; letter-spacing: 2px; background: transparent;"
        )
        playtime_container.addWidget(pt_title)
        self._playtime_label = QLabel("0h 0min")
        self._playtime_label.setObjectName("playtimeLabel")
        self._playtime_label.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #e8e4dc; background: transparent;"
        )
        playtime_container.addWidget(self._playtime_label)
        stats_row.addLayout(playtime_container)

        last_container = QVBoxLayout()
        lt_title = QLabel("ULTIMA SESSAO")
        lt_title.setStyleSheet(
            "color: #555; font-size: 10px; letter-spacing: 2px; background: transparent;"
        )
        last_container.addWidget(lt_title)
        self._last_played_label = QLabel("Nunca")
        self._last_played_label.setStyleSheet(
            "font-size: 14px; color: #aaa; background: transparent;"
        )
        last_container.addWidget(self._last_played_label)
        stats_row.addLayout(last_container)

        sync_container = QVBoxLayout()
        sy_title = QLabel("SAVE SYNC")
        sy_title.setStyleSheet(
            "color: #555; font-size: 10px; letter-spacing: 2px; background: transparent;"
        )
        sync_container.addWidget(sy_title)
        self._sync_label = QLabel("Nao configurado")
        self._sync_label.setObjectName("syncStatusLabel")
        self._sync_label.setStyleSheet(
            "font-size: 13px; color: #5a9; background: transparent;"
        )
        sync_container.addWidget(self._sync_label)
        stats_row.addLayout(sync_container)

        stats_row.addStretch()
        content_layout.addLayout(stats_row)
        content_layout.addSpacing(20)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._play_btn = QPushButton("JOGAR")
        self._play_btn.setObjectName("playButton")
        self._play_btn.setMinimumHeight(52)
        self._play_btn.setMinimumWidth(220)
        self._play_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #22c55e;
                color: #08110b;
                border: 2px solid #16a34a;
                border-radius: 8px;
                padding: 14px 48px;
                font-size: 16px;
                font-weight: bold;
                letter-spacing: 2px;
            }
            QPushButton:hover {
                background-color: #4ade80;
                border-color: #22c55e;
            }
            QPushButton:pressed {
                background-color: #16a34a;
                color: #f7fff9;
            }
            QPushButton:disabled {
                background-color: #14532d;
                color: #d1fae5;
                border: 2px solid #166534;
            }
            """
        )
        self._play_btn.clicked.connect(self._on_play)
        btn_row.addWidget(self._play_btn)

        self._fav_btn = QPushButton("☆")
        self._fav_btn.setObjectName("favoriteButton")
        self._fav_btn.setFixedSize(44, 44)
        self._fav_btn.clicked.connect(self._on_toggle_favorite)
        btn_row.addWidget(self._fav_btn)

        self._config_btn = QPushButton("CONFIG")
        self._config_btn.setToolTip(
            "Editar executavel, pasta de saves e sincronizacao deste jogo"
        )
        self._config_btn.clicked.connect(self._on_config)
        btn_row.addWidget(self._config_btn)

        btn_row.addStretch()
        content_layout.addLayout(btn_row)
        content_layout.addStretch()

        main_layout.addWidget(self._content)
        self._bg_label.lower()
        self._overlay.lower()
        self._content.raise_()

        self._fade_timer = QTimer(self)
        self._fade_timer.setSingleShot(True)
        self._fade_timer.timeout.connect(self._animate_in)

    def set_game(self, game: GameData):
        self._current_game = game
        self._title_label.setText(game.name.upper())
        self._genre_label.setText(game.genre.upper() if game.genre else "SEM GENERO")
        self._dev_label.setText(game.developer or "")
        self._desc_label.setText(
            game.description[:300] + "..."
            if len(game.description) > 300
            else game.description or "Sem descricao disponivel."
        )
        self._playtime_label.setText(format_playtime(game.total_playtime_seconds))
        self._last_played_label.setText(game.last_played_formatted)
        self._fav_btn.setText("★" if game.is_favorite else "☆")
        self.set_play_button_state("JOGAR", True)
        self.set_metadata_status("")

        bg_path = self._resolve_background_path(game)
        if bg_path:
            pixmap = QPixmap(bg_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    self.width(),
                    450,
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation,
                )
                self._bg_label.setPixmap(scaled)
        else:
            self._bg_label.clear()

        self._fade_timer.start(50)

    def update_sync_status(self, synced: bool, info: str = ""):
        if synced:
            self._sync_label.setText(f"Sincronizado - {info}")
            self._sync_label.setStyleSheet(
                "font-size: 13px; color: #4ade80; background: transparent;"
            )
        else:
            self._sync_label.setText(info or "Nao sincronizado")
            self._sync_label.setStyleSheet(
                "font-size: 13px; color: #f87171; background: transparent;"
            )

    def set_metadata_status(self, message: str = "", level: str = "info"):
        colors = {
            "info": "#9aa4b2",
            "success": "#4ade80",
            "warning": "#facc15",
            "error": "#f87171",
        }
        if message:
            self._meta_status_label.setText(message)
            self._meta_status_label.setStyleSheet(
                f"color: {colors.get(level, colors['info'])}; "
                "font-size: 12px; background: transparent;"
            )
            self._meta_status_label.show()
        else:
            self._meta_status_label.hide()

    def set_play_button_state(self, text: str, enabled: bool = True):
        self._play_btn.setText(text)
        self._play_btn.setEnabled(enabled)

    def update_playtime(self, total_seconds: float):
        self._playtime_label.setText(format_playtime(total_seconds))

    def _on_play(self):
        if self._current_game:
            self.play_requested.emit(self._current_game.id)

    def _on_toggle_favorite(self):
        if self._current_game:
            self.favorite_toggled.emit(self._current_game.id)

    def _on_config(self):
        if self._current_game:
            self.settings_requested.emit(self._current_game.id)

    def _animate_in(self):
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(300)
        self._fade_anim.setStartValue(0.7)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._bg_label.setGeometry(0, 0, self.width(), 450)
        self._overlay.setGeometry(0, 0, self.width(), 450)
        self._content.raise_()

    def _resolve_background_path(self, game: GameData) -> str:
        for candidate in [game.banner_path, game.cover_path, game.background_url]:
            if candidate and os.path.exists(candidate):
                return candidate
        return ""
