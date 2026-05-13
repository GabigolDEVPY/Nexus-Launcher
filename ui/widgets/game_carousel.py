"""
Carrossel principal de jogos em estilo hero/ribbon inspirado no mock.
Mantem a selecao e os sinais usados pela janela principal.
"""

import hashlib
import os
from typing import List, Optional

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from models.game import GameData


def _palette_for_game(game: GameData) -> tuple[QColor, QColor, QColor]:
    seed = f"{game.name}|{game.genre}|{game.platform}|{game.id}".encode("utf-8")
    digest = hashlib.sha1(seed).hexdigest()
    hue = int(digest[:2], 16) * 359 // 255
    primary = QColor.fromHsv(hue, 165, 235)
    secondary = QColor.fromHsv((hue + 18) % 360, 185, 165)
    shadow = QColor.fromHsv((hue + 36) % 360, 130, 54)
    return primary, secondary, shadow


def _year_text(game: GameData) -> str:
    if game.release_date:
        return game.release_date[:4]
    if game.added_at:
        return game.added_at.strftime("%Y")
    return game.platform[:4].upper() if game.platform else "PC"


def _art_source(game: GameData) -> tuple[QPixmap, str]:
    for kind, candidate in [
        ("cover", game.cover_path),
        ("icon", game.icon_path),
        ("banner", game.banner_path),
        ("background", game.background_url),
    ]:
        if not candidate or not os.path.exists(candidate):
            continue

        pixmap = QPixmap(candidate)
        if pixmap.isNull():
            continue
        return pixmap, kind

    return QPixmap(), ""


