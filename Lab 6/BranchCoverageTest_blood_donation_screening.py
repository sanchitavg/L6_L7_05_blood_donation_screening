import pytest
from blood_donation_screening import process_donor_cohort, verify_storage_centrifuge


def cohort(donors, registered=True, ctype="standard", fast_track=False):
    return {
        "clinic_registered": registered,
        "type": ctype,
        "fast_track": fast_track,
        "donors": donors,
    }


def donor(age=25, weight=65, hb=14.0):
    return {"age": age, "weight_kg": weight, "hb": hb}


# ---- input validation: both operands of the 'or' ----
def test_not_a_list_raises():
    with pytest.raises(ValueError):
        process_donor_cohort({"a": 1}, 450)


def test_negative_volume_raises():
    with pytest.raises(ValueError):
        process_donor_cohort([], -5)


def test_empty_list_valid_gives_zero_yield():
    assert process_donor_cohort([], 450) == {"collected_ml": 0, "status": "ZERO_YIELD"}


# ---- registration branch ----
def test_registered_false_and_missing_key_are_skipped():
    cohorts = [cohort([donor()], registered=False), {"donors": [donor()]}]
    assert process_donor_cohort(cohorts, 450)["status"] == "ZERO_YIELD"


def test_registered_cohort_without_optional_keys_uses_defaults():
    # no "type", "donors", "fast_track" keys -> defaults used
    result = process_donor_cohort([{"clinic_registered": True}], 450)
    assert result == {"collected_ml": 0, "status": "ZERO_YIELD"}


# ---- eligibility: age / weight boundaries ----
@pytest.mark.parametrize("age,weight,expected", [
    (16, 65, 0),     # age just below limit
    (17, 65, 450),   # age at limit
    (25, 49, 0),     # weight just below limit
    (25, 50, 450),   # weight at limit
    (16, 49, 0),     # both fail
])
def test_age_weight_boundaries(age, weight, expected):
    result = process_donor_cohort([cohort([donor(age=age, weight=weight)])], 450)
    assert result["collected_ml"] == expected


def test_missing_donor_fields_default_to_deferred():
    result = process_donor_cohort([cohort([{}])], 450)
    assert result["collected_ml"] == 0


# ---- hemoglobin boundaries ----
@pytest.mark.parametrize("hb,expected", [
    (12.4, 0),
    (12.5, 450),
    (18.0, 450),
    (18.1, 0),
])
def test_hemoglobin_boundaries(hb, expected):
    result = process_donor_cohort([cohort([donor(hb=hb)])], 450)
    assert result["collected_ml"] == expected


def test_low_hb_in_standard_cohort_does_not_break_loop():
    result = process_donor_cohort([cohort([donor(hb=10.0), donor(), donor()])], 100)
    assert result["collected_ml"] == 200


def test_low_hb_in_high_altitude_cohort_breaks_and_resets():
    donors = [donor(), donor(), donor(hb=10.0), donor()]
    result = process_donor_cohort([cohort(donors, ctype="high_altitude")], 450)
    assert result["collected_ml"] == 0


def test_high_altitude_cohort_with_normal_hb_unaffected():
    result = process_donor_cohort([cohort([donor()], ctype="high_altitude")], 450)
    assert result["collected_ml"] == 450


def test_high_altitude_break_only_stops_that_cohort():
    cohorts = [
        cohort([donor(hb=10.0)], ctype="high_altitude"),
        cohort([donor()]),
    ]
    assert process_donor_cohort(cohorts, 450)["collected_ml"] == 450


# ---- fast track ----
def test_fast_track_true_and_false():
    assert process_donor_cohort([cohort([donor()], fast_track=True)], 450)["collected_ml"] == 500
    assert process_donor_cohort([cohort([donor()], fast_track=False)], 450)["collected_ml"] == 450


def test_fast_track_on_empty_cohort_gives_accepted_bonus():
    result = process_donor_cohort([cohort([], fast_track=True)], 450)
    assert result == {"collected_ml": 50, "status": "ACCEPTED"}


# ---- final status: deferral threshold 4 vs 5 ----
def test_four_deferrals_not_high_deferral():
    donors = [donor(age=10)] * 4 + [donor()]
    assert process_donor_cohort([cohort(donors)], 450)["status"] == "ACCEPTED"


def test_five_deferrals_high_deferral():
    donors = [donor(age=10)] * 5 + [donor()]
    result = process_donor_cohort([cohort(donors)], 450)
    assert result == {"collected_ml": 450, "status": "HIGH_DEFERRAL"}


# ---- centrifuge ----
def test_centrifuge_none_and_empty():
    assert verify_storage_centrifuge(None) == "NO_DATA"
    assert verify_storage_centrifuge([]) == "NO_DATA"


def test_centrifuge_two_consecutive_drops_abort():
    assert verify_storage_centrifuge([[2999, 2999]]) == "ABORT_SPIN"


def test_centrifuge_single_drop_then_recovery_is_stable():
    assert verify_storage_centrifuge([[3000, 2999, 3000, 2999, 3000]]) == "STABLE"


def test_centrifuge_boundary_3000_is_not_a_drop():
    assert verify_storage_centrifuge([[3000, 3000, 3000]]) == "STABLE"


def test_centrifuge_empty_run_is_stable():
    assert verify_storage_centrifuge([[]]) == "STABLE"


def test_centrifuge_streak_resets_between_runs():
    assert verify_storage_centrifuge([[2900], [2900]]) == "STABLE"


def test_centrifuge_abort_in_later_run():
    assert verify_storage_centrifuge([[3500, 3400], [3500, 2000, 1000]]) == "ABORT_SPIN"
