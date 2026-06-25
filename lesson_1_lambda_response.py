import json
from typing import Any


def lambda_handler(event: dict[str, Any], context) -> dict[str, Any]:
    # trade_id, product, volume_mwh
    trade_id = event.get("trade_id")
    product = event.get("product")
    volume_mwh = event.get("volume_mwh")

    if trade_id is None:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing required field: trade_id"}),
        }
    if product is None:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing required field: product"}),
        }

    if volume_mwh is None:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing required field: volume_mwh"}),
        }

    response_body = {
        "trade_id": trade_id,
        "product": product,
        "volume_mwh": volume_mwh,
        "status": "received",
    }
    return {
        "statusCode": 200,
        "body": json.dumps(response_body),
    }


test_event = {
    "trade_id": "TRD-1001",
    "product": "UK Power",
    "volume_mwh": 250,
}

result = lambda_handler(test_event, None)
print(result)

test_event = {
    "product": "UK Power",
    "volume_mwh": 250,
}
result = lambda_handler(test_event, None)
print(result)

test_event = {
    "trade_id": "TRD-1001",
    "volume_mwh": 250,
}
result = lambda_handler(test_event, None)
print(result)

test_event = {
    "trade_id": "TRD-1001",
    "product": "UK Power",
}
result = lambda_handler(test_event, None)
print(result)