class GameCard(QWidget):
    clicked = Signal(int)
    card_hovered = Signal(int)

    CARD_W = 148
    CARD_H = 212
    PAD = 20

    def __init__(self, game: GameData, parent=None):
        super().__init__(parent)
        self.game = game
        self._hover_value = 0.0
        self._glow_value = 0.0
        self._palette = _palette_for_game(game)
        self._cover, self._art_kind = _art_source(game)

        self.setFixedSize(self.CARD_W + self.PAD * 2, self.CARD_H + self.PAD * 2)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        self._hover_anim = QPropertyAnimation(self, b"hoverValue")
        self._hover_anim.setDuration(180)
        self._hover_anim.setEasingCurve(QEasingCurve.OutQuad)

        self._glow_anim = QPropertyAnimation(self, b"glowValue")
        self._glow_anim.setDuration(260)
        self._glow_anim.setEasingCurve(QEasingCurve.OutCubic)

    def _get_hover(self):
        return self._hover_value

    def _set_hover(self, value):
        self._hover_value = value
        self.update()

    hoverValue = Property(float, _get_hover, _set_hover)

    def _get_glow(self):
        return self._glow_value

    def _set_glow(self, value):
        self._glow_value = value
        self.update()

    glowValue = Property(float, _get_glow, _set_glow)

    def set_selected(self, selected: bool):
        self._glow_anim.stop()
        self._glow_anim.setEndValue(1.0 if selected else 0.0)
        self._glow_anim.start()

    def enterEvent(self, event):
        self._hover_anim.stop()
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()
        self.card_hovered.emit(self.game.id)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_anim.stop()
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.game.id)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.CARD_W
        height = self.CARD_H
        center_x = self.width() / 2
        center_y = self.height() / 2

        intensity = max(self._hover_value, self._glow_value * 0.45)
        scale = 1.0 + 0.075 * intensity
        lift = -7 * self._hover_value - 3 * self._glow_value

        painter.translate(center_x, center_y + lift)
        painter.scale(scale, scale)
        painter.translate(-width / 2, -height / 2)

        card_rect = QRectF(2, 2, width - 4, height - 4)
        path = QPainterPath()
        path.addRoundedRect(card_rect, 12, 12)

        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(QRectF(6, 8, width - 8, height - 6), 12, 12)
        painter.fillPath(shadow_path, QColor(0, 0, 0, int(58 + 92 * intensity)))

        primary, secondary, shadow = self._palette
        gradient = QLinearGradient(0, 0, width * 0.32, height)
        gradient.setColorAt(0.0, primary.lighter(118))
        gradient.setColorAt(0.55, secondary)
        gradient.setColorAt(1.0, shadow)
        painter.fillPath(path, gradient)

        media_rect = QRectF(12, 12, width - 24, height - 82)
        media_path = QPainterPath()
        media_path.addRoundedRect(media_rect, 10, 10)
        painter.fillPath(media_path, QColor(5, 8, 14, 168))

        if not self._cover.isNull():
            painter.save()
            painter.setClipPath(media_path)

            target_rect = media_rect.adjusted(10, 10, -10, -10)
            if self._art_kind == "icon":
                target_rect = media_rect.adjusted(28, 24, -28, -28)

            source_ratio = self._cover.width() / max(1, self._cover.height())
            if self._art_kind in {"banner", "background"} or source_ratio > 1.18:
                target_rect = target_rect.adjusted(6, 8, -6, -12)

            scaled = self._cover.scaled(
                target_rect.size().toSize(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            draw_x = target_rect.center().x() - scaled.width() / 2
            draw_y = target_rect.center().y() - scaled.height() / 2
            if self._art_kind not in {"icon"}:
                draw_y = min(draw_y, target_rect.top() + 6)

            painter.drawPixmap(int(draw_x), int(draw_y), scaled)

            image_wash = QLinearGradient(0, media_rect.top(), 0, media_rect.bottom())
            image_wash.setColorAt(0.0, QColor(255, 255, 255, 0))
            image_wash.setColorAt(1.0, QColor(0, 0, 0, 18))
            painter.fillRect(media_rect, image_wash)
            painter.restore()
        else:
            placeholder_circle = QRectF(
                media_rect.center().x() - 34,
                media_rect.center().y() - 34,
                68,
                68,
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 24))
            painter.drawEllipse(placeholder_circle)
            painter.setPen(QColor(255, 255, 255, 210))
            painter.setFont(QFont("Segoe UI", 22, QFont.Bold))
            painter.drawText(
                placeholder_circle,
                Qt.AlignCenter,
                (self.game.name[:1] or "?").upper(),
            )

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 16))
        painter.drawEllipse(card_rect.right() - 42, card_rect.top() + 16, 34, 34)
        painter.setBrush(QColor(255, 255, 255, 10))
        painter.drawEllipse(card_rect.left() + 14, card_rect.center().y() - 12, 20, 20)
        painter.setPen(QPen(QColor(255, 255, 255, 22), 1))
        painter.drawLine(16, int(height * 0.34), width - 16, int(height * 0.34))

        painter.save()
        painter.setClipPath(path)
        bottom = QLinearGradient(0, height * 0.46, 0, height)
        bottom.setColorAt(0.0, QColor(0, 0, 0, 0))
        bottom.setColorAt(0.55, QColor(0, 0, 0, 155))
        bottom.setColorAt(1.0, QColor(0, 0, 0, 236))
        painter.fillRect(QRectF(0, height * 0.44, width, height * 0.56), bottom)
        painter.restore()

        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Segoe UI", 8, QFont.DemiBold))
        painter.drawText(
            QRectF(12, height - 62, width - 24, 52),
            Qt.AlignLeft | Qt.AlignBottom | Qt.TextWordWrap,
            self.game.name,
        )

        badge_path = QPainterPath()
        badge_path.addRoundedRect(QRectF(10, 10, 42, 18), 4, 4)
        painter.fillPath(badge_path, QColor(255, 255, 255, 32))
        painter.setPen(QColor(255, 255, 255, 200))
        painter.setFont(QFont("Segoe UI", 7))
        painter.drawText(QRectF(10, 10, 42, 18), Qt.AlignCenter, _year_text(self.game))

        genre_text = (self.game.genre or self.game.platform or "BIBLIOTECA").upper()[
            :14
        ]
        painter.setPen(QColor(255, 255, 255, 148))
        painter.setFont(QFont("Segoe UI", 7))
        painter.drawText(
            QRectF(12, height - 78, width - 24, 12), Qt.AlignLeft, genre_text
        )

        border_intensity = max(self._hover_value, self._glow_value)
        if border_intensity > 0.01:
            painter.setPen(
                QPen(QColor(255, 255, 255, int(border_intensity * 230)), 2.5)
            )
            painter.drawPath(path)

        if self._glow_value > 0.01:
            glow_path = QPainterPath()
            glow_path.addRoundedRect(
                QRectF(width * 0.24, height - 4, width * 0.52, 3.4), 1.7, 1.7
            )
            painter.fillPath(
                glow_path, QColor(255, 255, 255, int(self._glow_value * 255))
            )

        painter.end()


