from step_functions_validate_trade_handler import step_functions_validate_trade_handler
from trade_validation import build_internal_trade


def test_build_internal_trade():
    request_body = {
        "trade_id": "TRD-1001",
        "product": "UK Power",
        "volume_mwh": 250,
        "external_comment": "Client supplied value",
    }

    internal_trade = build_internal_trade(request_body)

    validation_result = step_functions_validate_trade_handler(
        internal_trade,
        None,
    )

    assert internal_trade == {
        "trade_id": "TRD-1001",
        "product": "UK Power",
        "volume_mwh": 250,
    }
    assert validation_result == {
        "is_valid": True,
        "error": None,
    }
