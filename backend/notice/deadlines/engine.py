"""Deterministic deadline engine.

Deadlines are computed by code, never by a model. Every result carries a trace
explaining exactly how the due date was reached so a QS can check it by hand.

Counting conventions (configurable per rule, defaults follow common Irish/UK
practice and the PWC-style "within N Working Days after X" wording):

* The trigger day itself is never counted; counting starts the day after.
* working_days: only working days (calendar.is_working_day) are counted.
* calendar_days / weeks: every day counts. If `roll_forward` is set and the
  last day is not a working day, the deadline moves to the next working day.
* months: same day-of-month N months later, clamped to month end
  (31 Jan + 1 month = 28/29 Feb), then optional roll-forward.
* period 0 means "on the trigger date itself" (e.g. "immediately"); with
  roll_forward it moves to the next working day.
"""

from __future__ import annotations

import calendar as _cal
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum

from .calendar import WorkingCalendar


class PeriodUnit(str, Enum):
    WORKING_DAYS = "working_days"
    CALENDAR_DAYS = "calendar_days"
    WEEKS = "weeks"
    MONTHS = "months"


class DeadlineStatus(str, Enum):
    OPEN = "open"
    DUE_TODAY = "due_today"
    OVERDUE = "overdue"


@dataclass(frozen=True)
class DeadlineRule:
    period: int
    unit: PeriodUnit
    roll_forward: bool = True  # only affects calendar-type units

    def __post_init__(self) -> None:
        if self.period < 0:
            raise ValueError("period must be >= 0")
        if not isinstance(self.unit, PeriodUnit):
            object.__setattr__(self, "unit", PeriodUnit(self.unit))


@dataclass
class DeadlineResult:
    trigger_date: date
    due_date: date
    rule: DeadlineRule
    skipped: list[tuple[date, str]] = field(default_factory=list)
    rolled_from: date | None = None
    explanation: str = ""

    def to_trace(self) -> dict:
        return {
            "trigger_date": self.trigger_date.isoformat(),
            "due_date": self.due_date.isoformat(),
            "period": self.rule.period,
            "unit": self.rule.unit.value,
            "roll_forward": self.rule.roll_forward,
            "skipped": [{"date": d.isoformat(), "reason": r} for d, r in self.skipped],
            "rolled_from": self.rolled_from.isoformat() if self.rolled_from else None,
            "explanation": self.explanation,
        }


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    last = _cal.monthrange(year, month)[1]
    return date(year, month, min(d.day, last))


def compute_deadline(trigger: date, rule: DeadlineRule, cal: WorkingCalendar) -> DeadlineResult:
    if rule.unit == PeriodUnit.WORKING_DAYS:
        return _working_days(trigger, rule, cal)
    if rule.unit == PeriodUnit.CALENDAR_DAYS:
        raw = trigger + timedelta(days=rule.period)
    elif rule.unit == PeriodUnit.WEEKS:
        raw = trigger + timedelta(weeks=rule.period)
    elif rule.unit == PeriodUnit.MONTHS:
        raw = add_months(trigger, rule.period)
    else:  # pragma: no cover - enum exhaustive
        raise ValueError(rule.unit)

    res = DeadlineResult(trigger_date=trigger, due_date=raw, rule=rule)
    label = {PeriodUnit.CALENDAR_DAYS: "calendar day", PeriodUnit.WEEKS: "week", PeriodUnit.MONTHS: "month"}[rule.unit]
    expl = f"{rule.period} {label}{'s' if rule.period != 1 else ''} after {trigger.isoformat()} = {raw.isoformat()}"
    if rule.roll_forward and not cal.is_working_day(raw):
        reason = cal.non_working_reason(raw)
        due = cal.next_working_day(raw)
        cur = raw
        while cur < due:
            res.skipped.append((cur, cal.non_working_reason(cur) or ""))
            cur += timedelta(days=1)
        res.rolled_from, res.due_date = raw, due
        expl += f"; {raw.isoformat()} is not a working day ({reason}), rolled forward to {due.isoformat()}"
    res.explanation = expl
    return res


def _working_days(trigger: date, rule: DeadlineRule, cal: WorkingCalendar) -> DeadlineResult:
    res = DeadlineResult(trigger_date=trigger, due_date=trigger, rule=rule)
    if rule.period == 0:
        due = cal.next_working_day(trigger) if rule.roll_forward else trigger
        res.due_date = due
        res.explanation = f"0 working days: due {due.isoformat()}"
        return res
    counted = 0
    cur = trigger
    guard = 0
    while counted < rule.period:
        cur += timedelta(days=1)
        guard += 1
        if guard > 3660:
            raise ValueError("Deadline exceeds 10 years; check calendar configuration")
        reason = cal.non_working_reason(cur)
        if reason is None:
            counted += 1
        else:
            res.skipped.append((cur, reason))
    res.due_date = cur
    res.explanation = (
        f"{rule.period} working day{'s' if rule.period != 1 else ''} after {trigger.isoformat()} "
        f"(day after trigger counts as day 1; {len(res.skipped)} non-working day(s) skipped) = {cur.isoformat()}"
    )
    return res


def deadline_status(due: date, today: date) -> DeadlineStatus:
    if today > due:
        return DeadlineStatus.OVERDUE
    if today == due:
        return DeadlineStatus.DUE_TODAY
    return DeadlineStatus.OPEN


def working_days_remaining(due: date, today: date, cal: WorkingCalendar) -> int:
    """Working days left after today up to and including the due date (negative when overdue)."""
    return cal.working_days_between(today, due)
