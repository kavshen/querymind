"""
nlsql_generator.py

WHY THIS FILE EXISTS:
This is the "brain" of the NL-to-SQL service, same role schema_inspector.py
played for the Schema Service. Its job: given a question and a connection
string, (1) fetch the real schema by calling the Schema Service, (2) build
a prompt, (3) call Gemini, (4) clean up the response into pure SQL.

WHY WE CALL THE SCHEMA SERVICE OVER HTTP (not by importing its code):
Even though both services currently run on the same laptop, treating them as
independent HTTP services -- rather than importing schema_inspector.py
directly -- matches the real microservice architecture from the project
design doc. It also means either service could be swapped, scaled, or moved
to its own container later with zero code changes here.
"""

import os
from pathlib import Path
import requests
from dotenv import load_dotenv
from google import genai

from models import NLToSQLRequest, NLToSQLResponse
from prompt_builder import build_prompt

# WHY explicit path instead of a bare load_dotenv():
# uvicorn's working directory depends on which folder you ran it from
# (backend/nlsql_service in our case). A bare load_dotenv() searches
# upward from the current working directory, which is usually fine --
# but being explicit here removes any ambiguity: .env always lives in
# backend/, one level up from this file's own folder (nlsql_service/).
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)

SCHEMA_SERVICE_URL = os.environ.get("SCHEMA_SERVICE_URL", "http://localhost:5001")


def _fetch_schema(connection_string: str) -> dict:
    """
    Calls the Schema Service's /schema endpoint to get real table/column data.

    Raises requests.HTTPError if the Schema Service itself failed (e.g. bad
    connection string) -- main.py will catch this and turn it into a clean
    error response, same pattern as the Schema Service's own error handling.
    """
    response = requests.post(
        f"{SCHEMA_SERVICE_URL}/schema",
        json={"connection_string": connection_string},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def _clean_sql_response(raw_text: str) -> str:
    """
    LLMs sometimes wrap SQL in markdown code fences (```sql ... ```) even
    when told not to. This strips that off defensively, so callers always
    get back plain, executable SQL regardless of how the model formatted it.
    """
    text = raw_text.strip()

    if text.startswith("```"):
        # Remove the opening fence (handles both ``` and ```sql)
        text = text.split("\n", 1)[1] if "\n" in text else text
        # Remove the closing fence
        if text.endswith("```"):
            text = text[: -3]

    return text.strip()


def generate_sql(request: NLToSQLRequest) -> NLToSQLResponse:
    """
    Main entry point: orchestrates the full flow from question -> SQL.
    """
    # Step 1: get the real schema for this database
    schema = _fetch_schema(request.connection_string)

    # Step 2: build a prompt that gives the LLM real facts to work with
    prompt = build_prompt(request, schema)

    # Step 3: call Gemini
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set -- check your .env file")

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-flash-latest",
        contents=prompt,
    )

    # Step 4: clean up the response into plain SQL
    generated_sql = _clean_sql_response(response.text)

    return NLToSQLResponse(
        question=request.question,
        generated_sql=generated_sql,
        database_type=schema["database_type"],
        cached=False,  # Redis caching gets wired in next -- always False for now
    )