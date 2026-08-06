"""Split database scripts into executable driver units."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class SplitResult:
    executable: tuple[str, ...]
    stripped_transaction_control: int = 0
    stripped_batch_separators: int = 0


def _without_sql_comments(sql: str) -> str:
    output: list[str] = []
    index = 0
    state = "normal"
    while index < len(sql):
        char = sql[index]
        following = sql[index + 1] if index + 1 < len(sql) else ""
        if state == "normal":
            if char == "'":
                state = "single"
                output.append(char)
            elif char == '"':
                state = "double"
                output.append(char)
            elif char == "[":
                state = "bracket"
                output.append(char)
            elif char == "-" and following == "-":
                state = "line_comment"
                output.extend((" ", " "))
                index += 1
            elif char == "/" and following == "*":
                state = "block_comment"
                output.extend((" ", " "))
                index += 1
            else:
                output.append(char)
        elif state == "single":
            output.append(char)
            if char == "'":
                if following == "'":
                    output.append(following)
                    index += 1
                else:
                    state = "normal"
        elif state == "double":
            output.append(char)
            if char == '"':
                if following == '"':
                    output.append(following)
                    index += 1
                else:
                    state = "normal"
        elif state == "bracket":
            output.append(char)
            if char == "]":
                state = "normal"
        elif state == "line_comment":
            if char in "\r\n":
                output.append(char)
                state = "normal"
            else:
                output.append(" ")
        else:
            if char == "*" and following == "/":
                output.extend((" ", " "))
                index += 1
                state = "normal"
            elif char in "\r\n":
                output.append(char)
            else:
                output.append(" ")
        index += 1
    return "".join(output)


def _classification(sql: str) -> str:
    without_comments = _without_sql_comments(sql)
    return " ".join(without_comments.strip().rstrip(";").split()).upper()


_TRANSACTION_CONTROL = {
    "BEGIN",
    "BEGIN TRANSACTION",
    "COMMIT",
    "COMMIT TRANSACTION",
    "END",
    "END TRANSACTION",
    "ROLLBACK",
    "ROLLBACK TRANSACTION",
}


def split_sqlite_script(sql: str) -> SplitResult:
    """Split with SQLite's parser and remove file-owned transaction control."""

    executable: list[str] = []
    buffer: list[str] = []
    stripped = 0

    def flush(statement: str) -> None:
        nonlocal stripped
        classification = _classification(statement)
        if not classification:
            return
        if classification in _TRANSACTION_CONTROL:
            stripped += 1
            return
        executable.append(statement.strip())

    for char in sql:
        buffer.append(char)
        if char == ";" and sqlite3.complete_statement("".join(buffer)):
            flush("".join(buffer))
            buffer.clear()

    tail = "".join(buffer)
    if _classification(tail):
        if not sqlite3.complete_statement(tail + ";"):
            raise ValueError("incomplete SQLite statement at end of script")
        flush(tail)

    return SplitResult(tuple(executable), stripped_transaction_control=stripped)


_GO_LINE = re.compile(r"^\s*GO(?:\s+(\d+))?\s*(?:--.*)?$", re.IGNORECASE)


def split_sqlserver_script(sql: str) -> SplitResult:
    """Split SQL Server scripts on sqlcmd GO batch separators."""

    executable: list[str] = []
    buffer: list[str] = []
    separators = 0

    def flush(repeat: int = 1) -> None:
        batch = "".join(buffer).strip()
        buffer.clear()
        if _classification(batch):
            executable.extend(batch for _ in range(repeat))

    for line in sql.splitlines(keepends=True):
        match = _GO_LINE.match(line.rstrip("\r\n"))
        if match:
            separators += 1
            repeat = int(match.group(1) or "1")
            if repeat < 1:
                raise ValueError("GO repeat count must be positive")
            flush(repeat)
        else:
            buffer.append(line)
    flush()
    return SplitResult(tuple(executable), stripped_batch_separators=separators)


def split_script(dialect: str, sql: str) -> SplitResult:
    if dialect == "sqlite":
        return split_sqlite_script(sql)
    if dialect == "sqlserver":
        return split_sqlserver_script(sql)
    raise ValueError(f"unsupported SQL dialect: {dialect}")
