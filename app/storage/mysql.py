from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from app.utils.env import load_env

load_env()

try:
    import pymysql
except ModuleNotFoundError:  # pragma: no cover
    pymysql = None

_POOL: list[Any] = []
_POOL_LOCK = threading.Lock()
_POOL_MAX = 5


def mysql_config(database: str | None = None) -> dict[str, Any]:
    config = {
        "host": os.environ.get("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.environ.get("MYSQL_PORT", "3306")),
        "user": os.environ.get("MYSQL_USER", "root"),
        "password": os.environ.get("MYSQL_PASSWORD", ""),
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": False,
        "connect_timeout": 10,
        "read_timeout": 30,
        "write_timeout": 30,
    }
    db_name = os.environ.get("MYSQL_DATABASE", "data_agent") if database is None else database
    if db_name:
        config["database"] = db_name
    return config


def get_connection(database: str | None = None):
    if pymysql is None:
        raise ModuleNotFoundError("pymysql is not installed")

    with _POOL_LOCK:
        while _POOL:
            conn = _POOL.pop()
            try:
                conn.ping(reconnect=False)
                return conn
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass

    return pymysql.connect(**mysql_config(database=database))


def _return_to_pool(conn: Any) -> None:
    with _POOL_LOCK:
        if len(_POOL) < _POOL_MAX:
            try:
                conn.ping(reconnect=False)
                _POOL.append(conn)
                return
            except Exception:
                pass
        try:
            conn.close()
        except Exception:
            pass


@contextmanager
def pooled_connection(database: str | None = None):
    conn = get_connection(database=database)
    try:
        yield conn
    except Exception:
        conn.close()
        raise
    else:
        _return_to_pool(conn)


def close_pool() -> None:
    with _POOL_LOCK:
        while _POOL:
            conn = _POOL.pop()
            try:
                conn.close()
            except Exception:
                pass


def check_mysql() -> tuple[bool, str | None]:
    if pymysql is None:
        return False, "pymysql is not installed"
    try:
        with pooled_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 AS ok")
                cursor.fetchone()
        return True, None
    except Exception as exc:
        return False, str(exc)


def initialize_database(schema_path: str | None = None) -> None:
    if pymysql is None:
        raise ModuleNotFoundError("pymysql is not installed")
    path = Path(schema_path or Path(__file__).with_name("schema.sql"))
    sql = path.read_text(encoding="utf-8")
    statements = [stmt.strip() for stmt in sql.split(";") if stmt.strip()]
    with pooled_connection(database="") as conn:
        try:
            with conn.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
