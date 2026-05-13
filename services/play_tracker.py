"""
Servico de rastreamento de tempo de jogo.
Detecta quando um processo e iniciado, atualiza o banco em tempo real
e encerra a sessao quando o processo termina.
"""

import os
import time
from datetime import datetime
from typing import Dict, Optional, Tuple

import psutil
from PySide6.QtCore import QObject, QThread, Signal

from database.db_manager import DatabaseManager
from database.models import Game as GameModel, PlaySession as SessionModel
from utils.logger import get_logger

logger = get_logger("PlayTracker")


class _TrackerThread(QThread):
    """Thread que monitora processos ativos."""

    session_progress = Signal(int, float)
    session_ended = Signal(int, float)

    def __init__(self):
        super().__init__()
        self._active: Dict[int, dict] = {}
        self._running = True

    def register_launch(
        self,
        game_id: int,
        pid: int,
        exe_name: str,
        session_id: Optional[int],
        base_total: float,
    ):
        self._active[game_id] = {
            "pid": pid,
            "start_time": time.time(),
            "exe_name": exe_name.lower(),
            "session_id": session_id,
            "base_total": base_total,
        }
        logger.info(f"Jogo {game_id} registrado - PID {pid}")

    def get_active_snapshot(self) -> Dict[int, dict]:
        return {gid: dict(info) for gid, info in self._active.items()}

    def run(self):
        while self._running:
            ended = []
            now = time.time()

            for gid, info in list(self._active.items()):
                pid = info["pid"]
                try:
                    proc = psutil.Process(pid)
                    if proc.status() == psutil.STATUS_ZOMBIE:
                        raise psutil.NoSuchProcess(pid)
                    duration = max(0.0, now - info["start_time"])
                    self.session_progress.emit(gid, duration)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    duration = max(0.0, now - info["start_time"])
                    ended.append((gid, duration))
                    logger.info(f"Jogo {gid} encerrou - {duration:.0f}s")

            for gid, duration in ended:
                self._active.pop(gid, None)
                self.session_ended.emit(gid, duration)

            self.msleep(1000)

    def is_running(self, game_id: int) -> bool:
        return game_id in self._active

    def stop(self):
        self._running = False
        self.wait(5000)


