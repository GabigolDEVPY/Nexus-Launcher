"""
Gerenciador de banco de dados — engine, sessões, migrações.
"""
import os
from contextlib import contextmanager
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from database.models import Base
from core.constants import DB_PATH, prepare_runtime_environment


class DatabaseManager:
    """Encapsula a engine SQLAlchemy e fornece sessões seguras."""

    def __init__(self, db_path: str = DB_PATH):
        prepare_runtime_environment()
        self._db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        db_url = f"sqlite:///{db_path}"
        self._engine = create_engine(
            db_url,
            echo=False,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )

        # Habilita WAL para melhor concorrência
        @event.listens_for(self._engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        self._SessionFactory = sessionmaker(bind=self._engine, expire_on_commit=False)
        self._create_tables()

    def _create_tables(self):
        Base.metadata.create_all(self._engine)

    @contextmanager
    def session(self) -> Session:
        """Context manager que garante commit/rollback/close."""
        sess = self._SessionFactory()
        try:
            yield sess
            sess.commit()
        except Exception:
            sess.rollback()
            raise
        finally:
            sess.close()

    def close(self):
        self._engine.dispose()
