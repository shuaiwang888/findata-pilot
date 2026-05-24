from pydantic import BaseModel, Field
from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

from app.agent.executor import execute_query
from app.agent.streaming import stream_query


router = APIRouter()


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1)
    page: str = "1"
    limit: str = "100"
    save: bool = True


@router.post("/chat")
def chat(request: ChatRequest):
    result = execute_query(
        query=request.query,
        page=request.page,
        limit=request.limit,
        save=request.save,
    )
    return JSONResponse(content=result.payload, status_code=result.status_code)


@router.post("/chat/stream")
def chat_stream(request: ChatRequest):
    return StreamingResponse(
        stream_query(
            query=request.query,
            page=request.page,
            limit=request.limit,
            save=request.save,
        ),
        media_type="text/event-stream",
    )
