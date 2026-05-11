"""
NexusLauncher - Ponto de entrada principal.
"""
import os
import sys

# Garante que o diretorio raiz esta no path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.constants import prepare_runtime_environment

prepare_runtime_environment()

from PySide6.QtWidgets import QApplication

from core.app import NexusApp


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("NexusLauncher")
    app.setOrganizationName("NexusStudio")

    nexus = NexusApp(app)
    app.aboutToQuit.connect(nexus.shutdown)
    nexus.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
