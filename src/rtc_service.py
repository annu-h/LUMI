"""
LUMI — RTC (Real-Time Clock) Service

Provides current date/time with a mockable interface.
The mock allows fixed time injection in tests.

The physical DS3231 RTC will be read over I2C on the ESP32; this
interface is a placeholder for the desktop development environment.
"""

import abc
from datetime import datetime, timezone
from typing import Optional


class RTCService(abc.ABC):
    """Abstract real-time clock interface."""

    @abc.abstractmethod
    def now(self) -> datetime:
        """Return the current datetime (timezone-aware)."""
        ...

    def time_string(self) -> str:
        """Return a friendly time string like '2:35 in the afternoon'."""
        dt = self.now()
        hour = dt.hour
        minute = dt.minute

        if hour < 12:
            period = "in the morning"
            display_hour = hour if hour != 0 else 12
        elif hour == 12:
            period = "in the afternoon"
            display_hour = 12
        else:
            period = "in the afternoon" if hour < 17 else "in the evening"
            display_hour = hour - 12

        if minute == 0:
            return f"{display_hour} o'clock {period}"
        return f"{display_hour}:{minute:02d} {period}"

    def date_string(self) -> str:
        """Return a friendly date string like 'Monday, October 13'."""
        dt = self.now()
        # %-d is Linux-only; use safe alternative
        day = dt.day
        return dt.strftime(f"%A, %B {day}")


class SystemRTC(RTCService):
    """Real RTC backed by the system clock."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc).astimezone()


class MockRTC(RTCService):
    """Fixed-time RTC for tests.

    Args:
        fixed_time: The datetime to always return. Defaults to
                    2026-10-13 09:00 (naive, used as local time).
    """

    def __init__(self, fixed_time: Optional[datetime] = None) -> None:
        if fixed_time is None:
            fixed_time = datetime(2026, 10, 13, 9, 0, 0)
        self._time = fixed_time

    def now(self) -> datetime:
        return self._time
