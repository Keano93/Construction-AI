"""Unit tests for the deterministic deadline engine."""

from datetime import date

import pytest

from notice.deadlines import (
    DeadlineRule,
    DeadlineStatus,
    PeriodUnit,
    Shutdown,
    WorkingCalendar,
    add_months,
    compute_deadline,
    deadline_status,
    working_days_remaining,
)

IE = WorkingCalendar(region="IE")
XMAS_2026 = Shutdown("Christmas shutdown", date(2026, 12, 19), date(2027, 1, 4))
BUILDERS_HOLIDAY = Shutdown("Construction holiday", date(2026, 7, 27), date(2026, 8, 7))
IE_SHUT = WorkingCalendar(region="IE", shutdowns=(XMAS_2026, BUILDERS_HOLIDAY))


def wd(n: int) -> DeadlineRule:
    return DeadlineRule(n, PeriodUnit.WORKING_DAYS)


# --- calendar ------------------------------------------------------------

class TestCalendar:
    @pytest.mark.parametrize(
        "d,name",
        [
            (date(2026, 2, 2), "Saint Brigid's Day"),  # 1 Feb 2026 is a Sunday -> first Monday
            (date(2027, 2, 1), "Saint Brigid's Day"),  # 1 Feb 2027 is a Monday
            (date(2025, 2, 3), "Saint Brigid's Day"),
            (date(2026, 3, 17), "Saint Patrick's Day"),
            (date(2026, 4, 6), "Easter Monday"),
            (date(2026, 5, 4), "May Bank Holiday"),
            (date(2026, 6, 1), "June Bank Holiday"),
            (date(2026, 8, 3), "August Bank Holiday"),
            (date(2026, 10, 26), "October Bank Holiday"),
            (date(2026, 12, 25), "Christmas Day"),
        ],
    )
    def test_irish_public_holidays(self, d, name):
        assert IE.public_holiday(d) == name
        assert not IE.is_working_day(d)

    def test_good_friday_is_a_working_day_in_ireland(self):
        assert IE.is_working_day(date(2026, 4, 3))

    def test_good_friday_is_a_holiday_in_northern_ireland(self):
        assert not WorkingCalendar(region="GB-NIR").is_working_day(date(2026, 4, 3))

    def test_twelfth_observed_in_northern_ireland_only(self):
        assert not WorkingCalendar(region="GB-NIR").is_working_day(date(2026, 7, 13))
        assert WorkingCalendar(region="GB-ENG").is_working_day(date(2026, 7, 13))

    def test_weekends(self):
        assert IE.non_working_reason(date(2026, 11, 14)) == "weekend"
        assert IE.non_working_reason(date(2026, 11, 15)) == "weekend"
        assert IE.is_working_day(date(2026, 11, 16))

    def test_shutdown_reason(self):
        assert IE_SHUT.non_working_reason(date(2026, 12, 22)) == "shutdown: Christmas shutdown"

    def test_holiday_takes_precedence_over_shutdown_in_reason(self):
        assert IE_SHUT.non_working_reason(date(2026, 12, 25)) == "public holiday: Christmas Day"

    def test_extra_project_holiday(self):
        cal = WorkingCalendar(region="IE", extra_holidays=frozenset({date(2026, 11, 20)}))
        assert not cal.is_working_day(date(2026, 11, 20))

    def test_six_day_week(self):
        cal = WorkingCalendar(region="IE", working_weekdays=frozenset({0, 1, 2, 3, 4, 5}))
        assert cal.is_working_day(date(2026, 11, 14))  # Saturday

    def test_invalid_region(self):
        with pytest.raises(ValueError):
            WorkingCalendar(region="FR")

    def test_shutdown_must_be_ordered(self):
        with pytest.raises(ValueError):
            Shutdown("bad", date(2026, 1, 5), date(2026, 1, 1))

    def test_working_days_between(self):
        assert IE.working_days_between(date(2026, 11, 13), date(2026, 11, 20)) == 5
        assert IE.working_days_between(date(2026, 11, 20), date(2026, 11, 13)) == -5
        assert IE.working_days_between(date(2026, 11, 13), date(2026, 11, 13)) == 0


# --- working days --------------------------------------------------------

