"""
Serviço global de notificações — emite sinais Qt para toasts na UI.
"""
from PySide6.QtCore import QObject, Signal


class NotificationService(QObject):
    """Singleton de notificações. Conecte os sinais ao toast_widget."""

    toast_requested = Signal(str, str)  # (message, level: 'info'|'success'|'warning'|'error')

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        super().__init__()
        self._initialized = True

    def info(self, message: str):
        self.toast_requested.emit(message, "info")

    def success(self, message: str):
        self.toast_requested.emit(message, "success")

    def warning(self, message: str):
        self.toast_requested.emit(message, "warning")

    def error(self, message: str):
        self.toast_requested.emit(message, "error")
