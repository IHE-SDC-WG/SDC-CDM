"""Write build outcomes to etl.run."""

from __future__ import annotations

from sdc_cdm.db.backend import DatabaseBackend


class RunLog:
    def __init__(self, backend: DatabaseBackend):
        self.backend = backend

    def start(self, command: str) -> int:
        if self.backend.dialect == "sqlite":
            return int(
                self.backend.execute(
                    "INSERT INTO etl.run (command, dialect, status) VALUES (?, ?, 'running')",
                    (command, self.backend.dialect),
                )
            )
        return int(
            self.backend.execute(
                "INSERT INTO etl.run (command, dialect, status) "
                "OUTPUT INSERTED.run_id VALUES (?, ?, 'running')",
                (command, self.backend.dialect),
                return_scalar=True,
            )
        )

    def finish(self, run_id: int, *, error: str | None = None) -> None:
        status = "failed" if error is not None else "succeeded"
        now = (
            "strftime('%Y-%m-%dT%H:%M:%fZ','now')"
            if self.backend.dialect == "sqlite"
            else "SYSUTCDATETIME()"
        )
        self.backend.execute(
            f"UPDATE etl.run SET status = ?, completed_at = {now}, error_message = ? "
            "WHERE run_id = ?",
            (status, error, run_id),
        )
