"""Base exception hierarchy for Signal.

Every package raises a subclass of ``SignalError`` so callers can catch
broad or narrow as needed. The hierarchy is intentionally flat -- one
level of specialisation per concern boundary.
"""


class SignalError(Exception):
    """Base exception for all Signal errors.

    Catch this to handle any Signal-specific failure without importing
    individual subclasses.
    """


class ConfigError(SignalError):
    """Configuration loading or validation failed.

    Raised by ``load_config``, ``load_profile``, and Pydantic validation
    inside config/model constructors.
    """


class AIError(SignalError):
    """AI layer error -- LLM call failed, provider unavailable, etc.

    Raised by ``AILayer.complete`` when the underlying LiteLLM call or
    tool-call parsing fails.
    """


class InstanceError(SignalError):
    """Instance management error -- init, start, stop failures.

    Raised by ``create_instance`` and ``find_instance`` in ``config.py``.
    """


class MemoryStoreError(SignalError):
    """Memory storage, index, or retrieval failure.

    Raised by ``MemoryStorage`` and ``MemoryIndex`` operations when files
    are missing or malformed.
    """


class RoutingError(SignalError):
    """Message routing failed -- no match, talks_to violation, unknown agent.

    Raised by the ``MessageBus`` when a send cannot be delivered.
    """


class ToolExecutionError(SignalError):
    """Tool execution failed.

    Raised when a tool's ``execute`` method encounters an unrecoverable error.
    """
