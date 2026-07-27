"""
main.py (Schema Service)

WHY THIS FILE EXISTS:
This is the FastAPI entrypoint -- it wires together models.py (the request/
response shapes) and schema_inspector.py (the actual logic) into an HTTP API
that other services (NL-to-SQL, frontend, etc.) can call.

We run this on port 5001, separate from the Week 1 scaffold's port 8000,
since in the target architecture each service is independent.
"""

from fastapi import FastAPI, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from models import SchemaRequest, SchemaResponse
from schema_inspector import get_schema

app = FastAPI(
    title="QueryMind - Schema Service",
    description="Given a DB connection string, returns its full schema as structured JSON.",
    version="0.1.0",
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "schema-service"}


@app.post("/schema", response_model=SchemaResponse)
def read_schema(request: SchemaRequest):
    """
    Main endpoint. Takes a connection string, returns the DB's schema.
    Catches SQLAlchemyError (bad password, unreachable host, etc.) and
    converts it into a clean 400 response instead of a raw traceback.
    """
    try:
        return get_schema(request.connection_string)
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not connect to or read database: {str(e)}"
        )
