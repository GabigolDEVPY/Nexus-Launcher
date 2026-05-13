"""
Servico para registrar o launcher na inicializacao do Windows.
"""

import os
import sys

from core.constants import BASE_DIR
from utils.logger import get_logger

logger = get_logger("StartupService")


class StartupService:
    """Gerencia a entrada do NexusLauncher no startup do Windows."""

    RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
    VALUE_NAME = "NexusLauncher"

    def __init__(self, settings):
        self.settings = settings

    @property
    def supported(self) -> bool:
        return os.name == "nt"

    def is_enabled(self) -> bool:
        if not self.supported:
            return False

        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY_PATH) as key:
                winreg.QueryValueEx(key, self.VALUE_NAME)
                return True
        except FileNotFoundError:
            return False
        except OSError as e:
            logger.warning(f"Falha ao ler startup do Windows: {e}")
            return False

    def set_enabled(self, enabled: bool):
        if not self.supported:
            if enabled:
                raise RuntimeError(
                    "Iniciar com o Windows so esta disponivel no Windows."
                )
            return

        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            self.RUN_KEY_PATH,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            if enabled:
                command = self.build_launch_command()
                winreg.SetValueEx(key, self.VALUE_NAME, 0, winreg.REG_SZ, command)
                logger.info("Startup com Windows habilitado")
            else:
                try:
                    winreg.DeleteValue(key, self.VALUE_NAME)
                except FileNotFoundError:
                    pass
                logger.info("Startup com Windows desabilitado")

    def build_launch_command(self) -> str:
        if getattr(sys, "frozen", False):
            return f'"{os.path.abspath(sys.executable)}"'

        script_arg = (
            sys.argv[0] if sys.argv and sys.argv[0] not in {"", "-"} else "main.py"
        )
        script_path = os.path.abspath(script_arg)
        if not os.path.isfile(script_path):
            script_path = os.path.join(BASE_DIR, "main.py")
        interpreter = os.path.abspath(sys.executable)
        base_dir = os.path.dirname(interpreter)

        if os.path.basename(interpreter).lower() == "python.exe":
            pythonw = os.path.join(base_dir, "pythonw.exe")
            if os.path.exists(pythonw):
                interpreter = pythonw

        return f'"{interpreter}" "{script_path}"'
