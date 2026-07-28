"""
main.py (NL-to-SQL Service)

WHY THIS FILE EXISTS:
Wires nlsql_generator.py into an HTTP API, same role as the Schema Service's
main.py. Runs on port 5002 -- each service gets its own port, keeping them
independently runnable/deployable.
"""

from fastapi import FastAPI, HTTPException
import requests

from models import NLToSQLRequest, NLToSQLResponse
from nlsql_generator import generate_sql

app = FastAPI(
    title="QueryMind - NL-to-SQL Service",
    description="Given a plain-English question and a DB connection string, returns generated SQL.",
    version="0.1.0",
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "nlsql-service"}


@app.post("/generate-sql", response_model=NLToSQLResponse)
def generate_sql_endpoint(request: NLToSQLRequest):
    """
    Main endpoint. Takes a question + connection string, returns generated SQL.

    Error handling covers two distinct failure modes:
    - requests.RequestException: something went wrong calling the Schema
      Service (it's down, or the connection string it received was bad)
    - RuntimeError: our own config problem (e.g. missing GEMINI_API_KEY)

    We deliberately keep these separate from generic Exception handling so
    that unexpected bugs still surface as loud 500 errors during development,
    rather than being silently swallowed into a generic error message.
    """
    try:
        return generate_sql(request)
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach Schema Service or it returned an error: {str(e)}"
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
