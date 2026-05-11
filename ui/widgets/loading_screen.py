"""
Tela de loading / splash com animação de pontos.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont


class LoadingScreen(QWidget):
    """Overlay de loading exibido sobre a janela principal."""

    def __init__(self, parent=None, message: str = "Carregando..."):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background-color: rgba(0,0,0,0.85);")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        self._label = QLabel(message)
        self._label.setFont(QFont("Segoe UI", 16))
        self._label.setStyleSheet("color: #e8c547; background: transparent;")
        self._label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._label)

        self._counter = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._base_message = message

    def start(self):
        self._counter = 0
        self._timer.start(400)
        self.show()
        self.raise_()

    def stop(self):
        self._timer.stop()
        self.hide()

    def _animate(self):
        self._counter = (self._counter + 1) % 4
        dots = "." * self._counter
        self._label.setText(f"{self._base_message}{dots}")

    def resizeEvent(self, event):
        if self.parent():
            self.setGeometry(self.parent().rect())
        super().resizeEvent(event)
