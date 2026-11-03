"""Unit tests for the token quota rules.

The rules module uses the standard library only, so it is loaded straight from its
file and these tests need no database or backend install.
"""

import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[2] / 'open_webui' / 'utils' / 'quota_policy.py'
_spec = importlib.util.spec_from_file_location('quota_policy_under_test', _MODULE_PATH)
policy = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = policy  # dataclasses looks the module up by name
_spec.loader.exec_module(policy)


class TestAsLimit:
    @pytest.mark.parametrize(('value', 'expected'), [(0, 0), (5, 5), ('7', 7), (3.9, 3), (10**12, 10**12)])
    def test_accepts_non_negative_whole_numbers(self, value, expected):
        assert policy.as_limit(value) == expected

    @pytest.mark.parametrize('value', [None, -1, 'abc', '', [], {}, True, False, float('nan')])
    def test_rejects_everything_else(self, value):
        assert policy.as_limit(value) is None


class TestWindowBounds:
    def _ts(self, *args):
        return dt.datetime(*args).timestamp()

    def test_day_and_month_boundaries(self):
        now = self._ts(2026, 11, 18, 15, 30, 45)
        bounds = policy.window_bounds(now)
        assert bounds['daily'] == (int(self._ts(2026, 11, 18)), int(self._ts(2026, 11, 19)))
        assert bounds['monthly'] == (int(self._ts(2026, 11, 1)), int(self._ts(2026, 12, 1)))

    def test_instant_at_midnight_belongs_to_the_new_day(self):
        bounds = policy.window_bounds(self._ts(2026, 11, 18, 0, 0, 0))
        assert bounds['daily'][0] == int(self._ts(2026, 11, 18))

    def test_month_rolls_over_the_year(self):
        bounds = policy.window_bounds(self._ts(2026, 12, 31, 23, 59, 59))
        assert bounds['monthly'] == (int(self._ts(2026, 12, 1)), int(self._ts(2027, 1, 1)))

    def test_leap_february(self):
        bounds = policy.window_bounds(self._ts(2028, 2, 29, 12))
        assert bounds['monthly'] == (int(self._ts(2028, 2, 1)), int(self._ts(2028, 3, 1)))
        assert bounds['daily'][1] == int(self._ts(2028, 3, 1))


class TestResolveLimit:
    def test_default_applies_without_group_values(self):
        assert policy.resolve_limit([], 1000) == 1000
        assert policy.resolve_limit([None, None], 1000) == 1000

    def test_unset_default_means_unlimited(self):
        assert policy.resolve_limit([], 0) == policy.UNLIMITED
        assert policy.resolve_limit([], None) == policy.UNLIMITED

    def test_group_value_replaces_the_default_in_both_directions(self):
        assert policy.resolve_limit([500], 1000) == 500
        assert policy.resolve_limit([5000], 1000) == 5000

    def test_most_permissive_group_wins(self):
        assert policy.resolve_limit([500, 2000, 800], 100) == 2000

    def test_unlimited_group_beats_numbers(self):
        assert policy.resolve_limit([500, 0, 2000], 100) == policy.UNLIMITED

    def test_invalid_group_values_are_ignored(self):
        assert policy.resolve_limit([-5, 'x', None], 1000) == 1000
        assert policy.resolve_limit([-5, 300], 1000) == 300


class TestReadGroupQuota:
    def test_reads_both_windows(self):
        data = {'config': {'usage_quota': {'daily_tokens': 100, 'monthly_tokens': '2000'}}}
        assert policy.read_group_quota(data) == {'daily': 100, 'monthly': 2000}

    @pytest.mark.parametrize('data', [None, {}, {'config': None}, {'config': {}}, {'config': {'usage_quota': 'x'}}])
    def test_missing_or_malformed_means_unset(self, data):
        assert policy.read_group_quota(data) == {'daily': None, 'monthly': None}

    def test_zero_is_a_real_value(self):
        data = {'config': {'usage_quota': {'daily_tokens': 0}}}
        assert policy.read_group_quota(data) == {'daily': 0, 'monthly': None}


class TestTokenCounts:
    def test_uses_reported_totals(self):
        assert policy.token_counts({'input_tokens': 10, 'output_tokens': 5, 'total_tokens': 15}) == (10, 5, 15)

    def test_derives_total_when_missing(self):
        assert policy.token_counts({'input_tokens': 10, 'output_tokens': 5}) == (10, 5, 15)
        assert policy.token_counts({'output_tokens': 5}) == (0, 5, 5)

    def test_total_only(self):
        assert policy.token_counts({'total_tokens': 42}) == (0, 0, 42)

    @pytest.mark.parametrize('usage', [None, {}, 'x', {'timings': 1}, {'total_tokens': 'n/a'}])
    def test_no_usage_reported(self, usage):
        assert policy.token_counts(usage) is None


class TestFirstExceeded:
    limits = policy.QuotaLimits(daily=100, monthly=1000)

    def test_under_both_limits(self):
        assert policy.first_exceeded({'daily': 99, 'monthly': 999}, self.limits) is None

    def test_limit_is_reached_at_equality(self):
        assert policy.first_exceeded({'daily': 100, 'monthly': 0}, self.limits) == 'daily'

    def test_daily_is_reported_before_monthly(self):
        assert policy.first_exceeded({'daily': 500, 'monthly': 5000}, self.limits) == 'daily'

    def test_monthly_only(self):
        assert policy.first_exceeded({'daily': 1, 'monthly': 1000}, self.limits) == 'monthly'

    def test_unlimited_windows_never_trigger(self):
        assert policy.first_exceeded({'daily': 10**9, 'monthly': 10**9}, policy.QuotaLimits()) is None
        only_monthly = policy.QuotaLimits(daily=0, monthly=50)
        assert policy.first_exceeded({'daily': 10**9, 'monthly': 49}, only_monthly) is None
