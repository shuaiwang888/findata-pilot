import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse


router = APIRouter()


@router.get("/files/{filename}")
def get_file(filename: str):
    base = Path(os.environ.get("DATA_AGENT_OUTPUT_DIR", "outputs/tables")).resolve()
    target = (base / filename).resolve()
    if base not in target.parents or not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target)
