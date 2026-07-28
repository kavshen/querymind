"""
prompt_builder.py

WHY THIS FILE EXISTS:
An LLM cannot write correct SQL for a database it knows nothing about. This
file's one job is turning (schema JSON + a plain-English question) into a
prompt that gives the LLM everything it needs: the real table names, real
column names, real types, and real foreign key relationships -- so it isn't
guessing.

WHY THIS IS ITS OWN FILE (separate from nlsql_generator.py):
Prompt engineering is something you'll iterate on A LOT as you test this
against real questions -- tweaking wording, adding few-shot examples, adding
warnings about dialect differences, etc. Keeping it isolated means you can
change prompt wording without touching any API-calling logic.
"""

from models import NLToSQLRequest


def _format_schema_as_text(schema: dict) -> str:
    """
    Converts the Schema Service's JSON output into a compact, readable text
    block for the LLM -- similar to how you'd write CREATE TABLE statements.

    WHY THIS FORMAT SPECIFICALLY:
    LLMs are trained on enormous amounts of real SQL DDL (CREATE TABLE
    statements), so representing the schema in that familiar shape gets
    better results than, say, dumping raw JSON at the model.
    """
    lines = []
    for table in schema["tables"]:
        lines.append(f"TABLE {table['name']} (")

        for col in table["columns"]:
            pk_marker = " PRIMARY KEY" if col["primary_key"] else ""
            null_marker = "" if col["nullable"] else " NOT NULL"
            lines.append(f"    {col['name']} {col['type']}{pk_marker}{null_marker},")

        for fk in table["foreign_keys"]:
            lines.append(
                f"    FOREIGN KEY ({fk['column']}) REFERENCES "
                f"{fk['references_table']}({fk['references_column']}),"
            )

        lines.append(")")
        lines.append("")  # blank line between tables for readability

    return "\n".join(lines)


def build_prompt(request: NLToSQLRequest, schema: dict) -> str:
    """
    Assembles the final prompt sent to the LLM.

    Structure follows a common, effective pattern for text-to-SQL prompting:
    1. Role/task framing
    2. The real schema (so the model has facts, not guesses)
    3. Explicit output format instructions (so we get back ONLY sql, no
       chatty explanation we'd have to strip out)
    4. The actual question
    """
    schema_text = _format_schema_as_text(schema)

    prompt = f"""You are an expert SQL developer. Given a database schema and a question, generate a single, correct SQL query that answers the question.

Database type: {schema['database_type']}

Schema:
{schema_text}

Rules:
- Return ONLY the SQL query. No explanation, no markdown code fences, no commentary.
- Use only the tables and columns shown above -- do not invent column or table names.
- Prefer explicit JOINs over implicit comma joins.
- If the question cannot be answered with the given schema, return exactly: -- CANNOT_ANSWER

Question: {request.question}

SQL query:"""

    return prompt
