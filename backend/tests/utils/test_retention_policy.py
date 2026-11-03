"""Unit tests for the chat retention rules (standard library only, loaded by file path)."""

import importlib.util
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[2] / 'open_webui' / 'utils' / 'retention_policy.py'
_spec = importlib.util.spec_from_file_location('retention_policy_under_test', _PATH)
policy = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = policy  # dataclasses looks the module up by name
_spec.loader.exec_module(policy)

rule = lambda days=None, hold=False: {'days': days, 'hold': hold}  # noqa: E731


class TestAsDays:
    @pytest.mark.parametrize(('value', 'expected'), [(0, 0), (30, 30), ('90', 90), (7.9, 7)])
    def test_valid(self, value, expected):
        assert policy.as_days(value) == expected

    @pytest.mark.parametrize('value', [None, -1, 'x', '', True, False, [], float('nan')])
    def test_invalid(self, value):
        assert policy.as_days(value) is None


class TestReadGroupRetention:
    def test_days_and_hold(self):
        data = {'config': {'retention': {'days': 30, 'hold': True}}}
        assert policy.read_group_retention(data) == {'days': 30, 'hold': True}

    def test_days_only(self):
        assert policy.read_group_retention({'config': {'retention': {'days': '10'}}}) == {'days': 10, 'hold': False}

    def test_zero_days_is_a_rule(self):
        assert policy.read_group_retention({'config': {'retention': {'days': 0}}}) == {'days': 0, 'hold': False}

    @pytest.mark.parametrize(
        'data',
        [None, {}, {'config': None}, {'config': {}}, {'config': {'retention': 'x'}}, {'config': {'retention': {}}},
         {'config': {'retention': {'days': -3}}}, {'config': {'retention': {'hold': 'yes'}}}],
    )  # fmt: skip
    def test_nothing_set(self, data):
        assert policy.read_group_retention(data) is None


class TestResolvePolicy:
    def test_default_applies_without_group_rules(self):
        assert policy.resolve_policy([], 365) == policy.RetentionPolicy(days=365)
        assert policy.resolve_policy([None], 365) == policy.RetentionPolicy(days=365)

    def test_no_default_means_keep_forever(self):
        assert policy.resolve_policy([], 0) == policy.RetentionPolicy(days=0)
        assert policy.resolve_policy([], None) == policy.RetentionPolicy(days=0)

    def test_group_overrides_default_in_both_directions(self):
        assert policy.resolve_policy([rule(30)], 365).days == 30
        assert policy.resolve_policy([rule(1000)], 365).days == 1000

    def test_longest_retention_wins(self):
        assert policy.resolve_policy([rule(30), rule(180), rule(90)], 365).days == 180

    def test_keep_forever_beats_numbers(self):
        assert policy.resolve_policy([rule(30), rule(0)], 365).days == 0

    def test_hold_protects_regardless_of_other_groups(self):
        resolved = policy.resolve_policy([rule(30), rule(hold=True)], 365)
        assert resolved.hold and not resolved.deletes

    def test_hold_beats_a_short_period_in_the_same_group(self):
        assert not policy.resolve_policy([rule(1, hold=True)], 365).deletes

    def test_deletes_flag(self):
        assert policy.RetentionPolicy(days=30).deletes
        assert not policy.RetentionPolicy(days=0).deletes
        assert not policy.RetentionPolicy(days=30, hold=True).deletes

    def test_group_without_days_follows_default(self):
        assert policy.resolve_policy([rule(None)], 365).days == 365


def test_cutoff():
    assert policy.cutoff_timestamp(1_000_000, 1) == 1_000_000 - 86400
    assert policy.cutoff_timestamp(1_000_000.9, 2) == 1_000_000 - 2 * 86400
