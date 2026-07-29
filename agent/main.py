"""
main.py (Agent Service)

WHY THIS FILE EXISTS:
The agent itself (agent.py) is pure Python logic -- no HTTP, no FastAPI.
This file wraps it in an HTTP API (port 5004) so the frontend we build in
Phase 5 has a single, clean endpoint to call: POST /ask, with a question
and a connection string, and get back a real answer. The frontend doesn't
need to know about Schema Service, NL-to-SQL Service, or Execution Service
at all -- it just talks to this one endpoint and gets results.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agent import run_agent

app = FastAPI(
    title="QueryMind - Agent",
    description="Ask a plain-English question about any database and get real results back.",
    version="0.1.0",
)


class AskRequest(BaseModel):
    question: str
    connection_string: str


@app.get("/health")
def health():
    return {"status": "ok", "service": "agent"}


@app.post("/ask")
def ask(request: AskRequest):
    """
    The single endpoint the frontend will call.
    Takes a question + connection string, runs the full agent loop,
    returns the generated SQL + query results.
    """
    try:
        return run_agent(request.question, request.connection_string)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Agent error: {str(e)}")