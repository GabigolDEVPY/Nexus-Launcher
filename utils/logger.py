"""
Sistema de logging centralizado.
"""
import logging
import os
import sys
from datetime import datetime
from core.constants import LOG_DIR, prepare_runtime_environment

prepare_runtime_environment()
os.makedirs(LOG_DIR, exist_ok=True)

_log_file = os.path.join(
    LOG_DIR, f"nexus_{datetime.now().strftime('%Y%m%d')}.log"
)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # File handler
    fh = logging.FileHandler(_log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)

    fmt = logging.Formatter(
        "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    fh.setFormatter(fmt)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger
