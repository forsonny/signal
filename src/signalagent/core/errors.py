"""Base exception hierarchy for Signal."""


class SignalError(Exception):
    """Base exception for all Signal errors."""


class ConfigError(SignalError):
    """Configuration loading or validation failed."""


class AIError(SignalError):
    """AI layer error -- LLM call failed, provider unavailable, etc."""


class InstanceError(SignalError):
    """Instance management error -- init, start, stop failures."""
