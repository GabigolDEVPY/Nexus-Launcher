"""
Constantes globais do NexusLauncher.
"""
import ctypes
import os
import shutil
import sys

APP_NAME = "NexusLauncher"
APP_VERSION = "1.0.0"

# Diretorios de codigo e recursos
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOURCE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
ASSETS_DIR = os.path.join(RESOURCE_DIR, "assets")


def _get_documents_dir() -> str:
    """Resolve a pasta Documentos do usuario."""
    if os.name == "nt":
        try:
            buffer = ctypes.create_unicode_buffer(260)
            # CSIDL_PERSONAL = 5
            result = ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer)
            if result == 0 and buffer.value:
                return buffer.value
        except Exception:
            pass

    home = os.path.expanduser("~")
    documents = os.path.join(home, "Documents")
    if os.path.isdir(documents):
        return documents
    return home


def _get_local_appdata_dir() -> str:
    local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
    if local_appdata:
        return local_appdata
    return os.path.join(os.path.expanduser("~"), "AppData", "Local")


def _resolve_app_data_dir() -> str:
    candidates = [
        os.path.join(_get_documents_dir(), APP_NAME),
        os.path.join(_get_local_appdata_dir(), APP_NAME),
        os.path.join(BASE_DIR, "user_data"),
    ]

    for candidate in candidates:
        try:
            os.makedirs(candidate, exist_ok=True)
            return candidate
        except OSError:
            continue

    return os.path.join(BASE_DIR, APP_NAME)


USER_DOCUMENTS_DIR = _get_documents_dir()
APP_DATA_DIR = _resolve_app_data_dir()
CACHE_DIR = os.path.join(APP_DATA_DIR, "cache")
IMAGE_CACHE_DIR = os.path.join(CACHE_DIR, "images")
LOG_DIR = os.path.join(APP_DATA_DIR, "logs")
DB_PATH = os.path.join(APP_DATA_DIR, "nexus.db")
CONFIG_PATH = os.path.join(APP_DATA_DIR, "config.json")

LEGACY_DB_PATH = os.path.join(BASE_DIR, "nexus.db")
LEGACY_CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

_runtime_prepared = False


def _copy_if_missing(source_path: str, destination_path: str):
    if not os.path.exists(source_path) or os.path.exists(destination_path):
        return

    os.makedirs(os.path.dirname(destination_path), exist_ok=True)
    shutil.copy2(source_path, destination_path)


def _migrate_legacy_user_data():
    """Copia dados legados do modo dev para a pasta do usuario."""
    _copy_if_missing(LEGACY_CONFIG_PATH, CONFIG_PATH)
    _copy_if_missing(LEGACY_DB_PATH, DB_PATH)
    _copy_if_missing(f"{LEGACY_DB_PATH}-shm", f"{DB_PATH}-shm")
    _copy_if_missing(f"{LEGACY_DB_PATH}-wal", f"{DB_PATH}-wal")


def prepare_runtime_environment():
    """Garante a estrutura de dados persistentes do launcher."""
    global _runtime_prepared
    if _runtime_prepared:
        return

    for path in [APP_DATA_DIR, CACHE_DIR, IMAGE_CACHE_DIR, LOG_DIR]:
        os.makedirs(path, exist_ok=True)

    _migrate_legacy_user_data()
    _runtime_prepared = True


# Dimensoes da UI
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 800
CAROUSEL_CARD_WIDTH = 220
CAROUSEL_CARD_HEIGHT = 310
DETAIL_BANNER_WIDTH = 900
DETAIL_BANNER_HEIGHT = 400

# Metadados
RAWG_API_URL = "https://api.rawg.io/api"
STEAMGRIDDB_API_URL = "https://www.steamgriddb.com/api/v2"

# Save sync
SAVE_SYNC_DEBOUNCE_MS = 3000  # debounce antes de commitar
MAX_COMMIT_MESSAGE_LEN = 200

# Extensoes de save conhecidas
SAVE_EXTENSIONS = {
    ".sav", ".save", ".dat", ".json", ".xml", ".ini",
    ".cfg", ".conf", ".profile", ".slot", ".esm", ".ess",
}

# Ignorar no monitoramento
IGNORE_PATTERNS = {
    "*.tmp", "*.temp", "~*", "*.lock", "Thumbs.db",
    ".DS_Store", "*.part", "*.crdownload",
}

# Play tracker
PROCESS_CHECK_INTERVAL_S = 5

# Fontes
FONT_DISPLAY = "Bebas Neue"
FONT_BODY = "Source Code Pro"
