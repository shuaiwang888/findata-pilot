import os

from fastapi import APIRouter

from app.storage.mysql import check_mysql


router = APIRouter()


@router.get("/health")
def health():
    mysql_ok, mysql_error = check_mysql()
    return {
        "ok": mysql_ok and bool(os.environ.get("IWENCAI_API_KEY")),
        "version": "0.2.0",
        "features": {"chat_stream": True, "llm_summary": True, "planner": True},
        "mysql": {"ok": mysql_ok, "database": os.environ.get("MYSQL_DATABASE", "data_agent"), "error": mysql_error},
        "iwencai_api_key_configured": bool(os.environ.get("IWENCAI_API_KEY")),
    }
