"""
Gerenciador de sincronizacao com GitHub via API REST.
Nao depende de Git instalado: clona, compara, envia e restaura saves
usando apenas requisicoes HTTP autenticadas por token.
"""

import base64
import hashlib
import json
import os
import re
import shutil
import threading
import time
from datetime import datetime
from typing import Any, Optional

import requests

from core.constants import CACHE_DIR
from utils.helpers import count_files, file_hash, sanitize_filename
from utils.logger import get_logger

logger = get_logger("SyncManager")

GAMES_DIR = os.path.join(CACHE_DIR, "github_saves")

API_BASE_URL = "https://api.github.com"
REQUEST_TIMEOUT_S = (15, 300)
MAX_BLOB_BYTES = 95 * 1024 * 1024  # limite pratico da API de blobs
EXCLUDED_DIR_NAMES = {".git"}


def _git_blob_sha(data: bytes) -> str:
    """Calcula o sha1 de blob do Git para comparar com a arvore remota."""
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


class _GitHubRepoClient:
    """Cliente minimo da API REST do GitHub focado em arquivos e commits."""

    def __init__(self, owner: str, repo: str, token: str):
        self.owner = owner
        self.repo = repo
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "NexusLauncher",
            }
        )

    def _url(self, path: str) -> str:
        base = f"{API_BASE_URL}/repos/{self.owner}/{self.repo}"
        # A API do GitHub rejeita barra final (404), entao o caminho vazio
        # nao pode deixar slash pendente
        if not path:
            return base
        return f"{base}/{path}"

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", REQUEST_TIMEOUT_S)
        response = self.session.request(method, self._url(path), **kwargs)

        if response.status_code == 403 and response.headers.get(
            "X-RateLimit-Remaining"
        ) == "0":
            raise RuntimeError(
                "Limite de requisicoes da API do GitHub atingido. Tente mais tarde."
            )
        return response

    def get_repo_info(self) -> Optional[dict]:
        response = self._request("GET", "")
        if response.status_code == 200:
            return response.json()
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def get_head_commit(self, branch: str) -> Optional[str]:
        response = self._request("GET", f"git/ref/heads/{branch}")
        if response.status_code == 200:
            return response.json()["object"]["sha"]
        if response.status_code in (404, 409):
            return None
        response.raise_for_status()
        return None

    def get_tree(
        self, commit_sha: str
    ) -> tuple[str, dict[str, tuple[str, int]]]:
        """Retorna (tree_sha, {caminho: (blob_sha, tamanho)}) da arvore completa."""
        response = self._request("GET", f"git/trees/{commit_sha}", params={"recursive": "1"})
        response.raise_for_status()
        payload = response.json()
        if payload.get("truncated"):
            raise RuntimeError(
                "Repositorio grande demais para leitura pela API do GitHub."
            )
        entries: dict[str, tuple[str, int]] = {}
        for item in payload.get("tree", []):
            if item.get("type") == "blob":
                entries[item["path"]] = (item["sha"], int(item.get("size", 0)))
        return payload["sha"], entries

    def get_commit_tree_sha(self, commit_sha: str) -> Optional[str]:
        """Resolve o SHA da tree raiz de um commit."""
        response = self._request("GET", f"git/commits/{commit_sha}")
        if response.status_code != 200:
            return None
        return response.json().get("tree", {}).get("sha")

    def get_blob(self, blob_sha: str) -> bytes:
        response = self._request("GET", f"git/blobs/{blob_sha}")
        response.raise_for_status()
        payload = response.json()
        if payload.get("encoding") == "base64":
            return base64.b64decode(payload["content"])
        return payload["content"].encode("utf-8")

    def create_blob(self, data: bytes) -> str:
        response = self._request(
            "POST", "git/blobs", json={"content": base64.b64encode(data).decode("ascii"), "encoding": "base64"}
        )
        response.raise_for_status()
        return response.json()["sha"]

    def create_tree(self, entries: list[dict], base_tree: Optional[str]) -> str:
        body: dict[str, Any] = {"tree": entries}
        if base_tree:
            body["base_tree"] = base_tree
        response = self._request("POST", "git/trees", json=body)
        response.raise_for_status()
        return response.json()["sha"]

    def create_commit(
        self, message: str, tree_sha: str, parents: list[str]
    ) -> str:
        response = self._request(
            "POST", "git/commits", json={"message": message, "tree": tree_sha, "parents": parents}
        )
        response.raise_for_status()
        return response.json()["sha"]

    def update_ref(self, branch: str, commit_sha: str) -> bool:
        response = self._request(
            "PATCH",
            f"git/refs/heads/{branch}",
            json={"sha": commit_sha, "force": False},
        )
        if response.status_code == 200:
            return True
        if response.status_code == 422:  # ref moveu enquanto commitavamos
            return False
        response.raise_for_status()
        return False

    def create_ref(self, branch: str, commit_sha: str) -> bool:
        response = self._request(
            "POST", "git/refs", json={"ref": f"refs/heads/{branch}", "sha": commit_sha}
        )
        return response.status_code == 201


