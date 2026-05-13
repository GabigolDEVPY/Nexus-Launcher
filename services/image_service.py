"""
Serviço de download e cache de imagens de jogos.
"""

import requests
from typing import Optional
from PIL import Image
from io import BytesIO
from utils.logger import get_logger
from utils.cache_manager import CacheManager

logger = get_logger("ImageService")


class ImageService:
    """Baixa imagens de URLs e as armazena no cache local."""

    def __init__(self):
        self.cache = CacheManager()

    def get_or_download(
        self, key: str, url: str, size: Optional[tuple] = None
    ) -> Optional[str]:
        """Retorna caminho local. Baixa se não estiver em cache."""
        if not url:
            return None

        cached = self.cache.get_image_path(key)
        if cached:
            return cached

        return self.download(key, url, size)

    def download(
        self, key: str, url: str, size: Optional[tuple] = None
    ) -> Optional[str]:
        """Baixa uma imagem e salva no cache."""
        try:
            resp = requests.get(url, timeout=15, stream=True)
            resp.raise_for_status()

            img = Image.open(BytesIO(resp.content))

            if size:
                img = self._resize_cover(img, size)

            fmt = "JPEG" if img.mode == "RGB" else "PNG"
            return self.cache.save_image_from_pil(key, img, fmt)

        except Exception as e:
            logger.warning(f"Falha ao baixar imagem '{key}': {e}")
            return None

    def create_placeholder(
        self, key: str, text: str = "No Image", size=(460, 215)
    ) -> str:
        """Gera uma imagem placeholder com texto."""
        cached = self.cache.get_image_path(key)
        if cached:
            return cached

        img = Image.new("RGB", size, color=(30, 30, 30))
        return self.cache.save_image_from_pil(key, img, "PNG")

    def _resize_cover(self, img: Image.Image, target: tuple) -> Image.Image:
        """Redimensiona mantendo aspect ratio, cortando o excesso."""
        img_ratio = img.width / img.height
        target_ratio = target[0] / target[1]

        if img_ratio > target_ratio:
            new_h = target[1]
            new_w = int(new_h * img_ratio)
        else:
            new_w = target[0]
            new_h = int(new_w / img_ratio)

        img = img.resize((new_w, new_h), Image.LANCZOS)

        left = (new_w - target[0]) // 2
        top = (new_h - target[1]) // 2
        return img.crop((left, top, left + target[0], top + target[1]))
