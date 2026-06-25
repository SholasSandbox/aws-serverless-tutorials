from eventbridge_trade_handler import eventbridge_trade_handler
from trade_handler import STATUS_RECEIVED


def test_eventbridge_trade_handler_valid_trade_returns_received():
    event = {
        "id": "evt-12345",
        "detail": {
            "trade_id": "TRD-1001",
            "product": "UK Power",
            "volume_mwh": 250,
        },
    }

    response = eventbridge_trade_handler(event, None)

    assert response["status"] == STATUS_RECEIVED
    assert response["request_id"] == "evt-12345"
    assert response["trade"]["trade_id"] == "TRD-1001"


def test_eventbridge_trade_handler_invalid_volume_mwh_returns_rejected():
    event = {
        "id": "evt-12345",
        "detail": {
            "trade_id": "TRD-1001",
            "product": "UK Power",
            "volume_mwh": 0,
        },
    }

    response = eventbridge_trade_handler(event, None)

    assert response["status"] == "rejected"
    assert response["request_id"] == "evt-12345"
    assert response["error"] == "volume_mwh must be greater than 0"