class SyncManager:
    """Sincroniza saves e dados do launcher com um repositorio GitHub pessoal."""

    GAME_SYNC_META_FILENAME = ".nexus-sync.json"

    def __init__(self, settings, notification_service):
        self.settings = settings
        self.notification = notification_service
        self._client: Optional[_GitHubRepoClient] = None
        self._repo_path: Optional[str] = None
        self._branch: str = "main"
        self._initialized = False
        self._lock = threading.RLock()
        os.makedirs(GAMES_DIR, exist_ok=True)

    # ------------------------------------------------------------------
    # Configuracao e ciclo de vida
    # ------------------------------------------------------------------

    @property
    def repo_path(self) -> str:
        return self._repo_path or ""

    def is_configured(self) -> bool:
        owner_repo, _ = self._resolve_repo_config()
        token = str(self.settings.get("github_token", "") or "").strip()
        return bool(owner_repo and token)

    def initialize(self) -> bool:
        """Valida o repositorio configurado e prepara o espelho local."""
        with self._lock:
            owner_repo, repo_name = self._resolve_repo_config()
            token = str(self.settings.get("github_token", "") or "").strip()

            if not owner_repo:
                message = (
                    "URL do repositorio GitHub invalida. "
                    "Use https://github.com/usuario/repo.git ou usuario/repo."
                )
                logger.error(message)
                self.notification.error(message)
                return False

            if not token:
                logger.warning("GitHub nao configurado")
                return False

            client = _GitHubRepoClient(owner_repo[0], owner_repo[1], token)
            try:
                info = client.get_repo_info()
            except requests.RequestException as e:
                logger.error(f"Falha ao acessar repositorio: {e}")
                self.notification.error(f"Erro de conexao com o GitHub: {e}")
                return False

            if info is None:
                message = f"Repositorio '{owner_repo[0]}/{owner_repo[1]}' nao encontrado."
                logger.error(message)
                self.notification.error(message)
                return False

            self._client = client
            self._branch = info.get("default_branch") or "main"
            self._repo_path = os.path.join(GAMES_DIR, repo_name or "saves_repo")
            os.makedirs(self._repo_path, exist_ok=True)
            self._discard_legacy_git_dir()
            self._initialized = True
            logger.info(
                f"Repositorio pronto: {owner_repo[0]}/{owner_repo[1]} (branch {self._branch})"
            )
            # Espelha o estado remoto antes de qualquer leitura, como o pull fazia
            self.refresh_from_remote()
            return True

    def ensure_ready(self) -> bool:
        if self._initialized and self._client and self._repo_path:
            return True
        return self.initialize()

    def refresh_from_remote(self) -> bool:
        """Baixa para o espelho local tudo o que mudou no GitHub."""
        with self._lock:
            if not self.ensure_ready():
                return False

            try:
                head = self._client.get_head_commit(self._branch)
                if head:
                    _, remote_tree = self._client.get_tree(head)
                else:
                    remote_tree = {}

                remote_paths = set(remote_tree)
                self._prune_mirror(remote_paths)
                self._download_missing(remote_tree)
                return True
            except (requests.RequestException, RuntimeError) as e:
                logger.error(f"Falha ao atualizar repo local a partir do GitHub: {e}")
                self.notification.error(f"Erro ao baixar do GitHub: {e}")
                return False

    def shutdown(self):
        """Limpeza ao encerrar."""
        self._initialized = False
        self._client = None

    # ------------------------------------------------------------------
    # Sync de saves de jogo
    # ------------------------------------------------------------------

    def sync_game_saves(self, game_id: int, game_name: str, save_folder: str) -> bool:
        """Compara a pasta local com o GitHub e envia as diferencas em um commit."""
        if not self.ensure_ready():
            return False

        try:
            game_dir_prefix = self._game_tree_prefix(game_id)
            head = self._client.get_head_commit(self._branch)
            if head:
                _, remote_tree = self._client.get_tree(head)
            else:
                remote_tree = {}

            commit_entries: list[dict] = []
            mirror_updates: dict[str, str] = {}  # tree_path -> arquivo local

            for dirpath, dirnames, filenames in os.walk(save_folder):
                dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIR_NAMES]
                for fname in filenames:
                    local_path = os.path.join(dirpath, fname)
                    rel_path = os.path.relpath(local_path, save_folder)
                    rel_path = rel_path.replace(os.sep, "/")
                    tree_path = f"{game_dir_prefix}{rel_path}"

                    try:
                        with open(local_path, "rb") as f:
                            data = f.read()
                    except OSError as e:
                        logger.warning(f"Nao foi possivel ler '{local_path}': {e}")
                        continue

                    if len(data) > MAX_BLOB_BYTES:
                        logger.warning(
                            f"Arquivo '{rel_path}' de '{game_name}' excede o limite "
                            "da API do GitHub e sera ignorado."
                        )
                        continue

                    blob_sha = _git_blob_sha(data)
                    remote_entry = remote_tree.get(tree_path)
                    if remote_entry and remote_entry[0] == blob_sha:
                        continue

                    sha = self._client.create_blob(data)
                    commit_entries.append(
                        {"path": tree_path, "mode": "100644", "type": "blob", "sha": sha}
                    )
                    mirror_updates[tree_path] = local_path

            meta_relative_path = self._get_game_sync_meta_relative_path(
                game_id, game_name
            )
            remote_paths = set(remote_tree)
            prefix_len = len(game_dir_prefix)
            for tree_path in remote_paths:
                if not tree_path.startswith(game_dir_prefix):
                    continue
                # o meta e sempre reenviado pelo bloco abaixo, nunca deletado
                if tree_path == meta_relative_path:
                    continue
                rel_path = tree_path[prefix_len:]
                local_path = os.path.join(save_folder, *rel_path.split("/"))
                if not os.path.isfile(local_path):
                    commit_entries.append(self._delete_entry(tree_path))
                    mirror_updates[tree_path] = ""

            meta_exists = meta_relative_path in remote_paths
            synced_at = self._current_sync_timestamp()

            if commit_entries or not meta_exists:
                meta_payload = {
                    "game_id": game_id,
                    "game_name": game_name,
                    "synced_at_utc": synced_at,
                }
                meta_content = (
                    json.dumps(meta_payload, indent=2, ensure_ascii=False) + "\n"
                ).encode("utf-8")
                meta_sha = self._client.create_blob(meta_content)
                commit_entries.append(
                    {
                        "path": meta_relative_path,
                        "mode": "100644",
                        "type": "blob",
                        "sha": meta_sha,
                    }
                )
                mirror_updates[meta_relative_path] = ""

            if not commit_entries:
                logger.debug(f"Nenhuma alteracao detectada para '{game_name}'")
                return True

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            commit_message = f"Auto-sync: {game_name} saves ({timestamp})"

            if self._commit_entries(commit_entries, commit_message):
                self._apply_mirror_updates(mirror_updates, synced_at, game_id, game_name)
                logger.info(f"Saves de '{game_name}' enviados ao GitHub")
                return True

            logger.error(f"Falha ao commitar saves de '{game_name}'")
            return False
        except (requests.RequestException, RuntimeError) as e:
            logger.error(f"Erro ao sincronizar '{game_name}': {e}")
            self.notification.error(f"Erro Git: {e}")
            return False
        except Exception as e:
            logger.error(f"Erro inesperado ao sincronizar '{game_name}': {e}")
            return False

    def compare_game_saves(
        self,
        game_id: int,
        game_name: str,
        local_save_folder: str,
        local_last_synced: Optional[datetime | str] = None,
    ) -> dict:
        """Compara save local e save do espelho do repo para detectar restauracao ou conflito."""
        if not self.ensure_ready():
            return self._empty_comparison()

        repo_dir = self._get_game_repo_dir(game_id, game_name)
        local_exists = self._directory_has_files(local_save_folder)
        repo_exists = self._directory_has_files(
            repo_dir,
            exclude_names={self.GAME_SYNC_META_FILENAME},
        )

        local_manifest = self._build_directory_manifest(local_save_folder)
        repo_manifest = self._build_directory_manifest(
            repo_dir,
            exclude_names={self.GAME_SYNC_META_FILENAME},
        )
        identical = local_manifest == repo_manifest

        repo_meta = self.get_game_sync_metadata(game_id, game_name)
        repo_synced_at = str((repo_meta or {}).get("synced_at_utc", "") or "")
        local_last_synced_text = self._normalize_sync_timestamp(local_last_synced)

        return {
            "local_exists": local_exists,
            "repo_exists": repo_exists,
            "identical": identical,
            "local_files": len(local_manifest),
            "local_size": sum(item["size"] for item in local_manifest.values()),
            "repo_files": len(repo_manifest),
            "repo_size": sum(item["size"] for item in repo_manifest.values()),
            "repo_synced_at": repo_synced_at,
            "local_last_synced": local_last_synced_text,
            "can_upload_without_prompt": (
                local_exists
                and repo_exists
                and not identical
                and bool(repo_synced_at)
                and repo_synced_at == local_last_synced_text
            ),
        }

    def restore_game_saves(
        self, game_id: int, game_name: str, destination_folder: str
    ) -> bool:
        """Restaura o save do repo para a pasta local configurada."""
        with self._lock:
            if not self.ensure_ready():
                return False

            repo_dir = self._get_game_repo_dir(game_id, game_name)
            if not self._directory_has_files(
                repo_dir,
                exclude_names={self.GAME_SYNC_META_FILENAME},
            ):
                return False

            os.makedirs(destination_folder, exist_ok=True)
            self._mirror_directory(
                repo_dir,
                destination_folder,
                exclude_names={self.GAME_SYNC_META_FILENAME},
            )
            return True

    def migrate_game_repo_reference(
        self,
        game_id: int,
        old_game_name: str,
        new_game_name: str,
    ) -> bool:
        """Move um save legado baseado em nome para uma chave estavel por id."""
        with self._lock:
            if not self.ensure_ready():
                return False

            try:
                target_prefix = self._game_tree_prefix(game_id)
                legacy_prefixes = [
                    f"Saves/{sanitize_filename(old_game_name)}/",
                    f"Saves/{sanitize_filename(new_game_name)}/",
                ]
                legacy_prefixes = [
                    prefix for prefix in legacy_prefixes if prefix != target_prefix
                ]

                head = self._client.get_head_commit(self._branch)
                if head:
                    _, remote_tree = self._client.get_tree(head)
                else:
                    remote_tree = {}

                commit_entries: list[dict] = []
                for tree_path, (blob_sha, _) in sorted(remote_tree.items()):
                    matched_prefix = next(
                        (
                            prefix
                            for prefix in legacy_prefixes
                            if tree_path.startswith(prefix)
                        ),
                        None,
                    )
                    if matched_prefix is None:
                        continue

                    new_path = target_prefix + tree_path[len(matched_prefix):]
                    if new_path == tree_path:
                        continue
                    commit_entries.append(
                        {"path": new_path, "mode": "100644", "type": "blob", "sha": blob_sha}
                    )
                    commit_entries.append(self._delete_entry(tree_path))

                target_meta = self._get_game_sync_meta_relative_path(
                    game_id, new_game_name
                )
                legacy_meta = next(
                    (
                        prefix + self.GAME_SYNC_META_FILENAME
                        for prefix in legacy_prefixes
                        if prefix + self.GAME_SYNC_META_FILENAME in remote_tree
                    ),
                    None,
                )
                if target_meta not in remote_tree:
                    if legacy_meta:
                        commit_entries.append(
                            {
                                "path": target_meta,
                                "mode": "100644",
                                "type": "blob",
                                "sha": remote_tree[legacy_meta][0],
                            }
                        )
                        commit_entries.append(self._delete_entry(legacy_meta))
                    else:
                        synced_at = self._current_sync_timestamp()
                        meta_content = (
                            json.dumps(
                                {
                                    "game_id": game_id,
                                    "game_name": new_game_name,
                                    "synced_at_utc": synced_at,
                                },
                                indent=2,
                                ensure_ascii=False,
                            )
                            + "\n"
                        ).encode("utf-8")
                        meta_sha = self._client.create_blob(meta_content)
                        commit_entries.append(
                            {
                                "path": target_meta,
                                "mode": "100644",
                                "type": "blob",
                                "sha": meta_sha,
                            }
                        )

                if not commit_entries:
                    return True

                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if not self._commit_entries(
                    commit_entries,
                    f"Save mapping atualizado: {new_game_name} ({timestamp})",
                ):
                    return False

                self.refresh_from_remote()
                return True
            except (requests.RequestException, RuntimeError) as e:
                logger.error(f"Erro ao migrar save de '{old_game_name}': {e}")
                self.notification.error(f"Erro Git: {e}")
                return False

    # ------------------------------------------------------------------
    # Arquivos avulsos (snapshot do estado do launcher)
    # ------------------------------------------------------------------

    def get_game_sync_metadata(self, game_id: int, game_name: str) -> Optional[dict]:
        meta_path = self._get_game_sync_meta_relative_path(game_id, game_name)
        payload = self._read_repo_file(meta_path)
        if payload is None:
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError as e:
            logger.error(f"Falha ao ler metadado de sync de '{game_name}': {e}")
            return None

    def read_json(self, relative_path: str) -> Optional[dict]:
        payload = self._read_repo_file(relative_path)
        if payload is None:
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError as e:
            logger.error(f"Falha ao ler JSON do repo '{relative_path}': {e}")
            return None

    def write_json_and_sync(
        self,
        relative_path: str,
        payload: dict,
        commit_message: str,
    ) -> bool:
        content = json.dumps(payload, indent=2, ensure_ascii=False)
        return self.write_text_and_sync(relative_path, content + "\n", commit_message)

    def write_text_and_sync(
        self,
        relative_path: str,
        content: str,
        commit_message: str,
    ) -> bool:
        with self._lock:
            if not self.ensure_ready():
                return False

            try:
                head = self._client.get_head_commit(self._branch)
                if head:
                    _, remote_tree = self._client.get_tree(head)
                else:
                    remote_tree = {}
                data = content.encode("utf-8")
                blob_sha = _git_blob_sha(data)

                remote_entry = remote_tree.get(relative_path)
                if remote_entry and remote_entry[0] == blob_sha:
                    return True

                sha = self._client.create_blob(data)
                entry = {
                    "path": relative_path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": sha,
                }
                if self._commit_entries([entry], commit_message):
                    self._write_mirror_file(relative_path, content)
                    return True
                return False
            except (requests.RequestException, RuntimeError) as e:
                logger.error(f"Falha ao gravar '{relative_path}' no GitHub: {e}")
                self.notification.error(f"Erro Git: {e}")
                return False

    def sync_paths(self, relative_paths: list[str], commit_message: str) -> bool:
        """Envia para o GitHub o conteudo atual desses arquivos no espelho local."""
        with self._lock:
            if not self.ensure_ready():
                return False

            try:
                head = self._client.get_head_commit(self._branch)
                if head:
                    _, remote_tree = self._client.get_tree(head)
                else:
                    remote_tree = {}

                commit_entries: list[dict] = []
                for relative_path in relative_paths:
                    relative_path = relative_path.replace("\\", "/")
                    mirror_file = os.path.join(self._repo_path, relative_path)
                    if not os.path.isfile(mirror_file):
                        if relative_path in remote_tree:
                            commit_entries.append(self._delete_entry(relative_path))
                        continue

                    with open(mirror_file, "rb") as f:
                        data = f.read()
                    blob_sha = _git_blob_sha(data)
                    remote_entry = remote_tree.get(relative_path)
                    if remote_entry and remote_entry[0] == blob_sha:
                        continue
                    sha = self._client.create_blob(data)
                    commit_entries.append(
                        {
                            "path": relative_path,
                            "mode": "100644",
                            "type": "blob",
                            "sha": sha,
                        }
                    )

                if not commit_entries:
                    logger.debug("Nenhuma alteracao para commit")
                    return True

                return self._commit_entries(commit_entries, commit_message)
            except (requests.RequestException, RuntimeError) as e:
                logger.error(f"Falha ao sincronizar caminhos {relative_paths}: {e}")
                self.notification.error(f"Erro Git: {e}")
                return False

    def get_sync_status(self, game_name: str, game_id: Optional[int] = None) -> dict:
        """Retorna status de sincronizacao de um jogo."""
        if not self._repo_path:
            return {"synced": False, "files": 0, "size": 0}

        if game_id is None:
            game_dir = self._get_legacy_game_repo_dir(game_name)
        else:
            game_dir = self._get_game_repo_dir(game_id, game_name)
        if not self._directory_has_files(
            game_dir,
            exclude_names={self.GAME_SYNC_META_FILENAME},
        ):
            return {"synced": False, "files": 0, "size": 0}

        return {
            "synced": True,
            "files": count_files(game_dir, None)
            - int(os.path.isfile(os.path.join(game_dir, self.GAME_SYNC_META_FILENAME))),
            "size": self._directory_size_without_meta(game_dir),
        }

    # ------------------------------------------------------------------
    # Commit de baixo nivel
    # ------------------------------------------------------------------

    @staticmethod
    def _delete_entry(tree_path: str) -> dict:
        """Entrada de remocao para a arvore; a API exige mode e type mesmo assim."""
        return {"path": tree_path, "mode": "100644", "type": "blob", "sha": None}

    def _commit_entries(
        self,
        entries: list[dict],
        message: str,
    ) -> bool:
        """Cria tree + commit + atualiza a branch, com retry em corrida."""
        for _ in range(3):
            head = self._client.get_head_commit(self._branch)
            base_tree = None
            if head:
                base_tree = self._client.get_commit_tree_sha(head)
                if not base_tree:
                    return False
            tree_sha = self._client.create_tree(entries, base_tree)
            parents = [head] if head else []
            commit_sha = self._client.create_commit(message, tree_sha, parents)
            if self._client.update_ref(self._branch, commit_sha):
                return True
            if not head and self._client.create_ref(self._branch, commit_sha):
                return True
            time.sleep(0.5)
        return False

    # ------------------------------------------------------------------
    # Espelho local do repositorio
    # ------------------------------------------------------------------

    def _discard_legacy_git_dir(self):
        """Remove metadados de clones antigos via Git; a API nao os usa."""
        legacy_git_dir = os.path.join(self._repo_path, ".git")
        if os.path.isdir(legacy_git_dir):
            shutil.rmtree(legacy_git_dir, ignore_errors=True)
            logger.info("Pasta .git de clone legado removida do espelho local")

    def _read_repo_file(self, relative_path: str) -> Optional[str]:
        """Le um arquivo do repo: primeiro do espelho, depois da API."""
        if not self.ensure_ready():
            return None

        mirror_file = os.path.join(self._repo_path, relative_path)
        if os.path.isfile(mirror_file):
            try:
                with open(mirror_file, "r", encoding="utf-8") as f:
                    return f.read()
            except OSError as e:
                logger.error(f"Falha ao ler '{relative_path}' do espelho: {e}")

        with self._lock:
            try:
                head = self._client.get_head_commit(self._branch)
                if not head:
                    return None
                _, remote_tree = self._client.get_tree(head)
                entry = remote_tree.get(relative_path)
                if not entry:
                    return None
                data = self._client.get_blob(entry[0])
                content = data.decode("utf-8")
                self._write_mirror_file(relative_path, content)
                return content
            except (requests.RequestException, RuntimeError) as e:
                logger.error(f"Falha ao baixar '{relative_path}': {e}")
                return None

    def _prune_mirror(self, remote_paths: set[str]):
        """Remove do espelho tudo que nao existe mais no repositorio remoto."""
        for dirpath, dirnames, filenames in os.walk(self._repo_path, topdown=True):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIR_NAMES]
            for fname in filenames:
                full_path = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(full_path, self._repo_path).replace(
                    os.sep, "/"
                )
                if rel_path not in remote_paths:
                    try:
                        os.remove(full_path)
                    except OSError:
                        pass

            for dirname in list(dirnames):
                subdir = os.path.join(dirpath, dirname)
                rel_dir = os.path.relpath(subdir, self._repo_path).replace(os.sep, "/")
                if not any(path.startswith(rel_dir + "/") for path in remote_paths):
                    shutil.rmtree(subdir, ignore_errors=True)
                    dirnames.remove(dirname)

    def _download_missing(self, remote_tree: dict[str, tuple[str, int]]):
        """Baixa arquivos remotos ausentes ou diferentes no espelho."""
        for tree_path, (blob_sha, _) in remote_tree.items():
            mirror_file = os.path.join(self._repo_path, *tree_path.split("/"))
            if os.path.isfile(mirror_file):
                try:
                    with open(mirror_file, "rb") as f:
                        if _git_blob_sha(f.read()) == blob_sha:
                            continue
                except OSError:
                    pass

            data = self._client.get_blob(blob_sha)
            os.makedirs(os.path.dirname(mirror_file), exist_ok=True)
            with open(mirror_file, "wb") as f:
                f.write(data)

    def _apply_mirror_updates(
        self,
        mirror_updates: dict[str, str],
        synced_at: str,
        game_id: int,
        game_name: str,
    ):
        """Reflete no espelho local o que foi enviado ao GitHub."""
        for tree_path, source_path in mirror_updates.items():
            mirror_file = os.path.join(self._repo_path, *tree_path.split("/"))
            if not source_path:
                if os.path.isfile(mirror_file):
                    try:
                        os.remove(mirror_file)
                    except OSError:
                        pass
                continue
            try:
                os.makedirs(os.path.dirname(mirror_file), exist_ok=True)
                shutil.copy2(source_path, mirror_file)
            except OSError as e:
                logger.warning(f"Falha ao atualizar espelho '{tree_path}': {e}")

        meta_relative_path = self._get_game_sync_meta_relative_path(
            game_id, game_name
        )
        self._write_mirror_file(
            meta_relative_path,
            json.dumps(
                {
                    "game_id": game_id,
                    "game_name": game_name,
                    "synced_at_utc": synced_at,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
        )

    def _write_mirror_file(self, relative_path: str, content: str):
        target = os.path.join(self._repo_path, *relative_path.split("/"))
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as e:
            logger.warning(f"Falha ao gravar espelho '{relative_path}': {e}")

    # ------------------------------------------------------------------
    # Helpers de caminho e manifesto
    # ------------------------------------------------------------------

    def _game_tree_prefix(self, game_id: int) -> str:
        return f"Saves/game_{game_id}/"

    def _get_legacy_game_repo_dir(self, game_name: str) -> str:
        return os.path.join(
            self._repo_path or "", "Saves", sanitize_filename(game_name)
        )

    def _get_game_repo_dir(self, game_id: int, game_name: str) -> str:
        target_dir = os.path.join(
            self._repo_path or "", "Saves", f"game_{game_id}"
        )
        legacy_dir = self._get_legacy_game_repo_dir(game_name)
        if (
            not os.path.isdir(target_dir)
            and os.path.isdir(legacy_dir)
            and legacy_dir != target_dir
        ):
            os.makedirs(os.path.dirname(target_dir), exist_ok=True)
            shutil.move(legacy_dir, target_dir)
        return target_dir

    def _get_game_sync_meta_relative_path(self, game_id: int, game_name: str) -> str:
        return f"Saves/game_{game_id}/{self.GAME_SYNC_META_FILENAME}"

    def _mirror_directory(
        self,
        src: str,
        dst: str,
        exclude_names: Optional[set[str]] = None,
    ) -> bool:
        """Faz o diretorio de destino espelhar exatamente o de origem."""
        changed = False
        exclude_names = exclude_names or set()

        os.makedirs(dst, exist_ok=True)

        for dirpath, dirnames, filenames in os.walk(dst, topdown=False):
            rel_dir = os.path.relpath(dirpath, dst)
            src_dir = src if rel_dir == "." else os.path.join(src, rel_dir)

            for fname in filenames:
                if fname in exclude_names:
                    continue
                src_file = os.path.join(src_dir, fname)
                dst_file = os.path.join(dirpath, fname)
                if not os.path.exists(src_file):
                    os.remove(dst_file)
                    changed = True

            for dirname in dirnames:
                dst_subdir = os.path.join(dirpath, dirname)
                src_subdir = os.path.join(src_dir, dirname)
                if not os.path.exists(src_subdir):
                    shutil.rmtree(dst_subdir, ignore_errors=True)
                    changed = True

        for dirpath, _, filenames in os.walk(src):
            rel_dir = os.path.relpath(dirpath, src)
            dest_dir = dst if rel_dir == "." else os.path.join(dst, rel_dir)
            os.makedirs(dest_dir, exist_ok=True)

            for fname in filenames:
                if fname in exclude_names:
                    continue

                src_file = os.path.join(dirpath, fname)
                dst_file = os.path.join(dest_dir, fname)

                if not os.path.exists(dst_file) or self._files_differ(
                    src_file, dst_file
                ):
                    shutil.copy2(src_file, dst_file)
                    changed = True

        return changed

    def _build_directory_manifest(
        self,
        path: str,
        exclude_names: Optional[set[str]] = None,
    ) -> dict:
        manifest = {}
        exclude_names = exclude_names or set()
        if not os.path.isdir(path):
            return manifest

        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIR_NAMES]
            for fname in sorted(filenames):
                if fname in exclude_names:
                    continue

                file_path = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(file_path, path).replace("\\", "/")
                manifest[rel_path] = {
                    "size": os.path.getsize(file_path),
                    "sha256": file_hash(file_path),
                }

        return manifest

    def _directory_has_files(
        self,
        path: str,
        exclude_names: Optional[set[str]] = None,
    ) -> bool:
        exclude_names = exclude_names or set()
        if not os.path.isdir(path):
            return False

        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIR_NAMES]
            for fname in filenames:
                if fname not in exclude_names:
                    return True
        return False

    def _directory_size_without_meta(self, path: str) -> int:
        total = 0
        if not os.path.isdir(path):
            return total

        for dirpath, _, filenames in os.walk(path):
            for fname in filenames:
                if fname == self.GAME_SYNC_META_FILENAME:
                    continue
                total += os.path.getsize(os.path.join(dirpath, fname))
        return total

    def _files_differ(self, src_file: str, dst_file: str) -> bool:
        src_stat = os.stat(src_file)
        dst_stat = os.stat(dst_file)
        if src_stat.st_size != dst_stat.st_size:
            return True
        return file_hash(src_file) != file_hash(dst_file)

    def _empty_comparison(self) -> dict:
        return {
            "local_exists": False,
            "repo_exists": False,
            "identical": True,
            "local_files": 0,
            "local_size": 0,
            "repo_files": 0,
            "repo_size": 0,
            "repo_synced_at": "",
            "local_last_synced": "",
            "can_upload_without_prompt": False,
        }

    # ------------------------------------------------------------------
    # Config do repositorio
    # ------------------------------------------------------------------

    def _resolve_repo_config(self) -> tuple[Optional[tuple[str, str]], str]:
        """Normaliza URL remota para (owner, repo) e nome da pasta local."""
        repo_url = str(self.settings.get("github_repo_url", "") or "").strip()
        repo_name = str(self.settings.get("github_repo_name", "") or "").strip()

        if self._looks_like_repo_url(repo_name) and not self._looks_like_repo_url(
            repo_url
        ):
            repo_url, repo_name = repo_name, repo_url

        normalized_url = self._normalize_repo_url(repo_url)

        if not repo_name or self._looks_like_repo_url(repo_name):
            repo_name = self._extract_repo_name(repo_name or repo_url)

        owner_repo = self._extract_owner_repo(normalized_url)
        return owner_repo, sanitize_filename(repo_name or "saves_repo")

    @staticmethod
    def _looks_like_repo_url(value: str) -> bool:
        value = (value or "").strip()
        if not value:
            return False
        return (
            value.startswith("https://github.com/")
            or value.startswith("http://github.com/")
            or value.startswith("git@github.com:")
            or ("/" in value and "\\" not in value and " " not in value)
        )

    @staticmethod
    def _normalize_repo_url(value: str) -> str:
        value = (value or "").strip().rstrip("/")
        if not value:
            return ""

        if value.startswith("git@github.com:"):
            value = value.split(":", 1)[1]
            if value.endswith(".git"):
                return f"https://github.com/{value}"
            return f"https://github.com/{value}.git"

        if value.startswith("https://") or value.startswith("http://"):
            return value

        if "/" in value and "\\" not in value and " " not in value:
            if value.endswith(".git"):
                return f"https://github.com/{value}"
            return f"https://github.com/{value}.git"

        return ""

    @staticmethod
    def _extract_owner_repo(url: str) -> Optional[tuple[str, str]]:
        url = (url or "").strip().rstrip("/")
        url = re.sub(r"^https?://(www\.)?github\.com/", "", url, flags=re.IGNORECASE)
        url = url.removesuffix(".git")
        parts = [part for part in url.split("/") if part]
        if len(parts) >= 2 and parts[0] and parts[1]:
            return parts[0], parts[1]
        return None

    @staticmethod
    def _extract_repo_name(value: str) -> str:
        value = (value or "").strip().rstrip("/")
        if not value:
            return ""
        if value.endswith(".git"):
            value = value[:-4]
        if value.startswith("git@github.com:"):
            value = value.split(":", 1)[1]
        return value.rsplit("/", 1)[-1].strip()

    @staticmethod
    def _normalize_sync_timestamp(value: Optional[datetime | str]) -> str:
        if isinstance(value, datetime):
            return value.replace(microsecond=0).isoformat() + "Z"
        return str(value or "").strip()

    @staticmethod
    def _current_sync_timestamp() -> str:
        return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
