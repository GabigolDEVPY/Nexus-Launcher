"""
Widget de notificação toast — aparece no canto superior direito e desaparece.
"""
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QGraphicsOpacityEffect
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QPoint
from PySide6.QtGui import QColor


_COLORS = {
    "info": ("#1a1a2e", "#5b8def"),
    "success": ("#0d2818", "#4ade80"),
    "warning": ("#2d2206", "#facc15"),
    "error": ("#2d0a0a", "#f87171"),
}


class ToastWidget(QWidget):
    """Notificação flutuante animada."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(360)
        self.setFixedHeight(56)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(16, 8, 16, 8)

        self._label = QLabel()
        self._label.setWordWrap(True)
        self._label.setStyleSheet("font-size: 13px; font-weight: 600;")
        self._layout.addWidget(self._label)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._fade_anim = None
        self.hide()

    def show_toast(self, message: str, level: str = "info"):
        bg, border = _COLORS.get(level, _COLORS["info"])
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 8px;
            }}
        """)
        self._label.setText(message)
        self._label.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {border}; background: transparent;")

        # Posiciona no canto superior direito do parent
        if self.parent():
            pw = self.parent().width()
            self.move(pw - self.width() - 20, 20)

        self._opacity_effect.setOpacity(1.0)
        self.show()
        self.raise_()
        self._timer.start(3000)

    def _fade_out(self):
        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_anim.setDuration(400)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.finished.connect(self.hide)
        self._fade_anim.start()
