"""Tests for the parts that decide the numbers and the agent's safety. No data or model needed."""
import numpy as np
import pytest

import agent
import check

rng = np.random.default_rng(0)
STRANGER =  rng.normal(0.2, 0.1, 20000)


@pytest.mark.parametrize("far", [0.01, 0.001])
def test_threshold_lets_in_at_most_the_limit(far):
    t = check.threshold_for_far(STRANGER, far)
    assert np.mean(STRANGER >= t) <= far




def test_error_rates_by_hand():
    far, frr = check.error_rates([0.9, 0.4], [0.1, 0.6, 0.2, 0.3], threshold=0.5)
    assert (far, frr) == (0.25, 0.5)  # 1 of 4 strangers in, 1 of 2 owner attempts out


def test_interval_rule_of_three():
    lo, hi = check.interval(0, 3000)  # no errors in 3,000 trials
    assert lo == 0 and hi == pytest.approx(0.00123, abs=1e-5)



@pytest.mark.parametrize("voice", ["private", "low-risk", "unsure", "reject"])
def test_payment_always_needs_the_phone(voice):
    assert agent.next_step("pay", voice) == "confirm on phone"


def test_private_actions_need_the_strict_limit():
    assert agent.next_step("read_messages", "private") == "do it"
    assert agent.next_step("read_messages", "low-risk") != "do it"
    assert agent.next_step("calendar", "low-risk") == "do it"


def test_unsure_asks_a_phrase_then_the_phone():
    assert agent.next_step("read_messages", "unsure") == "ask to repeat a random phrase"
    assert agent.next_step("read_messages", "unsure", phrase_asked=True) == "confirm on phone"


def test_lockout_after_three_failures():
    assert agent.next_step("calendar", "private", failures=3) == "confirm on phone"