class TestWorkingDays:
    def test_simple_within_week(self):
        # Mon 9 Nov 2026 + 3 WD -> Thu 12 Nov
        assert compute_deadline(date(2026, 11, 9), wd(3), IE).due_date == date(2026, 11, 12)

    def test_trigger_day_not_counted(self):
        assert compute_deadline(date(2026, 11, 9), wd(1), IE).due_date == date(2026, 11, 10)

    def test_spans_weekend(self):
        # Thu 12 Nov + 2 WD -> Fri 13, Mon 16
        r = compute_deadline(date(2026, 11, 12), wd(2), IE)
        assert r.due_date == date(2026, 11, 16)
        assert [d for d, _ in r.skipped] == [date(2026, 11, 14), date(2026, 11, 15)]

    def test_trigger_on_weekend(self):
        # Sat 14 Nov + 1 WD -> Mon 16
        assert compute_deadline(date(2026, 11, 14), wd(1), IE).due_date == date(2026, 11, 16)

    def test_skips_october_bank_holiday(self):
        # Fri 23 Oct 2026 + 1 WD: Sat, Sun, Mon 26 (bank hol) skipped -> Tue 27
        r = compute_deadline(date(2026, 10, 23), wd(1), IE)
        assert r.due_date == date(2026, 10, 27)
        assert (date(2026, 10, 26), "public holiday: October Bank Holiday") in r.skipped

    def test_ten_working_days_over_august_bank_holiday(self):
        # Wed 29 Jul 2026 + 10 WD, 3 Aug is a holiday
        # 30,31 Jul (2), 4,5,6,7 Aug (6), 10,11,12,13 Aug (10)
        assert compute_deadline(date(2026, 7, 29), wd(10), IE).due_date == date(2026, 8, 13)

    def test_twenty_working_days(self):
        # Mon 2 Nov 2026 + 20 WD -> Mon 30 Nov
        assert compute_deadline(date(2026, 11, 2), wd(20), IE).due_date == date(2026, 11, 30)

    def test_christmas_shutdown(self):
        # Thu 17 Dec 2026 + 5 WD with shutdown 19 Dec - 4 Jan:
        # Fri 18 (1), then shutdown + holidays until Tue 5 Jan (2) ... Fri 8 Jan (5)
        r = compute_deadline(date(2026, 12, 17), wd(5), IE_SHUT)
        assert r.due_date == date(2027, 1, 8)

    def test_christmas_without_shutdown(self):
        # Thu 17 Dec 2026 + 5 WD, no shutdown: 18, 21, 22, 23, 24 Dec
        assert compute_deadline(date(2026, 12, 17), wd(5), IE).due_date == date(2026, 12, 24)

    def test_new_years_day_without_shutdown(self):
        # Wed 30 Dec 2026 + 2 WD: 31 Dec, (1 Jan hol), (2,3 weekend), Mon 4 Jan
        assert compute_deadline(date(2026, 12, 30), wd(2), IE).due_date == date(2027, 1, 4)

    def test_construction_holiday(self):
        # Fri 24 Jul 2026 + 1 WD, shutdown 27 Jul - 7 Aug -> Mon 10 Aug
        assert compute_deadline(date(2026, 7, 24), wd(1), IE_SHUT).due_date == date(2026, 8, 10)

    def test_trigger_inside_shutdown(self):
        # Trigger during shutdown: count starts when work resumes
        assert compute_deadline(date(2026, 12, 23), wd(1), IE_SHUT).due_date == date(2027, 1, 5)

    def test_zero_period_on_working_day(self):
        assert compute_deadline(date(2026, 11, 11), wd(0), IE).due_date == date(2026, 11, 11)

    def test_zero_period_on_weekend_rolls_forward(self):
        assert compute_deadline(date(2026, 11, 14), wd(0), IE).due_date == date(2026, 11, 16)

    def test_zero_period_without_roll_forward(self):
        rule = DeadlineRule(0, PeriodUnit.WORKING_DAYS, roll_forward=False)
        assert compute_deadline(date(2026, 11, 14), rule, IE).due_date == date(2026, 11, 14)

    def test_year_boundary_and_brigid(self):
        # Fri 29 Jan 2027 + 1 WD: Mon 1 Feb 2027 is St Brigid's Day -> Tue 2 Feb
        assert compute_deadline(date(2027, 1, 29), wd(1), IE).due_date == date(2027, 2, 2)

    def test_easter(self):
        # Thu 2 Apr 2026 + 2 WD: Fri 3 (Good Friday is working in IE), Mon 6 hol, Tue 7
        assert compute_deadline(date(2026, 4, 2), wd(2), IE).due_date == date(2026, 4, 7)

    def test_same_rule_different_region(self):
        nir = WorkingCalendar(region="GB-NIR")
        assert compute_deadline(date(2026, 4, 2), wd(2), nir).due_date == date(2026, 4, 8)

    def test_trace_is_serialisable(self):
        t = compute_deadline(date(2026, 10, 23), wd(1), IE).to_trace()
        assert t["due_date"] == "2026-10-27"
        assert t["unit"] == "working_days"
        assert len(t["skipped"]) == 3
        assert "October Bank Holiday" in t["skipped"][2]["reason"]

    def test_negative_period_rejected(self):
        with pytest.raises(ValueError):
            DeadlineRule(-1, PeriodUnit.WORKING_DAYS)

    def test_unit_from_string(self):
        assert DeadlineRule(3, "working_days").unit is PeriodUnit.WORKING_DAYS

    def test_long_period_crosses_year(self):
        # 250 WD is roughly a year; must terminate and land on a working day
        r = compute_deadline(date(2026, 1, 5), wd(250), IE_SHUT)
        assert IE_SHUT.is_working_day(r.due_date)
        assert IE_SHUT.working_days_between(date(2026, 1, 5), r.due_date) == 250


