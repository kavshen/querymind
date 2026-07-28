"""
models.py (Execution Service)

WHY THIS FILE EXISTS:
Same pattern as the other two services -- declare the request/response shape
once, let FastAPI validate and document it automatically.
"""

from pydantic import BaseModel, Field
from typing import Any


class ExecutionRequest(BaseModel):
    """
    What the client sends us: a SQL query to run, against which database,
    and whether this is a "preview" (cheap, capped at 5 rows) or a full run.

    WHY preview_mode EXISTS AS A SEPARATE FLAG (rather than the caller just
    adding "LIMIT 5" to their SQL themselves):
    The agent we build in the next step needs to test-run a freshly generated
    query BEFORE trusting it enough to show a user -- e.g. "did this even run
    without error, does the shape of the result look sane." Rewriting
    arbitrary SQL to inject a LIMIT is fragile (breaks on queries that
    already have ORDER BY, subqueries, etc.), so instead we handle row-
    limiting entirely on the Python side, after execution -- see
    query_executor.py for why that's safe.
    """
    sql: str = Field(..., description="The SQL query to execute")
    connection_string: str = Field(..., description="SQLAlchemy-style DB connection string")
    preview_mode: bool = Field(
        default=False,
        description="If true, caps results at 5 rows regardless of the query"
    )


class ExecutionResponse(BaseModel):
    """What we send back: the actual query results, plus useful metadata."""
    columns: list[str]
    rows: list[list[Any]]          # each inner list = one row's values, in column order
    row_count: int                  # how many rows we're actually returning
    truncated: bool                 # True if there were MORE rows than we returned
    execution_time_ms: float