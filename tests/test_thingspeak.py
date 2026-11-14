from services.thingspeak import ThingSpeakPublisher, _mode_from_value, _state_from_bit


def test_maps_seven_fields_from_telemetry():
    fields = ThingSpeakPublisher.make_fields(
        24.56, 88.2,
        telemetry={"fan_state": "ON", "led_state": "OFF", "mode": "AUTO", "sensor_error": False},
        region_id=3,
    )
    assert fields == {
        "field1": 24.6,
        "field2": 88.2,
        "field3": 1,
        "field4": 0,
        "field5": 0,
        "field6": 1,
        "field7": 3,
    }


def test_unknown_hardware_states_are_not_guessed():
    fields = ThingSpeakPublisher.make_fields(23.0, 70.0, telemetry={}, region_id=None)
    assert fields == {"field1": 23.0, "field2": 70.0}


def test_readback_decoding():
    assert _state_from_bit("1") == "ON"
    assert _state_from_bit("0") == "OFF"
    assert _state_from_bit(0.5) is None
    assert _mode_from_value("0") == "AUTO"
    assert _mode_from_value("1") == "MANUAL"