class PlayTracker(QObject):
    """Servico principal de rastreamento."""

    game_launched = Signal(int)
    game_closed = Signal(int, float)
    playtime_updated = Signal(int, float)

    PROGRESS_PERSIST_INTERVAL_S = 5.0

    def __init__(self, db: DatabaseManager):
        super().__init__()
        self.db = db
        self._thread = _TrackerThread()
        self._live_sessions: Dict[int, dict] = {}
        self._thread.session_progress.connect(self._on_session_progress)
        self._thread.session_ended.connect(self._on_session_ended)

    def start(self):
        self._thread.start()
        logger.info("PlayTracker iniciado")

    def stop(self):
        now = time.time()
        for gid, info in list(self._live_sessions.items()):
            duration = max(0.0, now - info["start_timestamp"])
            self._persist_session_state(gid, duration, ended=True)
        self._thread.stop()

    def launch_game(self, game_id: int, exe_path: str) -> Tuple[bool, str]:
        """Inicia o jogo e registra o processo quando possivel."""
        if self._thread.is_running(game_id):
            return False, "Este jogo ja esta em execucao."

        cwd = os.path.dirname(exe_path) or None

        try:
            proc = psutil.Popen([exe_path], cwd=cwd)
            time.sleep(0.8)
            if proc.poll() is not None:
                return False, (
                    f"O processo fechou imediatamente (codigo {proc.returncode})."
                )

            return self._register_running_game(
                game_id,
                exe_path,
                proc.pid,
                "Jogo iniciado com sucesso.",
            )
        except Exception as e:
            logger.warning(f"Lancamento direto falhou para jogo {game_id}: {e}")

            fallback_ok, fallback_pid, fallback_message = (
                self._launch_with_windows_shell(exe_path)
            )
            if fallback_ok and fallback_pid:
                return self._register_running_game(
                    game_id,
                    exe_path,
                    fallback_pid,
                    "Jogo aberto pelo Windows e rastreado com sucesso.",
                )
            if fallback_ok:
                self.game_launched.emit(game_id)
                logger.info(
                    f"Jogo {game_id} iniciado via fallback do Windows sem PID rastreavel."
                )
                return True, fallback_message

            logger.error(f"Falha ao iniciar jogo {game_id}: {fallback_message}")
            return False, fallback_message

    def is_running(self, game_id: int) -> bool:
        return self._thread.is_running(game_id)

    def _register_running_game(
        self,
        game_id: int,
        exe_path: str,
        pid: int,
        message: str,
    ) -> Tuple[bool, str]:
        session_id, base_total = self._create_live_session(game_id)
        self._live_sessions[game_id] = {
            "session_id": session_id,
            "base_total": base_total,
            "start_timestamp": time.time(),
            "started_at": datetime.utcnow(),
            "last_persisted_duration": 0.0,
        }
        self._thread.register_launch(
            game_id,
            pid,
            os.path.basename(exe_path),
            session_id,
            base_total,
        )
        self.game_launched.emit(game_id)
        self.playtime_updated.emit(game_id, base_total)
        logger.info(f"Jogo {game_id} lancado com PID {pid}")
        return True, message

    def _launch_with_windows_shell(
        self, exe_path: str
    ) -> Tuple[bool, Optional[int], str]:
        if os.name != "nt":
            return False, None, "Falha ao abrir o executavel no sistema atual."

        target_path = os.path.normcase(os.path.abspath(exe_path))
        target_name = os.path.basename(exe_path).lower()
        before = {proc.pid for proc in psutil.process_iter(["pid"])}

        try:
            os.startfile(exe_path)
            time.sleep(1.5)
        except OSError as e:
            return False, None, f"Windows nao conseguiu abrir o jogo: {e}"

        candidate = None
        for proc in psutil.process_iter(["pid", "name", "exe", "create_time"]):
            try:
                info = proc.info
                if info["pid"] in before:
                    continue

                exe = os.path.normcase(info.get("exe") or "")
                name = (info.get("name") or "").lower()
                if exe == target_path or name == target_name:
                    if candidate is None or (info.get("create_time") or 0) > (
                        candidate.info.get("create_time") or 0
                    ):
                        candidate = proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if candidate:
            return (
                True,
                candidate.pid,
                "Jogo aberto pelo Windows com rastreamento ativo.",
            )

        return (
            True,
            None,
            (
                "Jogo aberto pelo Windows, mas nao consegui vincular o processo para "
                "acompanhar as horas em tempo real."
            ),
        )

    def _create_live_session(self, game_id: int) -> Tuple[int, float]:
        started_at = datetime.utcnow()
        with self.db.session() as sess:
            game = sess.get(GameModel, game_id)
            base_total = (game.total_playtime_seconds or 0.0) if game else 0.0
            if game:
                game.last_played = started_at

            session = SessionModel(
                game_id=game_id,
                started_at=started_at,
                ended_at=None,
                duration_seconds=0.0,
            )
            sess.add(session)
            sess.flush()
            return session.id, base_total

    def _on_session_progress(self, game_id: int, duration: float):
        info = self._live_sessions.get(game_id)
        if not info:
            return

        total = info["base_total"] + duration
        self.playtime_updated.emit(game_id, total)

        if (
            duration - info["last_persisted_duration"]
            >= self.PROGRESS_PERSIST_INTERVAL_S
        ):
            self._persist_session_state(game_id, duration, ended=False)

    def _on_session_ended(self, game_id: int, duration: float):
        self._persist_session_state(game_id, duration, ended=True)
        self.game_closed.emit(game_id, duration)

    def _persist_session_state(self, game_id: int, duration: float, ended: bool):
        info = self._live_sessions.get(game_id)
        if not info:
            return

        ended_at = datetime.utcnow() if ended else None
        total = info["base_total"] + duration

        with self.db.session() as sess:
            session = sess.get(SessionModel, info["session_id"])
            if session:
                session.duration_seconds = duration
                if ended:
                    session.ended_at = ended_at

            game = sess.get(GameModel, game_id)
            if game:
                game.total_playtime_seconds = total
                if ended:
                    game.last_played = ended_at

        info["last_persisted_duration"] = duration
        self.playtime_updated.emit(game_id, total)

        if ended:
            self._live_sessions.pop(game_id, None)
