import pytest

from picpro.protocol.ChipConfig import ChipConfig


def test_from_bytes() -> None:
    chip_config = ChipConfig.from_bytes(bytes.fromhex('cb0f0000070fffffffffcd31ff3fff3fffffffffffffffffff3f'))
    assert chip_config.chip_id == 4043
    assert chip_config.id == b'\x00\x00\x07\x0f\xff\xff\xff\xff'
    assert chip_config.fuses == [12749, 16383, 16383, 65535, 65535, 65535, 65535]
    assert chip_config.calibrate == 16383


def test_to_bytes() -> None:
    chip_config = ChipConfig(
        chip_id=4043,
        id=b'\x00\x00\x07\x0f\xff\xff\xff\xff',
        fuses=[12749, 16383, 16383, 65535, 65535, 65535, 65535],
        calibrate=16383
    )

    expect = bytes.fromhex('cb0f0000070fffffffffcd31ff3fff3fffffffffffffffffff3f')

    assert chip_config.to_bytes() == expect

