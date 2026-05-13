"""
Servico de busca de metadados de jogos.
Usa RAWG quando configurado e recorre ao catalogo publico da Steam como fallback.
"""

from typing import Dict, List, Optional

import requests

from utils.cache_manager import CacheManager
from utils.logger import get_logger

logger = get_logger("MetadataService")


class MetadataService:
    """Busca informacoes e imagens de jogos online."""

    def __init__(self, settings):
        self.settings = settings
        self.cache = CacheManager()

    @property
    def rawg_key(self) -> str:
        return (self.settings.get("rawg_api_key", "") or "").strip()

    @property
    def sgdb_key(self) -> str:
        return (self.settings.get("steamgriddb_api_key", "") or "").strip()

    def search_game(self, query: str) -> List[Dict]:
        """Busca um jogo por nome. Retorna lista de resultados."""
        query = (query or "").strip()
        if not query:
            return []

        cache_key = f"search_{query.lower()}"
        cached = self.cache.get_metadata(cache_key)
        if cached:
            return cached

        results = self._search_rawg(query)
        if not results:
            results = self._search_steam_store(query)
        if not results:
            results = self._search_fallback(query)

        if results:
            self.cache.save_metadata(cache_key, results)
        return results

    def get_game_details(
        self,
        rawg_id: Optional[int] = None,
        steam_appid: Optional[int] = None,
    ) -> Optional[Dict]:
        """Obtem detalhes completos do jogo pela fonte disponivel."""
        if rawg_id:
            cache_key = f"detail_rawg_{rawg_id}"
            cached = self.cache.get_metadata(cache_key)
            if cached:
                return cached

            details = self._get_rawg_details(rawg_id)
            if details:
                self.cache.save_metadata(cache_key, details)
                return details

        if steam_appid:
            cache_key = f"detail_steam_{steam_appid}"
            cached = self.cache.get_metadata(cache_key)
            if cached:
                return cached

            details = self._get_steam_details(steam_appid)
            if details:
                self.cache.save_metadata(cache_key, details)
                return details

        return None

    def get_images(self, game_name: str) -> Dict[str, str]:
        """Busca imagens adicionais via SteamGridDB quando configurado."""
        images = {"banner": "", "cover": "", "hero": ""}

        if not self.sgdb_key:
            return images

        headers = {"Authorization": f"Bearer {self.sgdb_key}"}

        try:
            resp = requests.get(
                "https://www.steamgriddb.com/api/v2/search/autocomplete",
                params={"term": game_name},
                headers=headers,
                timeout=10,
            )
            if resp.status_code != 200 or not resp.json().get("data"):
                return images

            game_id = resp.json()["data"][0]["id"]

            grid_resp = requests.get(
                f"https://www.steamgriddb.com/api/v2/grids/game/{game_id}",
                headers=headers,
                timeout=10,
            )
            if grid_resp.status_code == 200 and grid_resp.json().get("data"):
                images["cover"] = grid_resp.json()["data"][0]["url"]

            hero_resp = requests.get(
                f"https://www.steamgriddb.com/api/v2/heroes/game/{game_id}",
                headers=headers,
                timeout=10,
            )
            if hero_resp.status_code == 200 and hero_resp.json().get("data"):
                images["hero"] = hero_resp.json()["data"][0]["url"]
                images["banner"] = images["hero"]

        except requests.RequestException as e:
            logger.warning(f"SteamGridDB request failed: {e}")

        return images

    def _search_rawg(self, query: str) -> List[Dict]:
        if not self.rawg_key:
            return []

        try:
            resp = requests.get(
                "https://api.rawg.io/api/games",
                params={"key": self.rawg_key, "search": query, "page_size": 5},
                timeout=10,
            )
            if resp.status_code != 200:
                return []

            data = resp.json()
            return [
                {
                    "source": "rawg",
                    "rawg_id": game["id"],
                    "steam_appid": None,
                    "name": game["name"],
                    "background_url": game.get("background_image", ""),
                    "cover_url": game.get("background_image", ""),
                    "released": game.get("released", ""),
                    "rating": game.get("rating", 0),
                }
                for game in data.get("results", [])
            ]
        except requests.RequestException as e:
            logger.warning(f"RAWG search failed: {e}")
            return []

    def _search_steam_store(self, query: str) -> List[Dict]:
        """Fallback publico usando o catalogo da Steam, sem API key."""
        try:
            resp = requests.get(
                "https://store.steampowered.com/api/storesearch/",
                params={"term": query, "l": "brazilian", "cc": "BR"},
                timeout=10,
            )
            if resp.status_code != 200:
                return []

            data = resp.json()
            results = []
            for item in data.get("items", [])[:8]:
                results.append(
                    {
                        "source": "steam",
                        "rawg_id": None,
                        "steam_appid": item.get("id"),
                        "name": item.get("name", query),
                        "background_url": item.get("tiny_image", ""),
                        "cover_url": item.get("tiny_image", ""),
                        "released": "",
                        "rating": item.get("metascore", 0),
                    }
                )
            return results
        except requests.RequestException as e:
            logger.warning(f"Steam store search failed: {e}")
            return []

    def _search_fallback(self, query: str) -> List[Dict]:
        """Fallback minimo para cadastro manual."""
        return [
            {
                "source": "fallback",
                "rawg_id": None,
                "steam_appid": None,
                "name": query,
                "background_url": "",
                "cover_url": "",
                "released": "",
                "rating": 0,
            }
        ]

    def _get_rawg_details(self, rawg_id: int) -> Optional[Dict]:
        if not self.rawg_key:
            return None

        try:
            resp = requests.get(
                f"https://api.rawg.io/api/games/{rawg_id}",
                params={"key": self.rawg_key},
                timeout=10,
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            return {
                "source": "rawg",
                "rawg_id": data.get("id"),
                "steam_appid": None,
                "name": data.get("name", ""),
                "description": self._clean_description(data.get("description_raw", "")),
                "genre": ", ".join(genre["name"] for genre in data.get("genres", [])),
                "developer": ", ".join(
                    dev["name"] for dev in data.get("developers", [])
                )
                if data.get("developers")
                else "",
                "publisher": ", ".join(
                    pub["name"] for pub in data.get("publishers", [])
                )
                if data.get("publishers")
                else "",
                "release_date": data.get("released", ""),
                "background_url": data.get("background_image", ""),
                "cover_url": data.get("background_image_additional", "")
                or data.get("background_image", ""),
                "platforms": ", ".join(
                    item["platform"]["name"]
                    for item in data.get("platforms", [])
                    if "platform" in item
                ),
            }
        except requests.RequestException as e:
            logger.warning(f"RAWG detail request failed: {e}")
            return None

    def _get_steam_details(self, steam_appid: int) -> Optional[Dict]:
        try:
            resp = requests.get(
                "https://store.steampowered.com/api/appdetails",
                params={"appids": steam_appid, "l": "brazilian", "cc": "BR"},
                timeout=10,
            )
            if resp.status_code != 200:
                return None

            payload = resp.json().get(str(steam_appid), {})
            if not payload.get("success"):
                return None

            data = payload.get("data", {})
            return {
                "source": "steam",
                "rawg_id": None,
                "steam_appid": steam_appid,
                "name": data.get("name", ""),
                "description": self._clean_description(
                    data.get("short_description")
                    or data.get("detailed_description", "")
                ),
                "genre": ", ".join(
                    genre.get("description", "")
                    for genre in data.get("genres", [])
                    if genre.get("description")
                ),
                "developer": ", ".join(data.get("developers", [])),
                "publisher": ", ".join(data.get("publishers", [])),
                "release_date": (data.get("release_date") or {}).get("date", ""),
                "background_url": data.get("header_image", ""),
                "cover_url": data.get("capsule_image", "")
                or data.get("capsule_imagev5", "")
                or data.get("header_image", ""),
                "platforms": ", ".join(
                    platform.upper()
                    for platform, enabled in (data.get("platforms") or {}).items()
                    if enabled
                )
                or "PC",
            }
        except requests.RequestException as e:
            logger.warning(f"Steam detail request failed: {e}")
            return None

    def _clean_description(self, text: str) -> str:
        """Remove tags HTML de descricoes vindas das APIs."""
        import re

        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("&amp;", "&").replace("&nbsp;", " ")
        return text.strip()[:2000]