class GameCarousel(QWidget):
    """Ribbon horizontal com selecao por hover, clique e teclado."""

    game_selected = Signal(GameData)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: List[GameCard] = []
        self._games: List[GameData] = []
        self._selected_index = 0
        self._selected_game_id: Optional[int] = None

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent;")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setStyleSheet("background: transparent;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(48, 0, 48, 6)
        header_layout.setSpacing(12)

        self._title = QLabel("BIBLIOTECA")
        self._title.setStyleSheet(
            "color: rgba(255,255,255,0.88);"
            "font-family: 'Segoe UI';"
            "font-size: 20px;"
            "font-weight: 700;"
            "letter-spacing: 4px;"
            "background: transparent;"
        )
        header_layout.addWidget(self._title)

        self._hint = QLabel("Passe o mouse ou use as setas")
        self._hint.setStyleSheet(
            "color: rgba(255,255,255,0.38);"
            "font-family: 'Segoe UI';"
            "font-size: 11px;"
            "letter-spacing: 1px;"
            "background: transparent;"
        )
        header_layout.addWidget(self._hint)
        header_layout.addStretch()
        root.addWidget(header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFocusPolicy(Qt.NoFocus)
        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QWidget { background: transparent; }"
        )
        root.addWidget(self._scroll)

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._layout = QHBoxLayout(self._container)
        self._layout.setContentsMargins(42, 6, 42, 26)
        self._layout.setSpacing(14)
        self._layout.setAlignment(Qt.AlignLeft)
        self._scroll.setWidget(self._container)

    def set_games(self, games: List[GameData]):
        preserved_id = self._selected_game_id
        self._games = list(games)
        self._clear_cards()

        for game in self._games:
            card = GameCard(game)
            card.clicked.connect(self._on_card_clicked)
            card.card_hovered.connect(self._on_card_hovered)
            self._layout.addWidget(card)
            self._cards.append(card)

        self._layout.addStretch()

        if not self._cards:
            self._selected_index = 0
            self._selected_game_id = None
            return

        target_index = 0
        if preserved_id is not None:
            for index, card in enumerate(self._cards):
                if card.game.id == preserved_id:
                    target_index = index
                    break

        self._select_card(target_index, emit_signal=False)

    def select_game_by_id(self, game_id: int, emit_signal: bool = False):
        for index, card in enumerate(self._cards):
            if card.game.id == game_id:
                self._select_card(index, emit_signal=emit_signal)
                return True
        return False

    def move_selection(self, offset: int):
        if not self._cards:
            return False
        target = max(0, min(self._selected_index + offset, len(self._cards) - 1))
        if target == self._selected_index:
            return False
        self._select_card(target, emit_signal=True)
        return True

    def current_game(self) -> Optional[GameData]:
        if not self._cards:
            return None
        return self._cards[self._selected_index].game

    def activate_current(self):
        current = self.current_game()
        if current:
            self.game_selected.emit(current)

    def _clear_cards(self):
        self._cards.clear()
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _on_card_hovered(self, game_id: int):
        self.select_game_by_id(game_id, emit_signal=True)

    def _on_card_clicked(self, game_id: int):
        self.select_game_by_id(game_id, emit_signal=True)

    def _select_card(self, index: int, emit_signal: bool):
        if not self._cards or index < 0 or index >= len(self._cards):
            return

        for card in self._cards:
            card.set_selected(False)

        self._selected_index = index
        selected = self._cards[index]
        self._selected_game_id = selected.game.id
        selected.set_selected(True)
        self._scroll.ensureWidgetVisible(selected, 110, 0)

        if emit_signal:
            self.game_selected.emit(selected.game)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Right:
            self.move_selection(1)
            return
        if event.key() == Qt.Key_Left:
            self.move_selection(-1)
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.activate_current()
            return
        super().keyPressEvent(event)
