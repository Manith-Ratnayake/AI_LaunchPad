from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from inference.orchestrator import answer_question


app = FastAPI(title="Annual Report RAG API")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class QuestionRequest(BaseModel):
    question: str


@app.get("/health")
def health():
    return {
        "status": "ok"
    }


@app.post("/query")
def query(request: QuestionRequest):
    try:
        return answer_question(request.question)

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )