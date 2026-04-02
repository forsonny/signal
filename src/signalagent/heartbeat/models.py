"""Heartbeat trigger models and runtime state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TriggerGuards(BaseModel):
    """Safety guards shared by all trigger types."""

    model_config = ConfigDict(extra="forbid")

    cooldown_seconds: int = Field(default=60, ge=0)
    max_fires: int = Field(default=0, ge=0)  # 0 = unlimited
    error_threshold: int = Field(default=3, ge=1)


class ClockTrigger(BaseModel):
    """Time-based trigger using cron expressions."""

    model_config = ConfigDict(extra="forbid")

    name: str
    cron: str
    recipient: str
    payload: str = ""
    guards: TriggerGuards = Field(default_factory=TriggerGuards)


class FileEventTrigger(BaseModel):
    """Polling-based file change trigger."""

    model_config = ConfigDict(extra="forbid")

    name: str
    path: str = "."
    interval_seconds: int = Field(default=30, ge=5)
    recipient: str
    payload: str = ""
    guards: TriggerGuards = Field(default_factory=TriggerGuards)


@dataclass
class TriggerState:
    """Runtime-only mutable state per trigger.

    Not persisted -- resets on process restart. fire_count,
    consecutive_errors, and last_fired all start fresh.
    """

    last_fired: datetime | None = None
    fire_count: int = 0
    consecutive_errors: int = 0
    enabled: bool = True
    last_matched_minute: datetime | None = None
