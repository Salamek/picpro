import struct
from dataclasses import replace

import pytest

from picpro.ProgrammingVariables import ProgrammingVariables, ProgrammingVariablesFlags

# Protocol command 3: ROM words (2), EEPROM bytes (2), core, flags,
# delay, power sequence, erase mode, retries, over-program count.
_PACKET = bytes.fromhex('1240 0200 0d 0b 7f 04 06 02 03')
_FIELD_LAYOUT = {
    'rom_size_words': (0, 2), 'eeprom_size': (2, 2), 'core_type': (4, 1),
    'program_delay': (6, 1), 'power_sequence': (7, 1), 'erase_mode': (8, 1),
    'program_retries': (9, 1), 'over_program': (10, 1),
}


def _with_numeric_field(variables: ProgrammingVariables, field: str, value: int) -> ProgrammingVariables:
    assert field in _FIELD_LAYOUT
    updated = replace(variables)
    setattr(updated, field, value)
    return updated


@pytest.fixture
def variables() -> ProgrammingVariables:
    return ProgrammingVariables(
        rom_size_words=0x1240, eeprom_size=0x0200, core_type=13,
        flags=ProgrammingVariablesFlags(
            flag_calibration_value_in_rom=True, flag_band_gap_fuse=True,
            flag_18f_single_panel_access_mode=False, flag_vcc_vpp_delay=True,
        ),
        program_delay=0x7f, power_sequence=4, erase_mode=6,
        program_retries=2, over_program=3,
    )


@pytest.mark.parametrize(('mask', 'calibration', 'band_gap', 'single_panel', 'delay'), [
    (0x00, False, False, False, False),
    (0x01, True, False, False, False),
    (0x02, False, True, False, False),
    (0x04, False, False, True, False),
    (0x08, False, False, False, True),
    (0x0f, True, True, True, True),
])
def test_flag_bit_positions(mask: int, *, calibration: bool, band_gap: bool, single_panel: bool, delay: bool) -> None:
    flags = ProgrammingVariablesFlags(
        flag_calibration_value_in_rom=calibration, flag_band_gap_fuse=band_gap,
        flag_18f_single_panel_access_mode=single_panel, flag_vcc_vpp_delay=delay,
    )
    assert flags.to_int() == mask
    assert ProgrammingVariablesFlags.from_int(mask) == flags


@pytest.mark.parametrize('mask', range(16))
def test_all_flag_combinations_round_trip(mask: int) -> None:
    flags = ProgrammingVariablesFlags.from_int(mask)
    assert flags.to_int() == mask
    assert ProgrammingVariablesFlags.from_int(flags.to_int()) == flags


@pytest.mark.parametrize(('wire_flags', 'known_flags'), [(0x10, 0), (0x80, 0), (0xf0, 0), (0x81, 1), (0xff, 15)])
def test_reserved_flag_bits_ignored(wire_flags: int, known_flags: int) -> None:
    assert ProgrammingVariablesFlags.from_int(wire_flags) == ProgrammingVariablesFlags.from_int(known_flags)
    packet = bytearray(_PACKET)
    packet[5] = wire_flags
    parsed = ProgrammingVariables.from_bytes(bytes(packet))
    assert parsed.flags.to_int() == known_flags
    assert parsed.to_bytes()[5] == known_flags


def test_exact_wire_encoding(variables: ProgrammingVariables) -> None:
    assert variables.to_bytes() == _PACKET
    assert len(variables.to_bytes()) == 11


def test_exact_wire_decoding(variables: ProgrammingVariables) -> None:
    assert ProgrammingVariables.from_bytes(_PACKET) == variables


@pytest.mark.parametrize('mask', range(16))
def test_packet_round_trip_with_all_flags(variables: ProgrammingVariables, mask: int) -> None:
    expected = replace(variables, flags=ProgrammingVariablesFlags.from_int(mask))
    packet = expected.to_bytes()
    assert packet[5] == mask
    assert ProgrammingVariables.from_bytes(packet) == expected


