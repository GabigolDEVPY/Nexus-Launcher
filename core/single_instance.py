"""
Garante que apenas uma instancia do launcher rode por maquina.
A segunda instancia pede para a primeira trazer a janela para frente e sai.
"""

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from core.constants import APP_NAME


class SingleInstanceGuard(QObject):
    """Guarda de instancia unica baseada em servidor local do Qt."""

    activate_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._server: QLocalServer | None = None

    @property
    def server_name(self) -> str:
        return f"{APP_NAME}-SingleInstance"

    def is_already_running(self) -> bool:
        """Tenta falar com a instancia existente; True se ela respondeu."""
        socket = QLocalSocket()
        socket.connectToServer(self.server_name)
        already_running = socket.waitForConnected(500)

        if already_running:
            socket.write(b"activate\n")
            socket.flush()
            socket.waitForBytesWritten(500)
            socket.disconnectFromServer()

        return already_running

    def start_listening(self) -> bool:
        """Comeca a escutar pedidos de ativacao de novas instancias."""
        QLocalServer.removeServer(self.server_name)
        self._server = QLocalServer()
        self._server.newConnection.connect(self._on_new_connection)
        if not self._server.listen(self.server_name):
            self._server = None
            return False
        return True

    def _on_new_connection(self):
        socket = self._server.nextPendingConnection()
        if socket:
            socket.readyRead.connect(self._emit_activate)
            if socket.bytesAvailable():
                self._emit_activate()

    def _emit_activate(self):
        self.activate_requested.emit()


def show_already_running_message():
    """Mensagem nativa exibida quando a ativacao via IPC nao e possivel."""
    if QApplication.instance():
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information(
            None,
            APP_NAME,
            "O NexusLauncher ja esta em execucao.\n"
            "Confira a bandeja do sistema (indice ao lado do relogio).",
        )
