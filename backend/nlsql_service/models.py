"""
models.py (NL-to-SQL Service)

WHY THIS FILE EXISTS:
Same reasoning as the Schema Service's models.py -- declare the shape of
requests/responses once, let FastAPI validate and document it automatically.
"""

from pydantic import BaseModel, Field


class NLToSQLRequest(BaseModel):
    """
    What the client sends us: a plain-English question, plus which database
    to answer it against.

    WHY we take connection_string here (not schema JSON directly):
    We want the CALLER's job to be simple -- "here's my question, here's my
    database" -- not "here's my question, and by the way go fetch my own
    schema first and hand it to me correctly formatted." This service takes
    on the responsibility of calling the Schema Service itself internally.
    This mirrors how the LangGraph agent in Phase 4 will orchestrate multiple
    services together.
    """
    question: str = Field(
        ...,
        description="A plain-English question about the data",
        examples=["How many customers do we have?"]
    )
    connection_string: str = Field(
        ...,
        description="SQLAlchemy-style DB connection string for the target database"
    )


class NLToSQLResponse(BaseModel):
    """What we send back: the generated SQL, plus some transparency about how we got there."""
    question: str
    generated_sql: str
    database_type: str
    cached: bool = Field(
        default=False,
        description="True if this SQL came from cache rather than a fresh LLM call"
    )
