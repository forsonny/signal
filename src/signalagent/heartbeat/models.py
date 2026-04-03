"""Heartbeat trigger models and runtime state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TriggerGuards(BaseModel):
    """Safety guards shared by all trigger types."""

    model_config = ConfigDict(extra="forbid")

    cooldown_seconds: int = Field(
        default=60, ge=0,
        description="Minimum seconds between consecutive fires.",
    )
    max_fires: int = Field(
        default=0, ge=0,
        description="Maximum total fires before auto-disable. 0 = unlimited.",
    )
    error_threshold: int = Field(
        default=3, ge=1,
        description="Consecutive dispatch errors before auto-disable.",
    )


class ClockTrigger(BaseModel):
    """Time-based trigger using cron expressions.

    Fires when the current minute matches the 5-field cron expression.
    Deduplication ensures at most one fire per minute transition.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Unique trigger identifier.")
    cron: str = Field(description="5-field cron expression (min hour dom month dow).")
    recipient: str = Field(description="Agent name to receive the trigger message.")
    payload: str = Field(default="", description="Message content sent on fire.")
    guards: TriggerGuards = Field(
        default_factory=TriggerGuards,
        description="Safety guards (cooldown, max_fires, error_threshold).",
    )


class FileEventTrigger(BaseModel):
    """Polling-based file change trigger.

    Checks for file changes (via git status or mtime) at a configurable
    interval. The ``{changed_files}`` placeholder in *payload* is
    replaced with the comma-separated list of changed paths on fire.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Unique trigger identifier.")
    path: str = Field(default=".", description="Directory to watch for changes.")
    interval_seconds: int = Field(
        default=30, ge=5,
        description="Seconds between polling checks.",
    )
    recipient: str = Field(description="Agent name to receive the trigger message.")
    payload: str = Field(
        default="",
        description="Message content; use {changed_files} for substitution.",
    )
    guards: TriggerGuards = Field(
        default_factory=TriggerGuards,
        description="Safety guards (cooldown, max_fires, error_threshold).",
    )


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
