"""
sql_validator.py

WHY THIS FILE EXISTS:
Gemini is generally reliable, but it's still a probabilistic model, not a
guaranteed-correct compiler. Two things can go wrong with its output:

1. It can produce SQL that's syntactically broken (rare, but possible --
   especially on ambiguous questions or edge-case schemas).
2. It can produce a query type we never want here. QueryMind's whole purpose
   is answering questions ("read" queries) -- there is no legitimate reason
   a natural-language QUESTION should ever produce a DROP, DELETE, UPDATE,
   or ALTER statement. If one appears, that's a sign something went wrong
   with the prompt or the model's interpretation, not a valid answer to
   return.

This file catches both cases BEFORE we return SQL to the caller, so bad
output fails loudly and safely here, rather than silently reaching the
Execution service in Phase 4.
"""

import sqlparse

# Statement types that should never appear in a read-only NL-to-SQL response.
# WHY THIS SPECIFIC LIST: these are exactly the SQL keywords that
# create/modify/destroy data or schema, as opposed to SELECT, which only
# reads data. A NL-to-SQL "question answering" tool has no legitimate reason
# to generate any of these.
FORBIDDEN_KEYWORDS = {"DROP", "DELETE", "UPDATE", "TRUNCATE", "ALTER", "INSERT", "CREATE", "GRANT", "REVOKE"}


class SQLValidationError(Exception):
    """Raised when generated SQL fails either the syntax or safety check."""
    pass


def validate_sql(sql: str) -> None:
    """
    Runs both checks. Raises SQLValidationError with a clear message if
    either fails. Returns nothing (None) on success -- callers just need to
    know "did this raise or not", not get a value back.
    """
    _check_syntax(sql)
    _check_is_read_only(sql)


def _check_syntax(sql: str) -> None:
    """
    Uses sqlparse (a SQL parsing library) to confirm the string is at least
    structurally valid SQL. This won't catch every possible semantic error
    (e.g. a typo'd column name -- that only fails when actually executed
    against a real database), but it does catch garbled/incomplete output.
    """
    parsed = sqlparse.parse(sql)

    if not parsed or not str(parsed[0]).strip():
        raise SQLValidationError("Generated output is not valid SQL (empty or unparseable).")


def _check_is_read_only(sql: str) -> None:
    """
    Scans the SQL for any forbidden (non-read-only) keywords. We check
    word-by-word (not substring search) to avoid false positives -- e.g. we
    don't want a column literally named "updated_at" to incorrectly trigger
    a match against "UPDATE".
    """
    # sqlparse tokenizes the SQL properly, respecting things like string
    # literals and comments, which a naive "UPDATE" in sql.upper() search
    # would not -- e.g. a string literal containing the word "delete" should
    # NOT trigger this check.
    parsed = sqlparse.parse(sql)[0]

    tokens = [token for token in parsed.flatten() if not token.is_whitespace]
    keywords_found = {
        token.value.upper()
        for token in tokens
        if token.ttype is not None and str(token.ttype).startswith("Token.Keyword")
    }

    forbidden_found = keywords_found & FORBIDDEN_KEYWORDS
    if forbidden_found:
        raise SQLValidationError(
            f"Generated SQL contains disallowed statement type(s): {', '.join(forbidden_found)}. "
            "Only read (SELECT) queries are permitted."
        )