# --- calendar-type periods -----------------------------------------------

class TestCalendarPeriods:
    def test_calendar_days_on_working_day(self):
        r = compute_deadline(date(2026, 11, 2), DeadlineRule(7, PeriodUnit.CALENDAR_DAYS), IE)
        assert r.due_date == date(2026, 11, 9)
        assert r.rolled_from is None

    def test_calendar_days_rolls_off_weekend(self):
        # Mon 2 Nov + 5 days = Sat 7 Nov -> Mon 9
        r = compute_deadline(date(2026, 11, 2), DeadlineRule(5, PeriodUnit.CALENDAR_DAYS), IE)
        assert r.due_date == date(2026, 11, 9)
        assert r.rolled_from == date(2026, 11, 7)

    def test_calendar_days_without_roll_forward(self):
        rule = DeadlineRule(5, PeriodUnit.CALENDAR_DAYS, roll_forward=False)
        assert compute_deadline(date(2026, 11, 2), rule, IE).due_date == date(2026, 11, 7)

    def test_calendar_days_rolls_off_bank_holiday(self):
        # Mon 19 Oct + 7 = Mon 26 Oct (bank hol) -> Tue 27
        r = compute_deadline(date(2026, 10, 19), DeadlineRule(7, PeriodUnit.CALENDAR_DAYS), IE)
        assert r.due_date == date(2026, 10, 27)

    def test_calendar_days_roll_out_of_shutdown(self):
        r = compute_deadline(date(2026, 12, 14), DeadlineRule(14, PeriodUnit.CALENDAR_DAYS), IE_SHUT)
        assert r.due_date == date(2027, 1, 5)

    def test_weeks(self):
        assert compute_deadline(date(2026, 11, 11), DeadlineRule(2, PeriodUnit.WEEKS), IE).due_date == date(2026, 11, 25)

    def test_months_month_end_clamp(self):
        # 31 Jan 2027 + 1 month = 28 Feb 2027 (Sun) -> Mon 1 Mar
        r = compute_deadline(date(2027, 1, 31), DeadlineRule(1, PeriodUnit.MONTHS), IE)
        assert r.rolled_from == date(2027, 2, 28)
        assert r.due_date == date(2027, 3, 1)

    def test_add_months_leap_year(self):
        assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
        assert add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)
        assert add_months(date(2026, 12, 15), 1) == date(2027, 1, 15)

    def test_months_twelve(self):
        # Defects period style: 12 months from Mon 16 Nov 2026 -> Tue 16 Nov 2027
        assert compute_deadline(date(2026, 11, 16), DeadlineRule(12, PeriodUnit.MONTHS), IE).due_date == date(2027, 11, 16)


# --- status helpers ------------------------------------------------------

class TestStatus:
    def test_status(self):
        due = date(2026, 11, 16)
        assert deadline_status(due, date(2026, 11, 13)) is DeadlineStatus.OPEN
        assert deadline_status(due, due) is DeadlineStatus.DUE_TODAY
        assert deadline_status(due, date(2026, 11, 17)) is DeadlineStatus.OVERDUE

    def test_working_days_remaining(self):
        # Fri 13 Nov -> Mon 16 Nov: 1 working day remaining
        assert working_days_remaining(date(2026, 11, 16), date(2026, 11, 13), IE) == 1
        assert working_days_remaining(date(2026, 11, 13), date(2026, 11, 17), IE) == -2
