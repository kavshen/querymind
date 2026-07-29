"""
agent.py

WHY THIS FILE EXISTS:
This is the orchestrator that replaces the manual PowerShell chaining we did
in Phase 3/4 testing. Instead of YOU calling Schema -> NL-to-SQL -> Execution
in sequence, this agent does that reasoning itself:

1. Fetches the schema (always -- it needs real facts before generating SQL)
2. Generates SQL from the question + schema
3. Runs the SQL in preview mode first (sanity check: did it even run? does
   the shape look right?)
4. If preview succeeded -> run the full query and return results
5. If preview failed -> retry SQL generation with a more specific prompt
   (up to MAX_RETRIES times before giving up cleanly)

WHY LANGGRAPH SPECIFICALLY:
LangGraph models this as a directed graph where each node is a step, and
"which node to go to next" is decided by conditional edges (functions that
look at the current state and return the next node name). This makes the
retry loop -- and any future branches we add -- explicit and readable, rather
than buried in nested if/else logic. It's also the most widely-adopted
framework for production LLM agents right now, which is why it's worth
having in your portfolio.

WHY WE CALL THE REST SERVICES DIRECTLY (not through MCP here):
The MCP layer we built exists for EXTERNAL clients (Claude Desktop, other
agent frameworks) to discover and call our tools. For our OWN internal
agent, calling the REST endpoints directly is simpler, faster, and avoids
the overhead of spawning a subprocess just to call our own services. Both
approaches are valid and can coexist -- the MCP server stays available for
external use.
"""

import os
import requests
from pathlib import Path
from typing import TypedDict, Annotated
from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

# Load .env from the backend/ folder (one level up from agent/)
_env_path = Path(__file__).resolve().parent.parent / "backend" / ".env"
load_dotenv(dotenv_path=_env_path)

SCHEMA_URL = os.environ.get("SCHEMA_SERVICE_URL", "http://localhost:5001")
NLSQL_URL = os.environ.get("NLSQL_SERVICE_URL", "http://localhost:5002")
EXECUTION_URL = os.environ.get("EXECUTION_SERVICE_URL", "http://localhost:5003")

MAX_RETRIES = 2  # how many times to retry SQL generation if preview fails


# ── State ──────────────────────────────────────────────────────────────────────
# WHY TypedDict FOR STATE:
# LangGraph passes a "state" dict between every node in the graph. TypedDict
# lets us declare exactly what fields the state has with their types, so the
# graph is self-documenting and Python can type-check it. Every node reads
# from and writes to this same shared state object.

class AgentState(TypedDict):
    # Inputs (set once at the start, never changed)
    question: str
    connection_string: str

    # Populated by fetch_schema node
    schema: dict

    # Populated/updated by generate_sql node
    generated_sql: str
    retry_count: int
    last_error: str          # stores preview error message if we need to retry

    # Populated by full_execute node
    final_result: dict

    # Standard LangGraph messages list -- we use this to give the agent
    # a running log of what happened, useful for debugging
    messages: Annotated[list, add_messages]


# ── Nodes ──────────────────────────────────────────────────────────────────────

def fetch_schema(state: AgentState) -> AgentState:
    """
    Node 1: Always runs first. Fetches the real schema so the SQL generation
    node has actual table/column facts to work with instead of guessing.
    """
    response = requests.post(
        f"{SCHEMA_URL}/schema",
        json={"connection_string": state["connection_string"]},
        timeout=15,
    )
    response.raise_for_status()
    schema = response.json()

    print(f"[agent] Schema fetched: {schema['table_count']} tables found")

    return {
        **state,
        "schema": schema,
        "retry_count": 0,
        "last_error": "",
    }


def generate_sql(state: AgentState) -> AgentState:
    """
    Node 2: Converts the question into SQL, using the NL-to-SQL service.

    On a retry (retry_count > 0), we append the previous error to the
    question so the LLM knows what went wrong last time and can try a
    different approach. This is the key mechanism that makes the retry
    loop actually productive rather than just asking the same question
    again and hoping for a different answer.
    """
    question = state["question"]

    # On retry: give the LLM the previous error as context
    if state.get("retry_count", 0) > 0:
        question = (
            f"{question}\n\n"
            f"Note: A previous SQL attempt failed with this error: "
            f"{state['last_error']}. Please generate a corrected query."
        )
        print(f"[agent] Retry {state['retry_count']}: regenerating SQL with error context")

    response = requests.post(
        f"{NLSQL_URL}/generate-sql",
        json={
            "question": question,
            "connection_string": state["connection_string"],
        },
        timeout=30,
    )
    response.raise_for_status()
    result = response.json()

    print(f"[agent] Generated SQL: {result['generated_sql']}")

    return {**state, "generated_sql": result["generated_sql"]}


