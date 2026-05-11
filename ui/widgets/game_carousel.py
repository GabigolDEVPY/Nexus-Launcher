"""
Carrossel de jogos estilo PS4 — lista horizontal com scroll suave e seleção visual.
"""
from typing import List, Optional
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QVBoxLayout, QScrollArea, QFrame,
)
from PySide6.QtCore import Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPixmap, QFont, QPainter, QColor, QPen, QLinearGradient

from models.game import GameData
from utils.cache_manager import CacheManager


class GameCard(QFrame):
    """Card individual de jogo no carrossel."""

    clicked = Signal(int)  # game_id

    CARD_W = 200
    CARD_H = 280

    def __init__(self, game: GameData, parent=None):
        super().__init__(parent)
        self.game = game
        self._selected = False
        self.setFixedSize(self.CARD_W, self.CARD_H)
        self.setCursor(Qt.PointingHandCursor)

        self.setStyleSheet("""
            QFrame {
                border-radius: 10px;
                background-color: #141414;
                border: 2px solid transparent;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Imagem do jogo
        self._image_label = QLabel()
        self._image_label.setFixedSize(self.CARD_W, 200)
        self._image_label.setAlignment(Qt.AlignCenter)
        self._image_label.setStyleSheet(
            "border-top-left-radius: 10px; border-top-right-radius: 10px;"
        )
        layout.addWidget(self._image_label)

        # Informações
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(10, 8, 10, 8)
        info_layout.setSpacing(2)

        self._name_label = QLabel(game.name)
        self._name_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self._name_label.setStyleSheet("color: #fff; background: transparent;")
        self._name_label.setWordWrap(True)
        info_layout.addWidget(self._name_label)

        self._genre_label = QLabel(game.genre[:30] if game.genre else "")
        self._genre_label.setStyleSheet(
            "color: #e8c547; font-size: 10px; letter-spacing: 1px; background: transparent;"
        )
        info_layout.addWidget(self._genre_label)

        layout.addLayout(info_layout)
        layout.addStretch()

        self._load_image()

    def _load_image(self):
        cache = CacheManager()
        key = f"cover_{self.game.id}"
        path = cache.get_image_path(key)
        if not path:
            path = self.game.cover_path or self.game.banner_path

        if path:
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    self.CARD_W, 200,
                    Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation,
                )
                # Crop to fit
                x = (scaled.width() - self.CARD_W) // 2
                y = (scaled.height() - 200) // 2
                cropped = scaled.copy(x, y, self.CARD_W, 200)
                self._image_label.setPixmap(cropped)
                return

        # Placeholder
        self._image_label.setText("🎮")
        self._image_label.setStyleSheet(
            "font-size: 48px; background: #1a1a1a; "
            "border-top-left-radius: 10px; border-top-right-radius: 10px;"
        )

    def set_selected(self, selected: bool):
        self._selected = selected
        if selected:
            self.setStyleSheet("""
                QFrame {
                    border-radius: 10px;
                    background-color: #1a1a1a;
                    border: 2px solid #e8c547;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame {
                    border-radius: 10px;
                    background-color: #141414;
                    border: 2px solid transparent;
                }
            """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.game.id)
        super().mousePressEvent(event)


class GameCarousel(QWidget):
    """Carrossel horizontal de jogos com scroll suave."""

    game_selected = Signal(GameData)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: List[GameCard] = []
        self._selected_index = 0

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Título da seção
        self._title = QLabel("BIBLIOTECA")
        self._title.setObjectName("sidebarTitle")
        self._title.setStyleSheet(
            "font-family: 'Bebas Neue', 'Impact', sans-serif; "
            "font-size: 20px; color: #e8c547; letter-spacing: 4px; "
            "padding: 12px 30px; background: transparent;"
        )
        main_layout.addWidget(self._title)

        # Scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        main_layout.addWidget(self._scroll)

        # Container dos cards
        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._h_layout = QHBoxLayout(self._container)
        self._h_layout.setContentsMargins(30, 10, 30, 20)
        self._h_layout.setSpacing(16)
        self._h_layout.setAlignment(Qt.AlignLeft)
        self._scroll.setWidget(self._container)

    def set_games(self, games: List[GameData]):
        """Popula o carrossel com uma lista de jogos."""
        # Limpa cards existentes
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()

        for game in games:
            card = GameCard(game)
            card.clicked.connect(self._on_card_clicked)
            self._h_layout.addWidget(card)
            self._cards.append(card)

        if self._cards:
            self._select_card(0)

    def _on_card_clicked(self, game_id: int):
        for i, card in enumerate(self._cards):
            if card.game.id == game_id:
                self._select_card(i)
                break

    def _select_card(self, index: int):
        if not self._cards or index < 0 or index >= len(self._cards):
            return

        # Deselecta todos
        for card in self._cards:
            card.set_selected(False)

        # Seleciona o atual
        self._selected_index = index
        card = self._cards[index]
        card.set_selected(True)

        # Scroll suave até o card
        self._scroll.ensureWidgetVisible(card, 100, 0)

        # Emite sinal
        self.game_selected.emit(card.game)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Right:
            self._select_card(min(self._selected_index + 1, len(self._cards) - 1))
        elif event.key() == Qt.Key_Left:
            self._select_card(max(self._selected_index - 1, 0))
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self._cards:
                self.game_selected.emit(self._cards[self._selected_index].game)
        else:
            super().keyPressEvent(event)
