"""Cron expression matching -- pure functions, no dependencies."""

from __future__ import annotations

from datetime import datetime

__all__ = ["cron_match", "validate_cron"]

# Field index -> (min_value, max_value)
_FIELD_RANGES: list[tuple[int, int]] = [
    (0, 59),   # minute
    (0, 23),   # hour
    (1, 31),   # day of month
    (1, 12),   # month
    (0, 6),    # day of week (ISO: Mon=0, Sun=6)
]


def _parse_field(field: str, min_val: int, max_val: int) -> set[int]:
    """Parse a single cron field into a set of matching integers.

    Supports: * (any), N (exact), N-M (range), */N (step), N,M (list),
    and combinations like 1-5,15,30.
    """
    values: set[int] = set()

    for part in field.split(","):
        part = part.strip()

        if part == "*":
            values.update(range(min_val, max_val + 1))
        elif "/" in part:
            # Step: */N or N-M/N
            base, step_str = part.split("/", 1)
            step = int(step_str)
            if step <= 0:
                raise ValueError(f"Step must be positive: {part}")
            if base == "*":
                start = min_val
                end = max_val
            elif "-" in base:
                start_str, end_str = base.split("-", 1)
                start = int(start_str)
                end = int(end_str)
            else:
                start = int(base)
                end = max_val
            values.update(range(start, end + 1, step))
        elif "-" in part:
            # Range: N-M
            start_str, end_str = part.split("-", 1)
            start = int(start_str)
            end = int(end_str)
            if start > end:
                raise ValueError(f"Invalid range: {part}")
            values.update(range(start, end + 1))
        else:
            # Exact value
            values.add(int(part))

    # Validate all values are in range
    for v in values:
        if v < min_val or v > max_val:
            raise ValueError(f"Value {v} out of range [{min_val}, {max_val}]")

    return values


def cron_match(expression: str, dt: datetime) -> bool:
    """Check if a datetime matches a 5-field cron expression.

    Fields: minute hour day-of-month month day-of-week
    Day-of-week uses ISO convention: Monday=0, Sunday=6
    (matches Python's datetime.weekday()).
    """
    fields = expression.strip().split()
    if len(fields) != 5:
        raise ValueError(f"Expected 5 fields, got {len(fields)}: {expression!r}")

    dt_values = [dt.minute, dt.hour, dt.day, dt.month, dt.weekday()]

    for field_str, (min_val, max_val), dt_val in zip(
        fields, _FIELD_RANGES, dt_values, strict=True,
    ):
        allowed = _parse_field(field_str, min_val, max_val)
        if dt_val not in allowed:
            return False

    return True


def validate_cron(expression: str) -> str | None:
    """Validate a cron expression. Returns error message or None if valid."""
    fields = expression.strip().split()
    if len(fields) != 5:
        return f"Expected 5 fields, got {len(fields)}"

    field_names = ["minute", "hour", "day-of-month", "month", "day-of-week"]
    for field_str, (min_val, max_val), name in zip(
        fields, _FIELD_RANGES, field_names, strict=True,
    ):
        try:
            _parse_field(field_str, min_val, max_val)
        except (ValueError, OverflowError) as e:
            return f"Invalid {name} field '{field_str}': {e}"

    return None
