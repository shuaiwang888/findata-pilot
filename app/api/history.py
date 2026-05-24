import os
from pathlib import Path

from fastapi import APIRouter, Query

from app.storage.repository import clear_query_runs, get_query_run, list_query_runs


router = APIRouter()


@router.get("/history")
def history(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    return {"items": list_query_runs(limit=limit, offset=offset)}


@router.get("/history/{run_id}")
def history_item(run_id: int):
    item = get_query_run(run_id)
    return {"item": item}


@router.delete("/history")
def clear_history(delete_files: bool = Query(True)):
    counts = clear_query_runs()
    deleted_files = 0
    if delete_files:
        output_dir = Path(os.environ.get("DATA_AGENT_OUTPUT_DIR", "outputs/tables"))
        if output_dir.exists():
            for path in output_dir.iterdir():
                if path.is_file() and path.suffix.lower() in {".csv", ".parquet"}:
                    path.unlink()
                    deleted_files += 1
    return {"ok": True, "deleted": {**counts, "files": deleted_files}}
