import pytest
import json

from unittest.mock import Mock
from trade_result_persistence import (
    build_accepted_trade_artifact,
    build_rejected_trade_artifact,
    build_s3_key,
    put_json_object_to_s3,
)


def test_build_accepted_trade_artifact_returns_expected_shape():
    trade = {
        "trade_id": "TRD-001",
        "product": "POWER",
        "volume_mwh": 100,
    }

    validation = {
        "is_valid": True,
        "errors": [],
    }

    artifact = build_accepted_trade_artifact(
        trade=trade,
        validation=validation,
        processed_at="2026-06-02T18:30:00Z",
    )

    assert artifact["artifact_type"] == "accepted_trade"
    assert artifact["schema_version"] == "1.0"
    assert artifact["status"] == "ACCEPTED"
    assert artifact["trade_id"] == "TRD-001"
    assert artifact["processed_at"] == "2026-06-02T18:30:00Z"
    assert artifact["trade"] == trade
    assert artifact["validation"] == validation


def test_build_rejected_trade_artifact_returns_expected_shape():
    trade = {
        "trade_id": "TRD-002",
        "product": "POWER",
        "volume_mwh": 0,
    }

    validation = {
        "is_valid": False,
        "errors": ["volume_mwh must be greater than 0"],
    }

    artifact = build_rejected_trade_artifact(
        trade=trade,
        validation=validation,
        processed_at="2026-06-02T18:31:00Z",
    )

    assert artifact["artifact_type"] == "rejected_trade"
    assert artifact["schema_version"] == "1.0"
    assert artifact["status"] == "REJECTED"
    assert artifact["trade_id"] == "TRD-002"
    assert artifact["processed_at"] == "2026-06-02T18:31:00Z"
    assert artifact["trade"] == trade
    assert artifact["validation"] == validation
    assert artifact["rejection_reasons"] == ["volume_mwh must be greater than 0"]


def test_build_s3_key_for_accepted_trade():
    key = build_s3_key(
        result_type="accepted",
        trade_id="TRD-001",
        processed_at="2026-06-02T18:30:00Z",
    )

    assert key == (
        "trade-results/accepted/"
        "year=2026/month=06/day=02/"
        "trade_id=TRD-001.json"
    )


def test_build_s3_key_for_rejected_trade():
    key = build_s3_key(
        result_type="rejected",
        trade_id="TRD-002",
        processed_at="2026-06-02T18:31:00Z",
    )

    assert key == (
        "trade-results/rejected/"
        "year=2026/month=06/day=02/"
        "trade_id=TRD-002.json"
    )


def test_build_s3_key_rejects_unsupported_result_type():
    with pytest.raises(ValueError, match="Unsupported result_type"):
        build_s3_key(
            result_type="failed",
            trade_id="TRD-003",
            processed_at="2026-06-02T18:32:00Z",
        )


def test_build_s3_key_allows_custom_base_prefix():
    key = build_s3_key(
        result_type="accepted",
        trade_id="TRD-004",
        processed_at="2026-06-02T18:33:00Z",
        base_prefix="custom-prefix",
    )

    assert key == (
        "custom-prefix/accepted/"
        "year=2026/month=06/day=02/"
        "trade_id=TRD-004.json"
    )


def test_put_json_object_to_s3_calls_put_object_with_expected_arguments():
    s3_client = Mock()

    body = {
        "artifact_type": "accepted_trade",
        "trade_id": "TRD-001",
        "status": "ACCEPTED",
    }

    put_json_object_to_s3(
        s3_client=s3_client,
        bucket_name="test-bucket",
        object_key="trade-results/accepted/year=2026/month=06/day=02/trade_id=TRD-001.json",
        body=body,
    )

    s3_client.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="trade-results/accepted/year=2026/month=06/day=02/trade_id=TRD-001.json",
        Body=json.dumps(body),
        ContentType="application/json",
    )


def test_build_s3_key_sanitises_trade_id():
    key = build_s3_key(
        result_type="accepted",
        trade_id="TRD 001 / bad",
        processed_at="2026-06-02T18:30:00Z",
    )

    assert key == (
        "trade-results/accepted/"
        "year=2026/month=06/day=02/"
        "trade_id=TRD-001-bad.json"
    )