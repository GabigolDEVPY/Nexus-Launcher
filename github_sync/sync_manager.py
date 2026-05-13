"""
Gerenciador de sincronizacao com GitHub.
Clona repositorios, cria commits e faz push de save-games e do estado do launcher.
"""

import json
import os
import shutil
import sys
import threading
from datetime import datetime
from typing import Optional

from git import GitCommandError, Repo, refresh
from git.exc import GitCommandNotFound, InvalidGitRepositoryError

from core.constants import BASE_DIR, CACHE_DIR, RESOURCE_DIR
from utils.helpers import count_files, file_hash, sanitize_filename
from utils.logger import get_logger

logger = get_logger("SyncManager")

GAMES_DIR = os.path.join(CACHE_DIR, "github_saves")


class SyncManager:
    """Sincroniza saves e dados do launcher com um repositorio GitHub pessoal."""

    GAME_SYNC_META_FILENAME = ".nexus-sync.json"

    def __init__(self, settings, notification_service):
        self.settings = settings
        self.notification = notification_service
        self._repo: Optional[Repo] = None
        self._repo_path: Optional[str] = None
        self._initialized = False
        self._git_runtime_checked = False
        self._git_executable = ""
        self._lock = threading.RLock()
        os.makedirs(GAMES_DIR, exist_ok=True)

    @property
    def repo_path(self) -> str:
        return self._repo_path or ""

    def is_configured(self) -> bool:
        repo_url, _ = self._resolve_repo_config()
        token = str(self.settings.get("github_token", "") or "").strip()
        return bool(repo_url and token)

    def initialize(self) -> bool:
        """Clona ou abre o repositorio configurado."""
        with self._lock:
            if not self._ensure_git_available():
                return False

            repo_url, repo_name = self._resolve_repo_config()
            token = str(self.settings.get("github_token", "") or "").strip()

            if not repo_url:
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

            self._repo_path = os.path.join(GAMES_DIR, repo_name or "saves_repo")
            auth_url = self._inject_token(repo_url, token)

            if os.path.isdir(os.path.join(self._repo_path, ".git")):
                try:
                    self._repo = Repo(self._repo_path)
                    self._repo.remote("origin").set_url(auth_url)
                    self._repo.remote("origin").pull()
                    self._initialized = True
                    logger.info(f"Repositorio aberto: {self._repo_path}")
                    return True
                except (GitCommandError, InvalidGitRepositoryError) as e:
                    logger.error(f"Erro ao abrir repo existente: {e}")
                    shutil.rmtree(self._repo_path, ignore_errors=True)

            try:
                self._repo = Repo.clone_from(auth_url, self._repo_path)
                self._initialized = True
                logger.info(f"Repositorio clonado: {self._repo_path}")
                return True
            except (GitCommandError, GitCommandNotFound) as e:
                logger.error(f"Falha ao clonar repositorio: {e}")
                self.notification.error(f"Erro ao clonar repositorio: {e}")
                return False

    def ensure_ready(self) -> bool:
        if self._initialized and self._repo and self._repo_path:
            return True
        return self.initialize()

    def refresh_from_remote(self) -> bool:
        with self._lock:
            if not self.ensure_ready():
                return False

            try:
                if self._repo.is_dirty(untracked_files=True):
                    logger.warning(
                        "Repositorio local com alteracoes pendentes; pull remoto ignorado."
                    )
                    return True

                self._repo.remote("origin").pull()
                return True
            except GitCommandError as e:
                logger.error(f"Falha ao atualizar repo local a partir do GitHub: {e}")
                self.notification.error(f"Erro Git: {e}")
                return False

    def sync_game_saves(self, game_id: int, game_name: str, save_folder: str) -> bool:
        """Espelha saves locais no repo, grava metadado e faz push."""
        if not self.ensure_ready():
            return False

        try:
            game_dir_name = self._get_game_repo_folder_name(game_id, game_name)
            dest_dir = self._get_game_repo_dir(game_id, game_name)
            os.makedirs(dest_dir, exist_ok=True)

            mirrored = self._mirror_directory(
                save_folder,
                dest_dir,
                exclude_names={self.GAME_SYNC_META_FILENAME},
            )

            meta_relative_path = self._get_game_sync_meta_relative_path(
                game_id, game_name
            )
            meta_exists = os.path.isfile(
                os.path.join(self._repo_path, meta_relative_path)
            )
            meta_written = False
            synced_at = self._current_sync_timestamp()

            if mirrored or not meta_exists:
                meta_written = self._write_game_sync_meta(game_id, game_name, synced_at)

            if not mirrored and not meta_written:
                logger.debug(f"Nenhuma alteracao detectada para '{game_name}'")
                return True

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            commit_paths = [os.path.join("Saves", game_dir_name)]
            if meta_written:
                commit_paths.append(meta_relative_path)
            commit_msg = f"Auto-sync: {game_name} saves ({timestamp})"
            return self.sync_paths(commit_paths, commit_msg)
        except GitCommandError as e:
            logger.error(f"Erro Git ao sincronizar '{game_name}': {e}")
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
        """Compara save local e save do repo para detectar restauracao ou conflito."""
        if not self.ensure_ready():
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

            target_dir = os.path.join(
                self._repo_path or "",
                "Saves",
                self._get_game_repo_folder_name(game_id, new_game_name),
            )
            current_dir = None
            legacy_old_dir = self._get_legacy_game_repo_dir(old_game_name)
            legacy_new_dir = self._get_legacy_game_repo_dir(new_game_name)

            for candidate in [target_dir, legacy_old_dir, legacy_new_dir]:
                if os.path.isdir(candidate):
                    current_dir = candidate
                    break

            if not current_dir:
                return True

            commit_paths = []
            if current_dir != target_dir:
                os.makedirs(os.path.dirname(target_dir), exist_ok=True)
                shutil.move(current_dir, target_dir)
                commit_paths.extend(
                    [
                        os.path.relpath(target_dir, self._repo_path),
                        os.path.relpath(current_dir, self._repo_path),
                    ]
                )
            else:
                commit_paths.append(os.path.relpath(target_dir, self._repo_path))

            self._write_game_sync_meta(
                game_id,
                new_game_name,
                self._current_sync_timestamp(),
            )
            commit_paths.append(
                self._get_game_sync_meta_relative_path(game_id, new_game_name)
            )

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return self.sync_paths(
                commit_paths,
                f"Save mapping atualizado: {new_game_name} ({timestamp})",
            )

    def get_game_sync_metadata(self, game_id: int, game_name: str) -> Optional[dict]:
        with self._lock:
            if not self.ensure_ready():
                return None

            meta_path = os.path.join(
                self._repo_path,
                self._get_game_sync_meta_relative_path(game_id, game_name),
            )
            if not os.path.isfile(meta_path):
                return None

            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                logger.error(f"Falha ao ler metadado de sync de '{game_name}': {e}")
                return None

    def read_json(self, relative_path: str) -> Optional[dict]:
        with self._lock:
            if not self.ensure_ready():
                return None

            target = os.path.join(self._repo_path, relative_path)
            if not os.path.isfile(target):
                return None

            try:
                with open(target, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError) as e:
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

            target = os.path.join(self._repo_path, relative_path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)

            return self.sync_paths([relative_path], commit_message)

    def sync_paths(self, relative_paths: list[str], commit_message: str) -> bool:
        with self._lock:
            if not self.ensure_ready():
                return False

            try:
                cleaned_paths = [path.replace("\\", "/") for path in relative_paths]
                self._repo.git.add("-A", "--", *cleaned_paths)

                status = self._repo.git.status("--porcelain", "--", *cleaned_paths)
                if not status.strip():
                    logger.debug("Nenhuma alteracao staged para commit")
                    return True

                self._repo.index.commit(commit_message)
                self._repo.remote("origin").push()
                logger.info(f"Commit enviado ao GitHub: {commit_message}")
                return True
            except GitCommandError as e:
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

    def _get_game_repo_folder_name(self, game_id: int, game_name: str) -> str:
        del game_name
        return f"game_{game_id}"

    def _get_legacy_game_repo_dir(self, game_name: str) -> str:
        return os.path.join(
            self._repo_path or "", "Saves", sanitize_filename(game_name)
        )

    def _get_game_repo_dir(self, game_id: int, game_name: str) -> str:
        target_dir = os.path.join(
            self._repo_path or "",
            "Saves",
            self._get_game_repo_folder_name(game_id, game_name),
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
        return os.path.join(
            "Saves",
            self._get_game_repo_folder_name(game_id, game_name),
            self.GAME_SYNC_META_FILENAME,
        )

    def _write_game_sync_meta(
        self, game_id: int, game_name: str, synced_at: str
    ) -> bool:
        meta_path = os.path.join(
            self._repo_path,
            self._get_game_sync_meta_relative_path(game_id, game_name),
        )
        payload = {
            "game_id": game_id,
            "game_name": game_name,
            "synced_at_utc": synced_at,
        }
        os.makedirs(os.path.dirname(meta_path), exist_ok=True)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")
        return True

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

        for dirpath, _, filenames in os.walk(path):
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

        for _, _, filenames in os.walk(path):
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

    def _inject_token(self, url: str, token: str) -> str:
        """Insere token de autenticacao na URL do GitHub."""
        if url.startswith("https://"):
            return url.replace("https://", f"https://x-access-token:{token}@")
        return url

    def _resolve_repo_config(self) -> tuple[str, str]:
        """Normaliza URL remota e nome da pasta local do repo."""
        repo_url = str(self.settings.get("github_repo_url", "") or "").strip()
        repo_name = str(self.settings.get("github_repo_name", "") or "").strip()

        if self._looks_like_repo_url(repo_name) and not self._looks_like_repo_url(
            repo_url
        ):
            repo_url, repo_name = repo_name, repo_url

        repo_url = self._normalize_repo_url(repo_url)

        if not repo_name or self._looks_like_repo_url(repo_name):
            repo_name = self._extract_repo_name(repo_name or repo_url)

        return repo_url, sanitize_filename(repo_name or "saves_repo")

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

    def shutdown(self):
        """Limpeza ao encerrar."""
        self._initialized = False
        self._repo = None

    def _ensure_git_available(self) -> bool:
        if self._git_runtime_checked and self._git_executable:
            return True

        bundled_git = self._find_bundled_git_executable()
        if bundled_git:
            try:
                refresh(bundled_git)
                self._git_executable = bundled_git
                self._git_runtime_checked = True
                logger.info(f"Git embutido detectado: {bundled_git}")
                return True
            except (GitCommandNotFound, OSError) as e:
                logger.warning(f"Falha ao ativar Git embutido '{bundled_git}': {e}")

        try:
            refresh()
            self._git_executable = "git"
            self._git_runtime_checked = True
            logger.info("Git do sistema detectado")
            return True
        except GitCommandNotFound:
            self._git_executable = ""
            self._git_runtime_checked = False
            logger.error("Nenhum executavel Git disponivel")
            self.notification.error(
                "Git nao encontrado. Para producao, empacote o PortableGit junto do launcher "
                "ou instale o Git no Windows."
            )
            return False

    def _find_bundled_git_executable(self) -> str:
        runtime_roots = []

        if getattr(sys, "frozen", False):
            runtime_roots.append(os.path.dirname(os.path.abspath(sys.executable)))

        for root in [RESOURCE_DIR, BASE_DIR]:
            if root and root not in runtime_roots:
                runtime_roots.append(root)

        relative_candidates = [
            os.path.join("vendor", "PortableGit", "cmd", "git.exe"),
            os.path.join("vendor", "PortableGit", "bin", "git.exe"),
            os.path.join("PortableGit", "cmd", "git.exe"),
            os.path.join("PortableGit", "bin", "git.exe"),
        ]

        for root in runtime_roots:
            for relative_path in relative_candidates:
                candidate = os.path.join(root, relative_path)
                if os.path.isfile(candidate):
                    return candidate

        return ""
