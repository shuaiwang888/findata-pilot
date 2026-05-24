from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.utils.env import load_env


load_env()

try:
    import pymysql
except ModuleNotFoundError:  # pragma: no cover
    pymysql = None


def mysql_config(database: str | None = None) -> dict[str, Any]:
    return {
        "host": os.environ.get("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.environ.get("MYSQL_PORT", "3306")),
        "user": os.environ.get("MYSQL_USER", "root"),
        "password": os.environ.get("MYSQL_PASSWORD", ""),
        "database": database if database is not None else os.environ.get("MYSQL_DATABASE", "data_agent"),
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": False,
    }


def get_connection(database: str | None = None):
    if pymysql is None:
        raise ModuleNotFoundError("pymysql is not installed")
    return pymysql.connect(**mysql_config(database=database))


def check_mysql() -> tuple[bool, str | None]:
    if pymysql is None:
        return False, "pymysql is not installed"
    try:
        with get_connection() as conn:
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
    with get_connection(database=None) as conn:
        try:
            with conn.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
