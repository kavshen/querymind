"""
main.py (Execution Service)

WHY THIS FILE EXISTS:
Wires query_executor.py into an HTTP API. Runs on port 5003 -- the third and
final "leaf" service (Schema=5001, NL-to-SQL=5002, Execution=5003) that the
Phase 4 agent will orchestrate.

WE DELIBERATELY DO NOT RE-VALIDATE SQL SAFETY HERE:
The NL-to-SQL service already runs sql_validator.py (syntax + read-only
check) before ever returning SQL to a caller. We could duplicate that check
here too, but choosing not to is intentional: this service's job is narrowly
"execute whatever valid SQL you're given, safely (rows/timeout)" -- it trusts
that safety-of-content was already handled upstream. This keeps each
service's responsibility narrow and avoids two services quietly drifting out
of sync on what "safe SQL" means.
"""

from fastapi import FastAPI, HTTPException

from models import ExecutionRequest, ExecutionResponse
from query_executor import execute_query, QueryExecutionError

app = FastAPI(
    title="QueryMind - Execution Service",
    description="Executes SQL queries with row-limit and timeout safety rails.",
    version="0.1.0",
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "execution-service"}


@app.post("/execute", response_model=ExecutionResponse)
def execute_endpoint(request: ExecutionRequest):
    try:
        return execute_query(request)
    except QueryExecutionError as e:
        raise HTTPException(status_code=400, detail=str(e))