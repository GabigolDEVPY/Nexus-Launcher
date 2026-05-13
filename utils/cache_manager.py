"""
Gerenciador de cache de imagens e metadados em disco.
"""

import os
import json
import shutil
from typing import Optional
from PIL import Image
from core.constants import IMAGE_CACHE_DIR, CACHE_DIR
from utils.logger import get_logger

logger = get_logger("CacheManager")


class CacheManager:
    """Cache local para imagens baixadas e metadados de APIs."""

    METADATA_DIR = os.path.join(CACHE_DIR, "metadata")

    def __init__(self):
        os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)
        os.makedirs(self.METADATA_DIR, exist_ok=True)

    # ---- Imagens ----

    def get_image_path(self, key: str) -> Optional[str]:
        """Retorna o caminho local de uma imagem cacheada, ou None."""
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            path = os.path.join(IMAGE_CACHE_DIR, f"{key}{ext}")
            if os.path.exists(path):
                return path
        return None

    def save_image(self, key: str, source_path: str) -> str:
        """Salva uma imagem no cache e retorna o caminho."""
        ext = os.path.splitext(source_path)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".webp"):
            ext = ".png"
        dest = os.path.join(IMAGE_CACHE_DIR, f"{key}{ext}")
        shutil.copy2(source_path, dest)
        return dest

    def save_image_from_pil(self, key: str, img: Image.Image, fmt: str = "PNG") -> str:
        ext = ".png" if fmt == "PNG" else ".jpg"
        dest = os.path.join(IMAGE_CACHE_DIR, f"{key}{ext}")
        img.save(dest, fmt)
        return dest

    # ---- Metadados ----

    def get_metadata(self, query: str) -> Optional[dict]:
        path = os.path.join(self.METADATA_DIR, self._safe_key(query) + ".json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def save_metadata(self, query: str, data: dict):
        path = os.path.join(self.METADATA_DIR, self._safe_key(query) + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _safe_key(self, key: str) -> str:
        return "".join(c if c.isalnum() or c in "._-" else "_" for c in key)[:128]
