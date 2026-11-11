import math

from analysis_core import summarize_binary_outcomes, wilson_interval


def test_wilson_interval_contains_observed_rate():
    lower, upper = wilson_interval(9, 10)

    assert lower < 0.9 < upper
    assert math.isclose(lower, 0.5958499732, rel_tol=1e-8)
    assert math.isclose(upper, 0.9821237869, rel_tol=1e-8)


def test_summarize_binary_outcomes_reports_lift_and_go_no_go():
    result = summarize_binary_outcomes(
        signal_successes=60,
        signal_total=100,
        control_successes=40,
        control_total=100,
        required_lift=0.10,
    )

    assert result["signal_rate"] == 0.60
    assert result["control_rate"] == 0.40
    assert math.isclose(result["lift_pp"], 20.0)
    assert result["lower_bound_exceeds_control"] is True
    assert result["passes_primary_gate"] is True


def test_empty_sample_is_explicitly_inconclusive():
    result = summarize_binary_outcomes(0, 0, 0, 0)

    assert result["signal_rate"] is None
    assert result["passes_primary_gate"] is False
    assert result["status"] == "INSUFFICIENT_SAMPLE"
