from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.agent.executor import execute_query
from app.agent.streaming import stream_query


router = APIRouter()


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1)
    page: int = Field(default=1, ge=1, le=10_000)
    limit: int = Field(default=100, ge=1, le=500)
    save: bool = True


@router.post("/chat")
def chat(request: ChatRequest):
    result = execute_query(
        query=request.query,
        page=str(request.page),
        limit=str(request.limit),
        save=request.save,
    )
    return JSONResponse(content=result.payload, status_code=result.status_code)


@router.post("/chat/stream")
def chat_stream(request: ChatRequest, req: Request):
    return StreamingResponse(
        stream_query(
            query=request.query,
            page=str(request.page),
            limit=str(request.limit),
            save=request.save,
            request=req,
        ),
        media_type="text/event-stream",
    )
