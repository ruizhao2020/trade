from app.adapters.futures_adapter import _to_minute_contract


def test_main_continuous_code_is_normalized_for_minute_resolution():
    assert _to_minute_contract("RB0") == "RB0"
    assert _to_minute_contract("v0") == "V0"
    assert _to_minute_contract("RB2610") == "RB2610"
