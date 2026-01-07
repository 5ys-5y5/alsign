"""Batch utilities for dynamic batch sizing and rate limit management."""

from typing import List, TypeVar
import time
from collections import deque

T = TypeVar('T')


class RateLimiter:
    """
    Sliding window rate limiter with dynamic batch sizing.

    Tracks API calls within a time window and enforces rate limits.
    """

    def __init__(self, calls_per_minute: int):
        """
        Initialize rate limiter.

        Args:
            calls_per_minute: Maximum allowed calls per minute
        """
        self.calls_per_minute = calls_per_minute
        self.window_size = 60.0  # seconds
        self.call_timestamps: deque = deque()

    async def acquire(self):
        """
        Wait if necessary to stay within rate limit.

        Blocks until it's safe to make another API call.
        """
        import asyncio

        now = time.time()

        # Remove timestamps outside window
        while self.call_timestamps and self.call_timestamps[0] < now - self.window_size:
            self.call_timestamps.popleft()

        # If at capacity, wait until oldest call ages out
        if len(self.call_timestamps) >= self.calls_per_minute:
            sleep_time = self.call_timestamps[0] + self.window_size - now + 0.1  # +0.1 buffer
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
            # Clean up again after sleeping
            now = time.time()
            while self.call_timestamps and self.call_timestamps[0] < now - self.window_size:
                self.call_timestamps.popleft()

        # Record this call
        self.call_timestamps.append(time.time())

    def get_current_rate(self) -> int:
        """
        Calculate current calls per minute in the sliding window.

        Returns:
            Number of calls in the current window
        """
        now = time.time()
        recent_calls = [ts for ts in self.call_timestamps if ts > now - self.window_size]
        return len(recent_calls)

    def get_usage_percentage(self) -> float:
        """
        Calculate current usage as percentage of rate limit.

        Formula per FR-029: usage_pct = current_requests_per_minute / config_lv1_api_service.usagePerMin

        Returns:
            Usage percentage (0.0 to 1.0+)
        """
        return self.get_current_rate() / self.calls_per_minute

    def calculate_dynamic_batch_size(self, remaining_items: int) -> tuple[int, str]:
        """
        Calculate batch size using FR-029 algorithm with FR-029-A mode reporting.

        Algorithm per FR-029:
            batch_size = max(1, min(remaining_items, floor(limit_per_min * (1 - usage_pct) / 2)))
            - When usage_pct >= 0.80: reduce to 1 (throttled mode)
            - When usage_pct < 0.50: increase up to 50 (aggressive mode)

        Batch modes per FR-029-A:
            - "dynamic": normal adaptive sizing (0.50 <= usage_pct < 0.80)
            - "throttled": usage_pct >= 0.80, batch_size = 1
            - "aggressive": usage_pct < 0.50, batch_size up to 50
            - "minimum": batch_size = 1 (forced minimum)

        Args:
            remaining_items: Number of items left to process

        Returns:
            Tuple of (batch_size, mode) where mode is one of: dynamic, throttled, aggressive, minimum
        """
        usage_pct = self.get_usage_percentage()
        limit_per_min = self.calls_per_minute

        # FR-029 algorithm
        if usage_pct >= 0.80:
            # Throttled mode - reduce to minimum
            batch_size = 1
            mode = "throttled"
        elif usage_pct < 0.50:
            # Aggressive mode - increase up to 50
            calculated = int(limit_per_min * (1 - usage_pct) / 2)
            batch_size = max(1, min(remaining_items, min(calculated, 50)))
            mode = "aggressive"
        else:
            # Dynamic mode - normal adaptive sizing
            calculated = int(limit_per_min * (1 - usage_pct) / 2)
            batch_size = max(1, min(remaining_items, calculated))
            mode = "dynamic"

        return batch_size, mode

    def adjust_batch_size(self, current_batch_size: int) -> tuple[int, str]:
        """
        Dynamically adjust batch size based on current usage.

        DEPRECATED: Use calculate_dynamic_batch_size() for FR-029 compliant behavior.

        This method is retained for backward compatibility.

        Args:
            current_batch_size: Current batch size

        Returns:
            Tuple of (new_batch_size, mode_name)
        """
        usage_pct = self.get_usage_percentage()

        if usage_pct < 0.3:
            # Aggressive mode
            new_size = int(current_batch_size * 1.5)
            mode = "Aggressive"
        elif usage_pct > 0.7:
            # Conservative mode
            new_size = max(1, int(current_batch_size * 0.7))
            mode = "Conservative"
        else:
            # Maintain mode
            new_size = current_batch_size
            mode = "Maintain"

        return new_size, mode


def chunk_list(items: List[T], chunk_size: int) -> List[List[T]]:
    """
    Split list into chunks of specified size.

    Args:
        items: List to chunk
        chunk_size: Maximum size of each chunk

    Returns:
        List of chunks

    Example:
        chunk_list([1,2,3,4,5], 2) -> [[1,2], [3,4], [5]]
    """
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def calculate_eta(total: int, done: int, elapsed_ms: int) -> int:
    """
    Calculate estimated time remaining in milliseconds.

    Args:
        total: Total items to process
        done: Items already processed
        elapsed_ms: Elapsed time in milliseconds

    Returns:
        Estimated time remaining in milliseconds (0 if done >= total)
    """
    if done >= total or done == 0:
        return 0

    avg_time_per_item = elapsed_ms / done
    remaining_items = total - done
    eta_ms = int(avg_time_per_item * remaining_items)

    return eta_ms


def format_progress(done: int, total: int) -> dict:
    """
    Format progress as dict with done, total, and percentage.

    Args:
        done: Items completed
        total: Total items

    Returns:
        Dict with done, total, pct keys
    """
    pct = int((done / total * 100)) if total > 0 else 0
    return {
        'done': done,
        'total': total,
        'pct': pct
    }


def format_eta_ms(eta_ms: int) -> str:
    """
    Format ETA milliseconds to human-readable time format.

    Args:
        eta_ms: ETA in milliseconds

    Returns:
        Formatted string like "1h 2m 3s", "5m 30s", or "45s"
        Returns "0s" if eta_ms is 0 or negative

    Examples:
        format_eta_ms(3661000) -> "1h 1m 1s"
        format_eta_ms(125000) -> "2m 5s"
        format_eta_ms(5000) -> "5s"
        format_eta_ms(0) -> "0s"
    """
    if eta_ms <= 0:
        return "0s"

    total_seconds = eta_ms // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or len(parts) == 0:
        parts.append(f"{seconds}s")

    return " ".join(parts)
