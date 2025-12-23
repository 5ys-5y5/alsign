"""Structured logging formatter with fixed 1-line format."""

import logging
from typing import Dict, Any, Optional
from ...utils.request_context import add_detailed_log


class StructuredFormatter(logging.Formatter):
    """
    Custom formatter for structured logs.

    Format: [endpoint | phase] elapsed=Xms | progress=done/total(pct%) | eta=Yms | rate=perMin/limitPerMin(usagePct%) | batch=size(mode) | ok=X fail=Y skip=Z upd=A ins=B cf=C | warn=[codes] | message
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record into structured 1-line format."""
        # Extract custom attributes with defaults
        endpoint = getattr(record, 'endpoint', 'N/A')
        phase = getattr(record, 'phase', 'N/A')
        elapsed_ms = getattr(record, 'elapsed_ms', 0)
        progress = getattr(record, 'progress', {})
        eta_ms = getattr(record, 'eta_ms', 0)
        rate = getattr(record, 'rate', {})
        batch = getattr(record, 'batch', {})
        counters = getattr(record, 'counters', {})
        warn = getattr(record, 'warn', [])

        # Build progress string
        if progress:
            done = progress.get('done', 0)
            total = progress.get('total', 0)
            pct = progress.get('pct', 0)
            progress_str = f"progress={done}/{total}({pct}%)"
        else:
            progress_str = "progress=N/A"

        # Build rate string
        if rate:
            per_min = rate.get('perMin', 0)
            limit_per_min = rate.get('limitPerMin', 0)
            usage_pct = rate.get('usagePct', 0)
            rate_str = f"rate={per_min}/{limit_per_min}({usage_pct}%)"
        else:
            rate_str = "rate=N/A"

        # Build batch string
        if batch:
            size = batch.get('size', 0)
            mode = batch.get('mode', 'N/A')
            batch_str = f"batch={size}({mode})"
        else:
            batch_str = "batch=N/A"

        # Build counters string
        counter_parts = []
        if 'success' in counters or 'ok' in counters:
            counter_parts.append(f"ok={counters.get('success', counters.get('ok', 0))}")
        if 'fail' in counters:
            counter_parts.append(f"fail={counters.get('fail', 0)}")
        if 'skip' in counters:
            counter_parts.append(f"skip={counters.get('skip', 0)}")
        if 'update' in counters or 'upd' in counters:
            counter_parts.append(f"upd={counters.get('update', counters.get('upd', 0))}")
        if 'insert' in counters or 'ins' in counters:
            counter_parts.append(f"ins={counters.get('insert', counters.get('ins', 0))}")
        if 'conflict' in counters or 'cf' in counters:
            counter_parts.append(f"cf={counters.get('conflict', counters.get('cf', 0))}")

        counters_str = " ".join(counter_parts) if counter_parts else "counters=N/A"

        # Build warn string
        warn_str = f"warn={warn}" if warn else "warn=[]"

        # Build full message
        log_parts = [
            f"[{endpoint} | {phase}]",
            f"elapsed={elapsed_ms}ms",
            progress_str,
            f"eta={eta_ms}ms",
            rate_str,
            batch_str,
            counters_str,
            warn_str,
            record.getMessage()
        ]

        formatted_log = " | ".join(log_parts)

        # Add to request context for detailed logs
        add_detailed_log(formatted_log)

        return formatted_log


def setup_logging(log_level: str = "INFO"):
    """
    Configure application logging with structured formatter.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Create logger
    logger = logging.getLogger("alsign")
    logger.setLevel(log_level)

    # Remove existing handlers
    logger.handlers.clear()

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)

    # Set structured formatter
    formatter = StructuredFormatter()
    console_handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(console_handler)

    return logger


def create_log_context(
    endpoint: str,
    phase: str,
    elapsed_ms: int = 0,
    progress: Optional[Dict[str, int]] = None,
    eta_ms: int = 0,
    rate: Optional[Dict[str, int]] = None,
    batch: Optional[Dict[str, Any]] = None,
    counters: Optional[Dict[str, int]] = None,
    warn: Optional[list] = None
) -> Dict[str, Any]:
    """
    Create log context dictionary for structured logging.

    Args:
        endpoint: API endpoint (e.g., "GET /sourceData")
        phase: Processing phase (e.g., "getHolidays", "Phase1", "Phase2")
        elapsed_ms: Elapsed time in milliseconds
        progress: Progress dict with done, total, pct
        eta_ms: Estimated time remaining in milliseconds
        rate: Rate dict with perMin, limitPerMin, usagePct
        batch: Batch dict with size, mode
        counters: Counters dict with success/ok, fail, skip, update/upd, insert/ins, conflict/cf
        warn: List of warning codes

    Returns:
        Dictionary of log context attributes
    """
    return {
        'endpoint': endpoint,
        'phase': phase,
        'elapsed_ms': elapsed_ms,
        'progress': progress or {},
        'eta_ms': eta_ms,
        'rate': rate or {},
        'batch': batch or {},
        'counters': counters or {},
        'warn': warn or []
    }
