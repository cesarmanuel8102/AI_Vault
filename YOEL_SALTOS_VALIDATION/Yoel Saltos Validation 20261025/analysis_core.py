import math


def wilson_interval(successes, total, z=1.959963984540054):
    if total <= 0:
        return None, None
    probability = successes / total
    denominator = 1 + z * z / total
    center = (probability + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            probability * (1 - probability) / total
            + z * z / (4 * total * total)
        )
        / denominator
    )
    return center - margin, center + margin


def summarize_binary_outcomes(
    signal_successes,
    signal_total,
    control_successes,
    control_total,
    required_lift=0.10,
):
    if signal_total <= 0 or control_total <= 0:
        return {
            "status": "INSUFFICIENT_SAMPLE",
            "signal_rate": None,
            "control_rate": None,
            "lift_pp": None,
            "signal_wilson_95": [None, None],
            "lower_bound_exceeds_control": False,
            "passes_primary_gate": False,
        }

    signal_rate = signal_successes / signal_total
    control_rate = control_successes / control_total
    lower, upper = wilson_interval(signal_successes, signal_total)
    lift = signal_rate - control_rate
    lower_exceeds_control = lower > control_rate
    return {
        "status": "OK",
        "signal_rate": signal_rate,
        "control_rate": control_rate,
        "lift_pp": lift * 100,
        "signal_wilson_95": [lower, upper],
        "lower_bound_exceeds_control": lower_exceeds_control,
        "passes_primary_gate": lift >= required_lift and lower_exceeds_control,
    }
