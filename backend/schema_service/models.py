"""
models.py

WHY THIS FILE EXISTS:
FastAPI uses Pydantic models to (a) validate incoming request bodies automatically,
and (b) auto-generate API docs (visible at /docs). Instead of manually checking
"did the user send a connection_string?", we just declare the shape once here,
and FastAPI enforces it for us on every request.
"""

from pydantic import BaseModel, Field
from typing import Optional


class SchemaRequest(BaseModel):
    """
    What the client must send us to request a schema.

    We accept a raw SQLAlchemy-style connection string rather than separate
    host/port/user/password fields, because it's the most flexible format --
    it works identically whether the DB is Postgres, MySQL, or SQLite, and
    matches what we'll store internally later.
    """
    connection_string: str = Field(
        ...,
        description="SQLAlchemy-style DB connection string",
        examples=["postgresql+psycopg://querymind:querymind_dev_pw@localhost:5432/querymind"]
    )


class ColumnInfo(BaseModel):
    """Describes a single column within a table."""
    name: str
    type: str
    nullable: bool
    primary_key: bool
    default: Optional[str] = None


class ForeignKeyInfo(BaseModel):
    """Describes a foreign key relationship from one table to another."""
    column: str
    references_table: str
    references_column: str


class TableInfo(BaseModel):
    """Full description of one table: its columns, keys, and indexes."""
    name: str
    columns: list[ColumnInfo]
    primary_keys: list[str]
    foreign_keys: list[ForeignKeyInfo]
    indexes: list[str]


class SchemaResponse(BaseModel):
    """What we send back: the full schema of the target database."""
    database_type: str
    table_count: int
    tables: list[TableInfo]
