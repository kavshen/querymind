"""
schema_inspector.py

WHY THIS FILE EXISTS:
This is the actual "brain" of the Schema Service. Its one job: given a DB
connection string, connect to that database and return everything about its
structure (tables, columns, types, primary keys, foreign keys, indexes) as
plain Python data.

WHY SQLAlchemy's inspect() API specifically:
Postgres, MySQL, and SQLite all store schema metadata differently internally.
SQLAlchemy's inspect() function abstracts all of that away -- we write ONE
piece of code, and it works against any of the three databases.
"""

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine

from models import TableInfo, ColumnInfo, ForeignKeyInfo, SchemaResponse


def _detect_database_type(engine: Engine) -> str:
    """Returns a human-readable database type string, e.g. "postgresql" or "mysql"."""
    return engine.dialect.name


def _inspect_table(inspector, table_name: str) -> TableInfo:
    """Builds a TableInfo object for a single table using SQLAlchemy's inspector."""

    columns = []
    for col in inspector.get_columns(table_name):
        columns.append(ColumnInfo(
            name=col["name"],
            type=str(col["type"]),
            nullable=col["nullable"],
            primary_key=col.get("primary_key", False),
            default=str(col["default"]) if col.get("default") is not None else None,
        ))

    pk_constraint = inspector.get_pk_constraint(table_name)
    primary_keys = pk_constraint.get("constrained_columns", []) or []

    for col in columns:
        if col.name in primary_keys:
            col.primary_key = True

    foreign_keys = []
    for fk in inspector.get_foreign_keys(table_name):
        for local_col, remote_col in zip(fk["constrained_columns"], fk["referred_columns"]):
            foreign_keys.append(ForeignKeyInfo(
                column=local_col,
                references_table=fk["referred_table"],
                references_column=remote_col,
            ))

    indexes = [idx["name"] for idx in inspector.get_indexes(table_name) if idx["name"]]

    return TableInfo(
        name=table_name,
        columns=columns,
        primary_keys=primary_keys,
        foreign_keys=foreign_keys,
        indexes=indexes,
    )


def get_schema(connection_string: str) -> SchemaResponse:
    """
    Main entry point. Connects to the target DB and returns its full schema.
    """
    engine = create_engine(connection_string)

    try:
        inspector = inspect(engine)
        table_names = inspector.get_table_names()

        tables = [_inspect_table(inspector, name) for name in table_names]

        return SchemaResponse(
            database_type=_detect_database_type(engine),
            table_count=len(tables),
            tables=tables,
        )
    finally:
        engine.dispose()
