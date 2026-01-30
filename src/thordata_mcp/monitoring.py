"""
Performance monitoring and metrics collection for Thordata MCP Server.
"""

import logging
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RequestMetric:
    """Single request metric."""
    tool: str
    duration: float
    success: bool
    timestamp: datetime
    url: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ToolStats:
    """Aggregated statistics for a tool."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_duration: float = 0.0
    min_duration: float = float('inf')
    max_duration: float = 0.0
    recent_metrics: List[RequestMetric] = field(default_factory=list)

    @property
    def avg_duration(self) -> float:
        """Calculate average duration."""
        return self.total_duration / self.total_requests if self.total_requests > 0 else 0.0

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        return self.successful_requests / self.total_requests if self.total_requests > 0 else 0.0


class PerformanceMonitor:
    """Monitor and track performance metrics for MCP tools."""

    def __init__(self, max_recent_metrics: int = 100):
        """
        Initialize performance monitor.

        Args:
            max_recent_metrics: Maximum number of recent metrics to keep per tool
        """
        self.stats: Dict[str, ToolStats] = defaultdict(ToolStats)
        self.max_recent_metrics = max_recent_metrics
        self._enabled = True

    def record_request(
        self,
        tool: str,
        duration: float,
        success: bool,
        url: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        Record a request metric.

        Args:
            tool: Name of the tool (e.g., 'serp', 'unlocker', 'browser')
            duration: Request duration in seconds
            success: Whether the request was successful
            url: Optional URL that was scraped
            error: Optional error message if request failed
        """
        if not self._enabled:
            return

        metric = RequestMetric(
            tool=tool,
            duration=duration,
            success=success,
            timestamp=datetime.now(),
            url=url,
            error=error,
        )

        stats = self.stats[tool]
        stats.total_requests += 1
        stats.total_duration += duration

        if success:
            stats.successful_requests += 1
        else:
            stats.failed_requests += 1

        stats.min_duration = min(stats.min_duration, duration)
        stats.max_duration = max(stats.max_duration, duration)

        # Keep only recent metrics
        stats.recent_metrics.append(metric)
        if len(stats.recent_metrics) > self.max_recent_metrics:
            stats.recent_metrics.pop(0)

    def get_stats(self, tool: str) -> Optional[ToolStats]:
        """
        Get statistics for a specific tool.

        Args:
            tool: Name of the tool

        Returns:
            ToolStats object or None if no data available
        """
        return self.stats.get(tool)

    def get_all_stats(self) -> Dict[str, ToolStats]:
        """Get statistics for all tools."""
        return dict(self.stats)

    def log_summary(self) -> None:
        """Log a summary of all collected metrics."""
        if not self.stats:
            logger.info("No performance metrics collected yet")
            return

        logger.info("=" * 60)
        logger.info("PERFORMANCE SUMMARY")
        logger.info("=" * 60)

        for tool, stats in self.stats.items():
            logger.info(f"\n{tool.upper()}:")
            logger.info(f"  Total Requests: {stats.total_requests}")
            logger.info(f"  Success Rate: {stats.success_rate * 100:.1f}%")
            logger.info(f"  Avg Duration: {stats.avg_duration:.2f}s")
            logger.info(f"  Min Duration: {stats.min_duration:.2f}s")
            logger.info(f"  Max Duration: {stats.max_duration:.2f}s")

    def reset(self) -> None:
        """Reset all collected metrics."""
        self.stats.clear()
        logger.info("Performance metrics reset")

    def enable(self) -> None:
        """Enable performance monitoring."""
        self._enabled = True
        logger.info("Performance monitoring enabled")

    def disable(self) -> None:
        """Disable performance monitoring."""
        self._enabled = False
        logger.info("Performance monitoring disabled")


# Global performance monitor instance
_global_monitor: Optional[PerformanceMonitor] = None


def get_monitor() -> PerformanceMonitor:
    """Get the global performance monitor instance."""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = PerformanceMonitor()
    return _global_monitor


class PerformanceTimer:
    """Context manager for timing operations."""

    def __init__(
        self,
        tool: str,
        url: Optional[str] = None,
        monitor: Optional[PerformanceMonitor] = None,
    ):
        """
        Initialize performance timer.

        Args:
            tool: Name of the tool being timed
            url: Optional URL being processed
            monitor: Optional specific monitor instance (uses global if None)
        """
        self.tool = tool
        self.url = url
        self.monitor = monitor or get_monitor()
        self.start_time: Optional[float] = None
        self.duration: Optional[float] = None
        self.success = False
        self.error: Optional[str] = None

    def __enter__(self):
        """Start timing."""
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop timing and record metric."""
        if self.start_time is not None:
            self.duration = time.time() - self.start_time

            # Determine success based on exception
            self.success = exc_type is None
            if exc_val:
                self.error = str(exc_val)

            # Record the metric
            self.monitor.record_request(
                tool=self.tool,
                duration=self.duration,
                success=self.success,
                url=self.url,
                error=self.error,
            )

            # Log slow requests
            from thordata_mcp.config import get_settings
            settings = get_settings()
            if settings.ENABLE_PERFORMANCE_MONITORING and self.duration > settings.SLOW_REQUEST_THRESHOLD:
                logger.warning(
                    f"Slow request detected: {self.tool} took {self.duration:.2f}s "
                    f"(threshold: {settings.SLOW_REQUEST_THRESHOLD}s)"
                )

        # Don't suppress exceptions
        return False

    def mark_success(self) -> None:
        """Manually mark the operation as successful."""
        self.success = True

    def mark_failure(self, error: str) -> None:
        """Manually mark the operation as failed."""
        self.success = False
        self.error = error
