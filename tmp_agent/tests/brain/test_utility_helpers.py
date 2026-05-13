"""
Tests for pure helper functions in brain_v9.brain.utility.

These tests target the stateless math/utility functions that don't depend
on the filesystem. We import them directly from the module.
"""
import math
import pytest


# We can't easily import from brain_v9.brain.utility at module level because
# it imports brain_v9.config which has side effects. Instead we import
# inside the test functions using the isolated_base_path fixture from conftest.


class TestRound:

    def test_basic_rounding(self, isolated_base_path):
        from brain_v9.brain.utility import _round
        assert _round(3.14159, 2) == 3.14
        assert _round(3.14159, 4) == 3.1416

    def test_default_digits(self, isolated_base_path):
        from brain_v9.brain.utility import _round
        assert _round(1.23456789) == 1.2346  # default 4 digits

    def test_integer_input(self, isolated_base_path):
        from brain_v9.brain.utility import _round
        assert _round(5, 2) == 5.0

    def test_zero(self, isolated_base_path):
        from brain_v9.brain.utility import _round
        assert _round(0.0, 4) == 0.0

    def test_negative(self, isolated_base_path):
        from brain_v9.brain.utility import _round
        assert _round(-1.5678, 2) == -1.57

    def test_string_number(self, isolated_base_path):
        """_round calls float(value), so string numbers should work."""
        from brain_v9.brain.utility import _round
        assert _round("3.14", 1) == 3.1


class TestClamp:

    def test_within_range(self, isolated_base_path):
        from brain_v9.brain.utility import _clamp
        assert _clamp(0.5, 0.0, 1.0) == 0.5

    def test_below_range(self, isolated_base_path):
        from brain_v9.brain.utility import _clamp
        assert _clamp(-5.0, 0.0, 1.0) == 0.0

    def test_above_range(self, isolated_base_path):
        from brain_v9.brain.utility import _clamp
        assert _clamp(10.0, 0.0, 1.0) == 1.0

    def test_at_boundaries(self, isolated_base_path):
        from brain_v9.brain.utility import _clamp
        assert _clamp(0.0, 0.0, 1.0) == 0.0
        assert _clamp(1.0, 0.0, 1.0) == 1.0

    def test_negative_range(self, isolated_base_path):
        from brain_v9.brain.utility import _clamp
        assert _clamp(-0.5, -1.0, 0.0) == -0.5
        assert _clamp(-2.0, -1.0, 0.0) == -1.0


class TestSquashSignal:

    def test_zero_input(self, isolated_base_path):
        from brain_v9.brain.utility import _squash_signal
        assert _squash_signal(0.0) == 0.0

    def test_positive(self, isolated_base_path):
        from brain_v9.brain.utility import _squash_signal
        result = _squash_signal(1.0)
        # tanh(1.0) ~= 0.7616
        assert 0.76 < result < 0.77

    def test_negative(self, isolated_base_path):
        from brain_v9.brain.utility import _squash_signal
        result = _squash_signal(-1.0)
        assert -0.77 < result < -0.76

    def test_large_value_capped_at_1(self, isolated_base_path):
        from brain_v9.brain.utility import _squash_signal
        result = _squash_signal(1000.0)
        assert result == 1.0  # tanh(1000) -> 1.0, clamped to [-1, 1]

    def test_large_negative_capped_at_minus_1(self, isolated_base_path):
        from brain_v9.brain.utility import _squash_signal
        result = _squash_signal(-1000.0)
        assert result == -1.0

    def test_scale_parameter(self, isolated_base_path):
        from brain_v9.brain.utility import _squash_signal
        # With scale=2.0, squash_signal(1.0, 2.0) = tanh(0.5) ~= 0.4621
        result = _squash_signal(1.0, scale=2.0)
        assert 0.46 < result < 0.47

    def test_scale_zero_defaults_to_one(self, isolated_base_path):
        from brain_v9.brain.utility import _squash_signal
        # scale <= 0 defaults to 1.0
        result_zero = _squash_signal(1.0, scale=0.0)
        result_one = _squash_signal(1.0, scale=1.0)
        assert result_zero == result_one

    def test_scale_negative_defaults_to_one(self, isolated_base_path):
        from brain_v9.brain.utility import _squash_signal
        result_neg = _squash_signal(1.0, scale=-5.0)
        result_one = _squash_signal(1.0, scale=1.0)
        assert result_neg == result_one

    def test_output_always_in_range(self, isolated_base_path):
        """Output should always be in [-1, 1] regardless of input."""
        from brain_v9.brain.utility import _squash_signal
        for val in [-1e10, -100, -1, 0, 1, 100, 1e10]:
            result = _squash_signal(val)
            assert -1.0 <= result <= 1.0, f"Out of range for input {val}: {result}"


class TestNowUtc:

    def test_returns_iso_string(self, isolated_base_path):
        from brain_v9.brain.utility import _now_utc
        ts = _now_utc()
        assert isinstance(ts, str)
        assert ts.endswith("Z")
        # Should be parseable — basic check for ISO format
        assert "T" in ts

    def test_no_plus_zero_offset(self, isolated_base_path):
        from brain_v9.brain.utility import _now_utc
        ts = _now_utc()
        assert "+00:00" not in ts  # Replaced with Z
