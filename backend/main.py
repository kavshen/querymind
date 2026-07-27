"""
QueryMind — Week 1 scaffold.

This is a placeholder entrypoint just to prove the environment works end to end:
FastAPI app running, able to reach Postgres/MySQL/Redis/Kafka defined in docker-compose.yml.

In Phase 2, this file gets replaced by backend/schema_service/main.py (port 5001).
"""

from fastapi import FastAPI
from datetime import datetime, timezone

app = FastAPI(title="QueryMind - Week 1 Scaffold")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "querymind-scaffold",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/")
def root():
    return {"message": "QueryMind backend is alive. Try GET /health"}
