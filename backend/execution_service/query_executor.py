"""
query_executor.py

WHY THIS FILE EXISTS:
This is where SQL actually gets run against a real database. Everything
before this point (Schema Service, NL-to-SQL Service) only ever READ schema
metadata or generated text -- this is the first point in the whole system
that touches real data. That's exactly why it gets the most defensive code
in the project.

THREE SAFETY RAILS, AND WHY EACH ONE EXISTS:

1. ROW LIMIT (hard cap, always applied):
   We never return more than MAX_ROWS to a caller, no matter what SQL was
   run. WHY ON THE PYTHON SIDE, NOT BY REWRITING THE SQL: rewriting
   arbitrary SQL to inject "LIMIT N" is fragile -- it can silently break
   queries that already have their own ORDER BY, UNION, or subqueries. It's
   much safer to let the query run as-written and simply stop consuming
   rows from the result set once we hit our cap. This is a standard,
   well-understood pattern (server-side cursors / fetchmany), not a hack.

2. PREVIEW MODE (opt-in, much smaller cap):
   Lets a caller (in Phase 4, the agent) cheaply test "does this query even
   run, does the shape look right" without paying the cost of a full result
   set.

3. TIMEOUT:
   Protects against a runaway query (e.g. an accidental cross join, or a
   query against a huge table with no WHERE clause) hanging the service
   indefinitely.
   HONEST LIMITATION, WORTH UNDERSTANDING RATHER THAN HIDING: the timeout
   here stops OUR code from waiting past N seconds. Depending on the
   database driver, the underlying query may or may not actually be
   cancelled server-side when we stop waiting for it -- true guaranteed
   query cancellation is DB-specific (e.g. Postgres's `statement_timeout`
   setting is the "real" fix, and would be the next thing to add for a
   production version of this service). Flagging this honestly is exactly
   the kind of nuance worth being able to explain in an interview.
"""

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from models import ExecutionRequest, ExecutionResponse

MAX_ROWS = 1000          # hard cap for a full (non-preview) run
PREVIEW_ROWS = 5          # cap when preview_mode=True
QUERY_TIMEOUT_SECONDS = 10

# A small reusable thread pool for running the blocking DB call. WHY A THREAD
# (not just calling the DB driver directly): the DB driver call is
# synchronous/blocking -- there's no built-in way to say "give up waiting
# after N seconds" on a plain function call. Running it in a worker thread
# lets us use .result(timeout=...) to enforce that limit from the outside.
_executor_pool = ThreadPoolExecutor(max_workers=4)


class QueryExecutionError(Exception):
    """Raised for any failure during query execution: bad SQL, timeout, connection issues."""
    pass


def _run_query_blocking(connection_string: str, sql: str, row_cap: int):
    """
    The actual blocking database call. Runs in a worker thread so the caller
    can enforce a timeout around it (see execute_query below).
    """
    engine = create_engine(connection_string)
    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql))

            columns = list(result.keys())

            # fetchmany(row_cap) pulls at most row_cap rows from the
            # underlying result cursor -- it does NOT require the full
            # result set to already exist in memory, which is what makes
            # this safe even against a query that could technically match
            # millions of rows.
            fetched_rows = result.fetchmany(row_cap)

            # Check if there was at least one more row beyond our cap, so we
            # can honestly report truncated=True/False rather than guessing.
            has_more = result.fetchone() is not None

            rows_as_lists = [list(row) for row in fetched_rows]

            return columns, rows_as_lists, has_more
    finally:
        engine.dispose()


def execute_query(request: ExecutionRequest) -> ExecutionResponse:
    """
    Main entry point. Runs the SQL with row-limiting and timeout protection,
    and returns a structured result.
    """
    row_cap = PREVIEW_ROWS if request.preview_mode else MAX_ROWS

    start_time = time.perf_counter()

    future = _executor_pool.submit(_run_query_blocking, request.connection_string, request.sql, row_cap)

    try:
        columns, rows, has_more = future.result(timeout=QUERY_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        raise QueryExecutionError(
            f"Query exceeded the {QUERY_TIMEOUT_SECONDS}-second timeout and was abandoned."
        )
    except SQLAlchemyError as e:
        raise QueryExecutionError(f"Database error while executing query: {str(e)}")

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    return ExecutionResponse(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=has_more,
        execution_time_ms=round(elapsed_ms, 2),
    )