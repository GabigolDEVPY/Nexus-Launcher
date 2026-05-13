"""
Painel principal do jogo selecionado em estilo hero.
Mantem os mesmos sinais e metodos consumidos pela MainWindow.
"""

import os

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
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


def _art_path(game: GameData) -> str:
    for candidate in [game.banner_path, game.cover_path, game.background_url]:
        if candidate and os.path.exists(candidate):
            return candidate
    return ""


class PlayButton(QWidget):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover_value = 0.0
        self._label = "JOGAR"
        self._text_font = QFont("Segoe UI", 12, QFont.Bold)

        self.setFixedSize(208, 54)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        self._anim = QPropertyAnimation(self, b"hoverValue")
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.OutQuad)

    def _get_hover(self):
        return self._hover_value

    def _set_hover(self, value):
        self._hover_value = value
        self.update()

    hoverValue = Property(float, _get_hover, _set_hover)

    def set_label(self, text: str):
        self._label = text
        self.update()

    def enterEvent(self, event):
        if self.isEnabled():
            self._anim.stop()
            self._anim.setEndValue(1.0)
            self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._anim.stop()
        self._anim.setEndValue(0.0)
        self._anim.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if self.isEnabled() and event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.width()
        height = self.height()
        rect = QRectF(1, 1, width - 2, height - 2)
        path = QPainterPath()
        path.addRoundedRect(rect, height / 2, height / 2)

        enabled = self.isEnabled()
        if enabled:
            base = QColor("#0070D1")
            hover = QColor("#2A9CFF")
            fill = QColor(
                int(base.red() + (hover.red() - base.red()) * self._hover_value),
                int(base.green() + (hover.green() - base.green()) * self._hover_value),
                int(base.blue() + (hover.blue() - base.blue()) * self._hover_value),
            )
            edge = QColor(255, 255, 255, int(46 + 85 * self._hover_value))
        else:
            fill = QColor("#25445E")
            edge = QColor(255, 255, 255, 36)

        if enabled and self._hover_value > 0.01:
            glow = QPainterPath()
            glow.addRoundedRect(
                QRectF(-4, -4, width + 8, height + 8),
                (height + 8) / 2,
                (height + 8) / 2,
            )
            painter.fillPath(glow, QColor(0, 112, 209, int(self._hover_value * 44)))

        painter.fillPath(path, fill)
        painter.setPen(QPen(edge, 1.1))
        painter.drawPath(path)

        triangle_size = 7
        center_y = height / 2
        left_x = width * 0.22
        triangle = QPolygonF(
            [
                QPointF(left_x - triangle_size, center_y - triangle_size),
                QPointF(left_x + triangle_size, center_y),
                QPointF(left_x - triangle_size, center_y + triangle_size),
            ]
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#FFFFFF" if enabled else "#C8D6E5"))
        painter.drawPolygon(triangle)

        painter.setPen(QColor("#FFFFFF" if enabled else "#D7E0E9"))
        painter.setFont(self._text_font)
        painter.drawText(
            QRectF(width * 0.31, 0, width * 0.6, height),
            Qt.AlignLeft | Qt.AlignVCenter,
            self._label,
        )
        painter.end()


class GameDetailPanel(QWidget):
    """Hero panel do jogo selecionado."""

    play_requested = Signal(int)
    favorite_toggled = Signal(int)
    settings_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_game: GameData | None = None
        self._art_source = QPixmap()

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent;")

        # -- main layout (text on left, art is manually positioned) --
        self._root_layout = QVBoxLayout(self)
        self._root_layout.setContentsMargins(56, 20, 56, 10)
        self._root_layout.setSpacing(0)

        # Art frame (manually positioned at right side)
        self._art_frame = QFrame(self)
        self._art_frame.setStyleSheet(
            """
            QFrame {
                background: rgba(4, 6, 10, 0.95);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 28px;
            }
            """
        )

        self._art_label = QLabel(self._art_frame)
        self._art_label.setAlignment(Qt.AlignCenter)
        self._art_label.setStyleSheet(
            "background: rgba(0,0,0,0.92);border: none;border-radius: 20px;"
        )

        self._art_overlay = QFrame(self._art_frame)
        self._art_overlay.setStyleSheet(
            """
            QFrame {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255,255,255,0),
                    stop:0.55 rgba(8,12,24,12),
                    stop:1 rgba(0,0,0,110)
                );
                border-radius: 28px;
            }
            """
        )
        self._art_overlay.setAttribute(Qt.WA_TransparentForMouseEvents)

        # Text content widget — uses QFrame so it draws its own background,
        # guaranteeing the dark card always matches the content size exactly.
        self._content = QFrame(self)
        self._content.setObjectName("DetailContent")
        self._content.setStyleSheet(
            """
            QFrame#DetailContent {
                background: qlineargradient(
                    x1:0, y1:0, x2:0.9, y2:1,
                    stop:0 rgba(2,3,6,246),
                    stop:0.55 rgba(6,8,14,236),
                    stop:1 rgba(10,14,22,226)
                );
                border: 1px solid rgba(255,255,255,0.07);
                border-radius: 28px;
            }
            """
        )
        content = QVBoxLayout(self._content)
        content.setContentsMargins(34, 30, 34, 24)
        content.setSpacing(10)

        self._eyebrow_label = QLabel("SELECIONADO")
        self._eyebrow_label.setStyleSheet(
            "color: rgba(255,255,255,0.48);"
            "font-family: 'Segoe UI';"
            "font-size: 11px;"
            "font-weight: 600;"
            "letter-spacing: 3px;"
            "background: transparent;"
        )
        content.addWidget(self._eyebrow_label)

        self._title_label = QLabel()
        self._title_label.setWordWrap(True)
        self._title_label.setStyleSheet(
            "color: white;"
            "font-family: 'Segoe UI';"
            "font-size: 34px;"
            "font-weight: 700;"
            "background: transparent;"
        )
        content.addWidget(self._title_label)

        self._subtitle_label = QLabel()
        self._subtitle_label.setStyleSheet(
            "color: rgba(255,255,255,0.54);"
            "font-family: 'Segoe UI';"
            "font-size: 13px;"
            "background: transparent;"
        )
        content.addWidget(self._subtitle_label)

        self._meta_status_label = QLabel("")
        self._meta_status_label.setWordWrap(True)
        self._meta_status_label.setStyleSheet(
            "color: #9AA4B2;"
            "font-family: 'Segoe UI';"
            "font-size: 12px;"
            "background: transparent;"
        )
        self._meta_status_label.hide()
        content.addWidget(self._meta_status_label)

        self._description_label = QLabel()
        self._description_label.setWordWrap(True)
        self._description_label.setMaximumWidth(540)
        self._description_label.setStyleSheet(
            "color: rgba(255,255,255,0.76);"
            "font-family: 'Segoe UI';"
            "font-size: 13px;"
            "line-height: 1.4;"
            "background: transparent;"
        )
        content.addWidget(self._description_label)

        content.addSpacing(10)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(28)
        stats_row.setContentsMargins(0, 0, 0, 0)

        self._playtime_value = self._create_stat_block(stats_row, "TEMPO DE JOGO")
        self._last_played_value = self._create_stat_block(stats_row, "ULTIMA SESSAO")
        self._platform_value = self._create_stat_block(stats_row, "PLATAFORMA")
        self._sync_value = self._create_stat_block(stats_row, "SAVE SYNC")
        stats_row.addStretch()

        content.addLayout(stats_row)
        content.addSpacing(16)

        actions = QHBoxLayout()
        actions.setSpacing(12)
        actions.setContentsMargins(0, 0, 0, 0)

        self._play_btn = PlayButton()
        self._play_btn.setFont(self.font())
        self._play_btn.clicked.connect(self._on_play)
        actions.addWidget(self._play_btn)

        self._fav_btn = QPushButton("FAVORITO")
        self._fav_btn.setFixedSize(138, 54)
        self._fav_btn.clicked.connect(self._on_toggle_favorite)
        actions.addWidget(self._fav_btn)

        self._config_btn = QPushButton("CONFIG")
        self._config_btn.setToolTip(
            "Editar executavel, pasta de saves e sync deste jogo"
        )
        self._config_btn.setFixedSize(130, 54)
        self._config_btn.clicked.connect(self._on_config)
        self._config_btn.setStyleSheet(
            """
            QPushButton {
                background: rgba(255,255,255,0.08);
                color: white;
                border: 1px solid rgba(255,255,255,0.16);
                border-radius: 27px;
                font-family: 'Segoe UI';
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 2px;
                padding: 0 22px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.15);
                border-color: rgba(255,255,255,0.28);
            }
            QPushButton:pressed {
                background: rgba(255,255,255,0.22);
            }
            """
        )
        actions.addWidget(self._config_btn)
        actions.addStretch()

        content.addLayout(actions)
        content.addStretch()
        self._content.setMaximumWidth(760)
        self._root_layout.addWidget(self._content, 0, Qt.AlignLeft | Qt.AlignVCenter)

        # No separate opacity effect on the art frame — the parent panel
        # already has one applied by MainWindow (_fade_fx). Nesting two
        # QGraphicsOpacityEffects causes the art to flicker/disappear on
        # Windows due to a known Qt compositing issue.

        self._set_favorite_state(False)
        self._set_sync_style("Checando...", "#9AA4B2")

    def _create_stat_block(self, layout: QHBoxLayout, title: str) -> QLabel:
        block = QVBoxLayout()
        block.setSpacing(2)
        block.setContentsMargins(0, 0, 0, 0)

        label = QLabel(title)
        label.setStyleSheet(
            "color: rgba(255,255,255,0.32);"
            "font-family: 'Segoe UI';"
            "font-size: 10px;"
            "font-weight: 600;"
            "letter-spacing: 2px;"
            "background: transparent;"
        )
        block.addWidget(label)

        value = QLabel("-")
        value.setStyleSheet(
            "color: rgba(255,255,255,0.82);"
            "font-family: 'Segoe UI';"
            "font-size: 15px;"
            "font-weight: 600;"
            "background: transparent;"
        )
        block.addWidget(value)
        layout.addLayout(block)
        return value

    def set_game(self, game: GameData):
        self._current_game = game
        self._title_label.setText(game.name)

        subtitle_parts = []
        if game.genre:
            subtitle_parts.append(game.genre)
        if game.developer:
            subtitle_parts.append(game.developer)
        elif game.publisher:
            subtitle_parts.append(game.publisher)
        if game.release_date:
            subtitle_parts.append(game.release_date[:4])
        elif game.platform:
            subtitle_parts.append(game.platform)
        self._subtitle_label.setText(
            "  .  ".join(subtitle_parts) if subtitle_parts else "Biblioteca Nexus"
        )

        description = game.description or "Sem descricao disponivel para este jogo."
        if len(description) > 320:
            description = description[:317].rstrip() + "..."
        self._description_label.setText(description)

        self._playtime_value.setText(format_playtime(game.total_playtime_seconds))
        self._last_played_value.setText(game.last_played_formatted)
        self._platform_value.setText(game.platform or "PC")
        self._set_sync_style("Checando...", "#9AA4B2")
        self._set_favorite_state(game.is_favorite)
        self.set_play_button_state("JOGAR", True)
        self.set_metadata_status("")

        art_path = _art_path(game)
        if art_path:
            pixmap = QPixmap(art_path)
            if not pixmap.isNull():
                self._art_source = pixmap
                self._art_frame.show()
                self._refresh_art_pixmap()
            else:
                self._art_source = QPixmap()
                self._art_label.clear()
                self._art_frame.hide()
        else:
            self._art_source = QPixmap()
            self._art_label.clear()
            self._art_frame.hide()

    def update_sync_status(self, synced: bool, info: str = ""):
        if synced:
            self._set_sync_style(info or "Sincronizado", "#5AD39A")
        else:
            self._set_sync_style(info or "Nao sincronizado", "#F18A8A")

    def set_metadata_status(self, message: str = "", level: str = "info"):
        colors = {
            "info": "#9AA4B2",
            "success": "#5AD39A",
            "warning": "#F3C867",
            "error": "#F18A8A",
        }
        if message:
            self._meta_status_label.setText(message)
            self._meta_status_label.setStyleSheet(
                f"color: {colors.get(level, colors['info'])};"
                "font-family: 'Segoe UI';"
                "font-size: 12px;"
                "background: transparent;"
            )
            self._meta_status_label.show()
        else:
            self._meta_status_label.hide()

    def set_play_button_state(self, text: str, enabled: bool = True):
        self._play_btn.setEnabled(enabled)
        self._play_btn.set_label(text)
        self._play_btn.setCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor)

    def update_playtime(self, total_seconds: float):
        self._playtime_value.setText(format_playtime(total_seconds))

    def _set_favorite_state(self, is_favorite: bool):
        if is_favorite:
            self._fav_btn.setStyleSheet(
                """
                QPushButton {
                    background: rgba(255,255,255,0.16);
                    color: white;
                    border: 1px solid rgba(255,255,255,0.28);
                    border-radius: 27px;
                    font-family: 'Segoe UI';
                    font-size: 11px;
                    font-weight: 700;
                    letter-spacing: 2px;
                    padding: 0 20px;
                }
                QPushButton:hover { background: rgba(255,255,255,0.22); }
                QPushButton:pressed { background: rgba(255,255,255,0.28); }
                """
            )
        else:
            self._fav_btn.setStyleSheet(
                """
                QPushButton {
                    background: rgba(255,255,255,0.07);
                    color: rgba(255,255,255,0.86);
                    border: 1px solid rgba(255,255,255,0.14);
                    border-radius: 27px;
                    font-family: 'Segoe UI';
                    font-size: 11px;
                    font-weight: 700;
                    letter-spacing: 2px;
                    padding: 0 20px;
                }
                QPushButton:hover {
                    background: rgba(255,255,255,0.14);
                    border-color: rgba(255,255,255,0.24);
                }
                QPushButton:pressed { background: rgba(255,255,255,0.20); }
                """
            )

    def _set_sync_style(self, text: str, color: str):
        self._sync_value.setText(text)
        self._sync_value.setStyleSheet(
            f"color: {color};"
            "font-family: 'Segoe UI';"
            "font-size: 14px;"
            "font-weight: 600;"
            "background: transparent;"
        )

    def _refresh_art_pixmap(self):
        if (
            self._art_source.isNull()
            or self._art_label.width() <= 0
            or self._art_label.height() <= 0
        ):
            return

        scaled = self._art_source.scaled(
            self._art_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self._art_label.setPixmap(scaled)

    def _on_play(self):
        if self._current_game:
            self.play_requested.emit(self._current_game.id)

    def _on_toggle_favorite(self):
        if self._current_game:
            self.favorite_toggled.emit(self._current_game.id)

    def _on_config(self):
        if self._current_game:
            self.settings_requested.emit(self._current_game.id)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        art_width = max(250, min(390, int(self.width() * 0.28)))
        art_height = max(250, min(self.height() - 26, int(self.height() * 0.78)))
        art_x = self.width() - art_width - 30
        art_y = max(12, (self.height() - art_height) // 2)

        self._art_frame.setGeometry(art_x, art_y, art_width, art_height)
        self._art_label.setGeometry(16, 16, art_width - 32, art_height - 32)
        self._art_overlay.setGeometry(0, 0, art_width, art_height)

        right_margin = art_width + 64
        content_width = max(420, self.width() - right_margin - 80)
        self._content.setMaximumWidth(min(760, content_width))
        self._root_layout.setContentsMargins(56, 20, right_margin, 10)

        self._refresh_art_pixmap()
