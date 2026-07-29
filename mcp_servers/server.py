"""
server.py (MCP Server)

WHY THIS FILE EXISTS:
Up until now, chaining the three services together (Schema -> NL-to-SQL ->
Execution) has been something YOU did manually -- calling one, copying its
output, pasting it into the next call. That's exactly the job an agent
should do automatically.

For an LLM agent to call our services itself, it needs more than a raw REST
API -- it needs each capability described in a structured way it can
understand: what does this tool do, what inputs does it need, what does it
return. That's exactly what MCP (Model Context Protocol) standardizes. This
file wraps our three existing REST services as three MCP "tools" -- the
LangGraph agent we build next will connect to this server and be able to
call get_schema / generate_sql / execute_query on its own, deciding when and
in what order, instead of us hardcoding that order by hand.

IMPORTANT DESIGN CHOICE: these tools are thin wrappers -- they don't
reimplement any logic. They just call the REST endpoints you already built
and tested (ports 5001/5002/5003). This means MCP is purely an additional
INTERFACE on top of working services, not a rewrite -- if something breaks,
you can always fall back to testing the plain REST endpoints directly, like
we've been doing all along.

We use FastMCP (part of the official `mcp` Python SDK) because it lets us
define a tool as a plain Python function with a docstring -- FastMCP handles
all the MCP protocol plumbing (tool discovery, schema generation from type
hints, etc.) for us.
"""

import os
import requests
from mcp.server.fastmcp import FastMCP

SCHEMA_SERVICE_URL = os.environ.get("SCHEMA_SERVICE_URL", "http://localhost:5001")
NLSQL_SERVICE_URL = os.environ.get("NLSQL_SERVICE_URL", "http://localhost:5002")
EXECUTION_SERVICE_URL = os.environ.get("EXECUTION_SERVICE_URL", "http://localhost:5003")

# The name "QueryMind" here is what shows up when an MCP client (like the
# LangGraph agent, or Claude Desktop, or the MCP Inspector) lists available
# servers -- it's a human-readable label, not something with functional effect.
mcp = FastMCP("QueryMind")


@mcp.tool()
def get_schema(connection_string: str) -> dict:
    """
    Fetches the full schema (tables, columns, primary keys, foreign keys)
    for a database. Use this FIRST, before generating SQL, so you know what
    tables and columns actually exist and how they relate to each other.

    Args:
        connection_string: SQLAlchemy-style connection string for the target database.

    Returns:
        A dict with database_type, table_count, and a list of tables with
        their columns, primary keys, and foreign key relationships.
    """
    response = requests.post(
        f"{SCHEMA_SERVICE_URL}/schema",
        json={"connection_string": connection_string},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


@mcp.tool()
def generate_sql(question: str, connection_string: str) -> dict:
    """
    Converts a plain-English question into a SQL query, using the real
    schema of the target database. The generated SQL is validated to be
    syntactically correct and read-only (no INSERT/UPDATE/DELETE/DROP)
    before being returned.

    Args:
        question: A plain-English question about the data (e.g. "how many customers are there").
        connection_string: SQLAlchemy-style connection string for the target database.

    Returns:
        A dict with the generated_sql, database_type, and whether the
        result came from cache.
    """
    response = requests.post(
        f"{NLSQL_SERVICE_URL}/generate-sql",
        json={"question": question, "connection_string": connection_string},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


@mcp.tool()
def execute_query(sql: str, connection_string: str, preview_mode: bool = False) -> dict:
    """
    Executes a SQL query against a database and returns the results.

    Use preview_mode=True to cheaply test a freshly generated query first
    (returns at most 5 rows) before committing to a full run -- this lets
    you sanity-check that a query works and looks reasonable without paying
    the cost of a large result set.

    Args:
        sql: The SQL query to run.
        connection_string: SQLAlchemy-style connection string for the target database.
        preview_mode: If True, caps results at 5 rows regardless of the query. Defaults to False.

    Returns:
        A dict with columns, rows, row_count, truncated (whether more rows
        existed beyond what was returned), and execution_time_ms.
    """
    response = requests.post(
        f"{EXECUTION_SERVICE_URL}/execute",
        json={"sql": sql, "connection_string": connection_string, "preview_mode": preview_mode},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    # WHY stdio transport: this is the standard way an MCP client (like the
    # LangGraph agent we build next, or Claude Desktop) launches and talks
    # to an MCP server -- as a subprocess, communicating over stdin/stdout,
    # rather than as a separately-running network server. FastMCP handles
    # the protocol details; we just need to call .run().
    mcp.run(transport="stdio")