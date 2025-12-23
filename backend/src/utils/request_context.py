"""Request context for collecting detailed logs per request."""

from contextvars import ContextVar
from typing import List, Optional

# Context variable to store logs for current request
_request_logs: ContextVar[Optional[List[str]]] = ContextVar('request_logs', default=None)


def start_log_collection():
    """Start collecting logs for current request."""
    _request_logs.set([])


def add_detailed_log(log_line: str):
    """Add a log line to current request's detailed logs."""
    logs = _request_logs.get()
    if logs is not None:
        logs.append(log_line)


def get_detailed_logs() -> List[str]:
    """Get all detailed logs for current request."""
    logs = _request_logs.get()
    return logs if logs is not None else []


def clear_detailed_logs():
    """Clear detailed logs for current request."""
    _request_logs.set(None)