@pytest.mark.parametrize('core_type', range(1, 14))
def test_supported_core_types(variables: ProgrammingVariables, core_type: int) -> None:
    expected = replace(variables, core_type=core_type)
    assert ProgrammingVariables.from_bytes(expected.to_bytes()) == expected


@pytest.mark.parametrize('sequence', range(5))
def test_supported_power_sequences(variables: ProgrammingVariables, sequence: int) -> None:
    expected = replace(variables, power_sequence=sequence)
    assert ProgrammingVariables.from_bytes(expected.to_bytes()) == expected


@pytest.mark.parametrize(('field', 'value'), [
    ('rom_size_words', 32), ('rom_size_words', 0xffe0),
    ('eeprom_size', 0), ('eeprom_size', 32), ('eeprom_size', 0xffe0),
    ('program_delay', 0), ('program_delay', 255),
    ('erase_mode', 0), ('erase_mode', 255),
    ('program_retries', 1), ('program_retries', 255),
    ('over_program', 0), ('over_program', 255),
])
def test_field_boundaries(variables: ProgrammingVariables, field: str, value: int) -> None:
    expected = _with_numeric_field(variables, field, value)
    assert ProgrammingVariables.from_bytes(expected.to_bytes()) == expected


@pytest.mark.parametrize(('field', 'value', 'message'), [
    ('rom_size_words', 0, 'rom_size_words cannot be empty'),
    ('rom_size_words', 1, 'rom_size_words has to be multiple of 32'),
    ('rom_size_words', 31, 'rom_size_words has to be multiple of 32'),
    ('rom_size_words', 33, 'rom_size_words has to be multiple of 32'),
    ('rom_size_words', 65535, 'rom_size_words has to be multiple of 32'),
    ('eeprom_size', 1, 'eeprom_size has to be multiple of 32'),
    ('eeprom_size', 31, 'eeprom_size has to be multiple of 32'),
    ('eeprom_size', 33, 'eeprom_size has to be multiple of 32'),
    ('eeprom_size', 65535, 'eeprom_size has to be multiple of 32'),
    ('core_type', 0, 'Unknown core_type'), ('core_type', 14, 'Unknown core_type'),
    ('core_type', 255, 'Unknown core_type'),
    ('power_sequence', 5, 'Unknown power_sequence'), ('power_sequence', 255, 'Unknown power_sequence'),
    ('program_retries', 0, 'program_retries has to be at least 1'),
])
def test_invalid_wire_values(field: str, value: int, message: str) -> None:
    # Construct malformed input independently of the serializer under test.
    packet = bytearray(_PACKET)
    offset, size = _FIELD_LAYOUT[field]
    packet[offset:offset + size] = value.to_bytes(size, 'big')
    with pytest.raises(ValueError, match=message):
        ProgrammingVariables.from_bytes(bytes(packet))


@pytest.mark.parametrize('size', [0, 1, 10, 12, 22])
def test_invalid_packet_length(size: int) -> None:
    packet = (_PACKET + bytes(11))[:size]
    with pytest.raises(struct.error, match='buffer of 11 bytes'):
        ProgrammingVariables.from_bytes(packet)


@pytest.mark.parametrize('field', ['rom_size_words', 'eeprom_size'])
@pytest.mark.parametrize('value', [-1, 65536])
def test_word_fields_cannot_overflow(variables: ProgrammingVariables, field: str, value: int) -> None:
    invalid = _with_numeric_field(variables, field, value)
    with pytest.raises(struct.error, match=r'requires|out of range'):
        invalid.to_bytes()


@pytest.mark.parametrize('field', ['core_type', 'program_delay', 'power_sequence', 'erase_mode', 'program_retries', 'over_program'])
@pytest.mark.parametrize('value', [-1, 256])
def test_byte_fields_cannot_overflow(variables: ProgrammingVariables, field: str, value: int) -> None:
    invalid = _with_numeric_field(variables, field, value)
    with pytest.raises(struct.error, match=r'requires|out of range'):
        invalid.to_bytes()
