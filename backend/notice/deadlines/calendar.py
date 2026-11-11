"""Working-day calendars: weekends, public holidays and project shutdowns.

Deterministic, no I/O. Public holidays come from the `holidays` package (a
pinned, rule-based dataset) and can be extended with explicit extra dates, so a
project can record e.g. a one-off government holiday without a code change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache

import holidays as holidays_lib

# Supported regions -> (country, subdivision)
REGIONS: dict[str, tuple[str, str | None]] = {
    "IE": ("IE", None),
    "GB-ENG": ("GB", "ENG"),
    "GB-NIR": ("GB", "NIR"),
    "GB-SCT": ("GB", "SCT"),
    "GB-WLS": ("GB", "WLS"),
}

MON, TUE, WED, THU, FRI, SAT, SUN = range(7)


@dataclass(frozen=True)
class Shutdown:
    name: str
    start: date
    end: date  # inclusive

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(f"Shutdown '{self.name}' ends before it starts")

    def contains(self, d: date) -> bool:
        return self.start <= d <= self.end


@lru_cache(maxsize=64)
def _public_holidays(region: str, year: int) -> dict[date, str]:
    if region not in REGIONS:
        raise ValueError(f"Unsupported holiday region '{region}'. Supported: {sorted(REGIONS)}")
    country, subdiv = REGIONS[region]
    cal = holidays_lib.country_holidays(country, subdiv=subdiv, years=year)
    return {d: name for d, name in cal.items()}


@dataclass(frozen=True)
class WorkingCalendar:
    region: str = "IE"
    working_weekdays: frozenset[int] = frozenset({MON, TUE, WED, THU, FRI})
    shutdowns: tuple[Shutdown, ...] = ()
    extra_holidays: frozenset[date] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if self.region not in REGIONS:
            raise ValueError(f"Unsupported holiday region '{self.region}'")
        if not self.working_weekdays:
            raise ValueError("A calendar needs at least one working weekday")

    # -- classification -------------------------------------------------
    def public_holiday(self, d: date) -> str | None:
        if d in self.extra_holidays:
            return "Project holiday"
        return _public_holidays(self.region, d.year).get(d)

    def shutdown(self, d: date) -> Shutdown | None:
        for s in self.shutdowns:
            if s.contains(d):
                return s
        return None

    def non_working_reason(self, d: date) -> str | None:
        """Why `d` is not a working day, or None if it is one."""
        if d.weekday() not in self.working_weekdays:
            return "weekend"
        hol = self.public_holiday(d)
        if hol:
            return f"public holiday: {hol}"
        sd = self.shutdown(d)
        if sd:
            return f"shutdown: {sd.name}"
        return None

    def is_working_day(self, d: date) -> bool:
        return self.non_working_reason(d) is None

    def next_working_day(self, d: date, *, inclusive: bool = True) -> date:
        cur = d if inclusive else d + timedelta(days=1)
        for _ in range(3660):  # guard against misconfiguration (10 years)
            if self.is_working_day(cur):
                return cur
            cur += timedelta(days=1)
        raise ValueError("No working day found within 10 years; check calendar configuration")

    def working_days_between(self, start: date, end: date) -> int:
        """Working days in the half-open interval (start, end]. Negative if end < start."""
        if end == start:
            return 0
        sign = 1 if end > start else -1
        lo, hi = (start, end) if sign > 0 else (end, start)
        n = 0
        cur = lo + timedelta(days=1)
        while cur <= hi:
            if self.is_working_day(cur):
                n += 1
            cur += timedelta(days=1)
        return n * sign
