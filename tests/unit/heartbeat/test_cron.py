"""Unit tests for cron matching -- pure function, no I/O."""

import pytest
from datetime import datetime

from signalagent.heartbeat.cron import cron_match, validate_cron


class TestCronMatchWildcard:
    def test_all_stars_matches_any_time(self):
        dt = datetime(2026, 4, 2, 14, 30)  # Wednesday
        assert cron_match("* * * * *", dt) is True

    def test_all_stars_matches_midnight(self):
        dt = datetime(2026, 1, 1, 0, 0)  # Thursday
        assert cron_match("* * * * *", dt) is True


class TestCronMatchExact:
    def test_exact_minute(self):
        dt = datetime(2026, 4, 2, 14, 30)
        assert cron_match("30 * * * *", dt) is True
        assert cron_match("31 * * * *", dt) is False

    def test_exact_hour(self):
        dt = datetime(2026, 4, 2, 14, 30)
        assert cron_match("* 14 * * *", dt) is True
        assert cron_match("* 15 * * *", dt) is False

    def test_exact_day_of_month(self):
        dt = datetime(2026, 4, 2, 14, 30)
        assert cron_match("* * 2 * *", dt) is True
        assert cron_match("* * 3 * *", dt) is False

    def test_exact_month(self):
        dt = datetime(2026, 4, 2, 14, 30)
        assert cron_match("* * * 4 *", dt) is True
        assert cron_match("* * * 5 *", dt) is False

    def test_exact_day_of_week_iso(self):
        """2026-04-02 is Thursday = weekday() 3."""
        dt = datetime(2026, 4, 2, 14, 30)
        assert cron_match("* * * * 3", dt) is True  # Thursday
        assert cron_match("* * * * 0", dt) is False  # Monday

    def test_all_fields_exact(self):
        dt = datetime(2026, 4, 2, 14, 30)  # Thursday
        assert cron_match("30 14 2 4 3", dt) is True
        assert cron_match("30 14 2 4 0", dt) is False  # wrong dow


class TestCronMatchRange:
    def test_minute_range(self):
        dt = datetime(2026, 4, 2, 14, 30)
        assert cron_match("25-35 * * * *", dt) is True
        assert cron_match("0-10 * * * *", dt) is False

    def test_hour_range(self):
        dt = datetime(2026, 4, 2, 14, 30)
        assert cron_match("* 9-17 * * *", dt) is True
        assert cron_match("* 0-8 * * *", dt) is False


class TestCronMatchStep:
    def test_every_5_minutes(self):
        assert cron_match("*/5 * * * *", datetime(2026, 4, 2, 14, 0)) is True
        assert cron_match("*/5 * * * *", datetime(2026, 4, 2, 14, 5)) is True
        assert cron_match("*/5 * * * *", datetime(2026, 4, 2, 14, 3)) is False

    def test_every_2_hours(self):
        assert cron_match("* */2 * * *", datetime(2026, 4, 2, 0, 0)) is True
        assert cron_match("* */2 * * *", datetime(2026, 4, 2, 2, 0)) is True
        assert cron_match("* */2 * * *", datetime(2026, 4, 2, 1, 0)) is False


class TestCronMatchCommaList:
    def test_minute_list(self):
        dt = datetime(2026, 4, 2, 14, 30)
        assert cron_match("0,15,30,45 * * * *", dt) is True
        assert cron_match("0,15,45 * * * *", dt) is False

    def test_day_of_week_list(self):
        """Thursday = 3."""
        dt = datetime(2026, 4, 2, 14, 30)
        assert cron_match("* * * * 0,3,4", dt) is True  # Mon,Thu,Fri
        assert cron_match("* * * * 0,1,4", dt) is False  # Mon,Tue,Fri


class TestCronMatchCombination:
    def test_range_and_list(self):
        """1-5,15,30 should match 3, 15, 30 but not 10."""
        assert cron_match("1-5,15,30 * * * *", datetime(2026, 4, 2, 14, 3)) is True
        assert cron_match("1-5,15,30 * * * *", datetime(2026, 4, 2, 14, 15)) is True
        assert cron_match("1-5,15,30 * * * *", datetime(2026, 4, 2, 14, 10)) is False

    def test_realistic_business_hours(self):
        """Every 15 min during business hours (9-17) on weekdays (0-4)."""
        expr = "0,15,30,45 9-17 * * 0-4"
        # Thursday 10:15
        assert cron_match(expr, datetime(2026, 4, 2, 10, 15)) is True
        # Thursday 10:10
        assert cron_match(expr, datetime(2026, 4, 2, 10, 10)) is False
        # Saturday 10:15 (weekday 5)
        assert cron_match(expr, datetime(2026, 4, 4, 10, 15)) is False


class TestValidateCron:
    def test_valid_expression(self):
        assert validate_cron("*/5 * * * *") is None

    def test_valid_complex(self):
        assert validate_cron("0,15,30,45 9-17 * * 0-4") is None

    def test_wrong_field_count(self):
        err = validate_cron("* * *")
        assert err is not None
        assert "5 fields" in err

    def test_too_many_fields(self):
        err = validate_cron("* * * * * *")
        assert err is not None
        assert "5 fields" in err

    def test_minute_out_of_range(self):
        err = validate_cron("60 * * * *")
        assert err is not None
        assert "minute" in err

    def test_hour_out_of_range(self):
        err = validate_cron("* 24 * * *")
        assert err is not None
        assert "hour" in err

    def test_day_of_month_zero(self):
        err = validate_cron("* * 0 * *")
        assert err is not None
        assert "day-of-month" in err

    def test_month_out_of_range(self):
        err = validate_cron("* * * 13 *")
        assert err is not None
        assert "month" in err

    def test_day_of_week_out_of_range(self):
        err = validate_cron("* * * * 7")
        assert err is not None
        assert "day-of-week" in err

    def test_invalid_syntax(self):
        err = validate_cron("abc * * * *")
        assert err is not None
        assert "minute" in err
