

if __name__ == "__main__":
    test_valid_event()
    test_missing_trade_id()
    test_missing_product()
    test_missing_volume_mwh()
    test_zero_volume_mwh()
    test_negative_volume_mwh()
    test_string_volume_mwh()
    test_boolean_volume_mwh()

    print("All tests passed")
