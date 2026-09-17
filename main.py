"""
NexusLauncher - Ponto de entrada principal.
"""

import os
import sys

# Garante que o diretorio raiz esta no path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.constants import prepare_runtime_environment

prepare_runtime_environment()

from PySide6.QtWidgets import QApplication  # noqa: E402

from core.app import NexusApp  # noqa: E402
from core.constants import APP_NAME  # noqa: E402
from core.single_instance import (  # noqa: E402
    SingleInstanceGuard,
    show_already_running_message,
)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("NexusStudio")
    app.setQuitOnLastWindowClosed(False)

    guard = SingleInstanceGuard(app)
    if guard.is_already_running():
        show_already_running_message()
        return 0

    nexus = NexusApp(app, guard)
    app.aboutToQuit.connect(nexus.shutdown)
    nexus.start()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
