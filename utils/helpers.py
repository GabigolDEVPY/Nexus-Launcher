"""
Utilitários gerais.
"""

import os
import re
import hashlib
from pathlib import Path
from typing import Optional


def sanitize_filename(name: str) -> str:
    """Remove caracteres inválidos para nomes de arquivo/pasta."""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip()


def human_readable_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024**2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024**3:
        return f"{size_bytes / (1024**2):.1f} MB"
    return f"{size_bytes / (1024**3):.2f} GB"


def file_hash(filepath: str) -> str:
    """SHA-256 hash rápido de um arquivo."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_game_name_from_path(exe_path: str) -> str:
    """Tenta extrair o nome do jogo a partir do caminho do executável."""
    parts = Path(exe_path).parts
    # Tenta achar um diretório que pareça o nome do jogo
    known_dirs = {"steamapps", "common", "Program Files", "Games", "GOG Games"}
    for i, part in enumerate(parts):
        if part in known_dirs and i + 1 < len(parts):
            return parts[i + 1]
    # Fallback: nome do executável sem extensão
    return Path(exe_path).stem.replace("_", " ").replace("-", " ").title()


def format_playtime(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if h > 0:
        return f"{h}h {m}min"
    return f"{m}min"


def get_directory_size(path: str) -> int:
    """Calcula o tamanho total de um diretório recursivamente."""
    total = 0
    try:
        for dirpath, _, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.isfile(fp):
                    total += os.path.getsize(fp)
    except OSError:
        pass
    return total


def count_files(path: str, extensions: Optional[set] = None) -> int:
    """Conta arquivos em um diretório, opcionalmente filtrando por extensão."""
    count = 0
    try:
        for _, _, filenames in os.walk(path):
            for f in filenames:
                if extensions is None or Path(f).suffix.lower() in extensions:
                    count += 1
    except OSError:
        pass
    return count