def preview_execute(state: AgentState) -> AgentState:
    """
    Node 3: Runs the generated SQL in preview mode (max 5 rows).

    WHY PREVIEW BEFORE FULL EXECUTION:
    Running with a small row cap first means if the SQL is wrong (bad
    column name, broken JOIN, etc.), we find out cheaply -- without
    potentially pulling thousands of rows from the database before
    discovering the query was broken. This is the same principle as
    "fail fast" in software engineering.

    We store any error in state["last_error"] so Node 2 can use it
    as context if it needs to retry.
    """
    try:
        response = requests.post(
            f"{EXECUTION_URL}/execute",
            json={
                "sql": state["generated_sql"],
                "connection_string": state["connection_string"],
                "preview_mode": True,
            },
            timeout=15,
        )
        response.raise_for_status()
        print(f"[agent] Preview succeeded")
        return {**state, "last_error": ""}

    except requests.HTTPError as e:
        error_msg = str(e)
        print(f"[agent] Preview failed: {error_msg}")
        return {
            **state,
            "last_error": error_msg,
            "retry_count": state.get("retry_count", 0) + 1,
        }


def full_execute(state: AgentState) -> AgentState:
    """
    Node 4: Runs the full query (no row cap beyond the hard 1000-row limit).
    Only reached after a successful preview, so we know the SQL is valid.
    """
    response = requests.post(
        f"{EXECUTION_URL}/execute",
        json={
            "sql": state["generated_sql"],
            "connection_string": state["connection_string"],
            "preview_mode": False,
        },
        timeout=15,
    )
    response.raise_for_status()
    result = response.json()

    print(f"[agent] Full execution complete: {result['row_count']} rows returned")

    return {**state, "final_result": result}


# ── Conditional edges ──────────────────────────────────────────────────────────

def should_retry_or_execute(state: AgentState) -> str:
    """
    Decision function: after preview_execute, which node comes next?

    Returns the NAME of the next node -- LangGraph uses this string to
    look up the edge in the graph and route accordingly.

    Three possible outcomes:
    - Preview succeeded (no error) -> go to full_execute
    - Preview failed but we still have retries left -> go back to generate_sql
    - Preview failed and we're out of retries -> go to END (give up)
    """
    if not state.get("last_error"):
        return "full_execute"

    if state.get("retry_count", 0) < MAX_RETRIES:
        return "generate_sql"

    print(f"[agent] Max retries ({MAX_RETRIES}) reached. Giving up.")
    return END


# ── Build the graph ────────────────────────────────────────────────────────────

def build_agent():
    """
    Assembles the LangGraph state machine from nodes + edges.

    This is where the graph structure (the diagram at the top of this file)
    gets expressed as code. Reading this function should match the diagram
    exactly -- each add_node() and add_edge() corresponds directly to a box
    or arrow.
    """
    graph = StateGraph(AgentState)

    # Register nodes
    graph.add_node("fetch_schema", fetch_schema)
    graph.add_node("generate_sql", generate_sql)
    graph.add_node("preview_execute", preview_execute)
    graph.add_node("full_execute", full_execute)

    # Fixed edges (always go this direction)
    graph.add_edge(START, "fetch_schema")
    graph.add_edge("fetch_schema", "generate_sql")
    graph.add_edge("generate_sql", "preview_execute")
    graph.add_edge("full_execute", END)

    # Conditional edge: after preview, the should_retry_or_execute function
    # decides which node to go to next
    graph.add_conditional_edges(
        "preview_execute",
        should_retry_or_execute,
        {
            "full_execute": "full_execute",
            "generate_sql": "generate_sql",
            END: END,
        },
    )

    return graph.compile()


# ── Public API ─────────────────────────────────────────────────────────────────

def run_agent(question: str, connection_string: str) -> dict:
    """
    The single entry point for using the agent. Takes a question and a
    database connection string, returns the full result dict (columns,
    rows, row_count, execution_time_ms).

    If the agent exhausted all retries without succeeding, raises a
    RuntimeError rather than silently returning an empty result.
    """
    agent = build_agent()

    initial_state: AgentState = {
        "question": question,
        "connection_string": connection_string,
        "schema": {},
        "generated_sql": "",
        "retry_count": 0,
        "last_error": "",
        "final_result": {},
        "messages": [],
    }

    final_state = agent.invoke(initial_state)

    if not final_state.get("final_result"):
        raise RuntimeError(
            f"Agent failed to generate a working SQL query after "
            f"{MAX_RETRIES} retries. Last error: {final_state.get('last_error')}"
        )

    return {
        "question": question,
        "generated_sql": final_state["generated_sql"],
        "result": final_state["final_result"],
    }