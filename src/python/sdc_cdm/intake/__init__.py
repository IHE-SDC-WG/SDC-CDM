"""Durable raw-message intake."""

from .store import IntakeResult, ingest_message

__all__ = ["IntakeResult", "ingest_message"]
