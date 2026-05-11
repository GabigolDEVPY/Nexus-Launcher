"""
Detector automático de jogos instalados no sistema.
Varredura de pastas conhecidas e extração de metadados de executáveis.
"""
import os
import re
import winreg
import struct
from pathlib import Path
from typing import List, Dict, Optional
from utils.logger import get_logger

logger = get_logger("GameDetector")

# Pastas padrão onde jogos costumam estar instalados
DEFAULT_SCAN_DIRS = [
    os.path.expandvars(r"C:\Program Files"),
    os.path.expandvars(r"C:\Program Files (x86)"),
    os.path.expandvars(r"D:\Games"),
    os.path.expandvars(r"D:\SteamLibrary\steamapps\common"),
    os.path.expandvars(r"C:\Program Files\Epic Games"),
    os.path.expandvars(r"C:\Program Files\GOG Galaxy\Games"),
    os.path.expandvars(r"C:\Program Files\Ubisoft\Ubisoft Game Launcher\games"),
    os.path.expandvars(r"C:\XboxGames"),
]


class GameDetector:
    """Detecta executáveis de jogos no sistema."""

    def __init__(self, extra_dirs: Optional[List[str]] = None):
        self.scan_dirs = list(DEFAULT_SCAN_DIRS)
        if extra_dirs:
            self.scan_dirs.extend(extra_dirs)

    def scan_all(self) -> List[Dict]:
        """Varre diretórios conhecidos e retorna executáveis encontrados."""
        results = []
        seen_paths = set()

        for scan_dir in self.scan_dirs:
            if not os.path.isdir(scan_dir):
                continue
            for entry in self._find_executables(scan_dir):
                norm = os.path.normcase(entry["path"])
                if norm not in seen_paths:
                    seen_paths.add(norm)
                    results.append(entry)

        # Busca via registro Windows (Steam, Epic, etc.)
        registry_games = self._scan_registry()
        for rg in registry_games:
            norm = os.path.normcase(rg["path"])
            if norm not in seen_paths:
                seen_paths.add(norm)
                results.append(rg)

        logger.info(f"Encontrados {len(results)} executáveis")
        return results

    def _find_executables(self, root: str, max_depth: int = 3):
        """Encontra .exe em até max_depth níveis de diretório."""
        root_depth = root.count(os.sep)
        for dirpath, dirnames, filenames in os.walk(root):
            current_depth = dirpath.count(os.sep) - root_depth
            if current_depth >= max_depth:
                dirnames.clear()
                continue

            # Pula diretórios irrelevantes
            dirnames[:] = [
                d for d in dirnames
                if d.lower() not in {
                    "__pycache__", ".git", "node_modules", "redist",
                    "redistributable", "_commonredist", "directx",
                    "dotnet", "vcredist", "support", "unins000",
                }
            ]

            for f in filenames:
                if f.lower().endswith(".exe"):
                    full_path = os.path.join(dirpath, f)
                    # Filtra desinstaladores e utilitários
                    fname_lower = f.lower()
                    if any(skip in fname_lower for skip in [
                        "unins", "uninstall", "setup", "installer",
                        "crash", "report", "helper", "updater", "patcher",
                    ]):
                        continue

                    yield {
                        "path": full_path,
                        "name": self._guess_name(f, dirpath),
                        "folder": dirpath,
                    }

    def _scan_registry(self) -> List[Dict]:
        """Lê programas registrados no Windows para encontrar jogos."""
        games = []
        try:
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
            for root_key in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                try:
                    key = winreg.OpenKey(root_key, key_path)
                except OSError:
                    continue

                for i in range(0, winreg.QueryInfoKey(key)[0]):
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        subkey = winreg.OpenKey(key, subkey_name)
                        display_name = self._reg_query(subkey, "DisplayName")
                        install_loc = self._reg_query(subkey, "InstallLocation")
                        icon_path = self._reg_query(subkey, "DisplayIcon")

                        if install_loc and os.path.isdir(install_loc):
                            exe = self._find_main_exe(install_loc)
                            if exe:
                                games.append({
                                    "path": exe,
                                    "name": display_name or self._guess_name(
                                        os.path.basename(exe), install_loc
                                    ),
                                    "folder": install_loc,
                                    "icon": icon_path,
                                })
                        winreg.CloseKey(subkey)
                    except (OSError, ValueError):
                        continue
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Registry scan error: {e}")

        return games

    def _reg_query(self, key, name: str) -> Optional[str]:
        try:
            val, _ = winreg.QueryValueEx(key, name)
            return str(val).strip().strip('"')
        except (OSError, ValueError):
            return None

    def _find_main_exe(self, folder: str) -> Optional[str]:
        """Tenta achar o executável principal de uma pasta."""
        exes = []
        for f in os.listdir(folder):
            if f.lower().endswith(".exe"):
                fl = f.lower()
                if any(skip in fl for skip in ["unins", "setup", "install"]):
                    continue
                full = os.path.join(folder, f)
                exes.append((os.path.getsize(full), full))

        if not exes:
            return None

        # O maior .exe costuma ser o jogo principal
        exes.sort(reverse=True)
        return exes[0][1]

    def _guess_name(self, exe_name: str, folder: str) -> str:
        """Extrai um nome legível."""
        # Usa o nome da pasta acima se for uma pasta 'common'
        parts = Path(folder).parts
        for i, p in enumerate(parts):
            if p.lower() in ("common", "games") and i + 1 < len(parts):
                return parts[i + 1]

        # Fallback: nome do exe
        return Path(exe_name).stem.replace("_", " ").replace("-", " ").title()
