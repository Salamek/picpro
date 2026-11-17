from copy import deepcopy
from dataclasses import replace

import pytest

from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.exceptions import FuseError
from picpro.ProgrammingVariables import ProgrammingVariables, ProgrammingVariablesFlags

_CORE_TYPES = [
    ('bit16_a', 1, 16, 0xffff), ('bit16_b', 2, 16, 0xffff),
    ('bit14_g', 3, 14, 0x3fff), ('bit12_a', 4, 12, 0x0fff),
    ('bit14_a', 5, 14, 0x3fff), ('bit14_b', 6, 14, 0x3fff),
    ('bit14_c', 7, 14, 0x3fff), ('bit14_d', 8, 14, 0x3fff),
    ('bit14_e', 9, 14, 0x3fff), ('bit14_f', 10, 14, 0x3fff),
    ('bit12_b', 11, 12, 0x0fff), ('bit14_h', 12, 14, 0x3fff),
    ('bit16_c', 13, 16, 0xffff), ('newf12b', 11, 12, 0x0fff),
]
_REQUIRED_FIELDS = [
    'chip_name', 'include', 'erase_mode', 'flash_chip', 'power_sequence',
    'program_delay', 'program_tries', 'over_program', 'core_type', 'rom_size',
    'eeprom_size', 'fuse_blank', 'cp_warn', 'cal_word', 'band_gap', 'icsp_only',
    'chip_id', 'fuses',
]


@pytest.fixture
def valid_data() -> dict:
    return {
        'chip_name': 'testchip', 'include': True, 'socket_image': 'dip28',
        'erase_mode': 3, 'flash_chip': True, 'power_sequence': 'VccFastVpp1',
        'program_delay': 10, 'program_tries': 2, 'over_program': 3,
        'core_type': 'bit14_c', 'rom_size': 8192, 'eeprom_size': 128,
        'fuse_blank': [0x3fff, 0x3fff], 'cp_warn': False, 'cal_word': False,
        'band_gap': False, 'icsp_only': False, 'chip_id': 0xba0,
        'fuses': {
            'MODE': {
                'Default': [(0, 0x3fff), (1, 0x3fff)],
                'First': [(0, 0x3ffe), (1, 0x3fff)],
                'Both': [(0, 0x3ffc), (1, 0x3ffd)],
            },
            'WDT': {'Enabled': [(1, 0x3fff)], 'Disabled': [(1, 0x3ff7)]},
        },
    }


@pytest.fixture
def entry(valid_data: dict) -> ChipInfoEntry:
    return ChipInfoEntry.from_dict(valid_data)


def test_dictionary_round_trip(valid_data: dict) -> None:
    original = deepcopy(valid_data)
    entry = ChipInfoEntry.from_dict(valid_data)
    assert entry.to_dict() == original
    assert valid_data == original
    assert ChipInfoEntry.from_dict(entry.to_dict()) == entry


@pytest.mark.parametrize('field', _REQUIRED_FIELDS)
@pytest.mark.parametrize('invalid', ['missing', 'null', 'wrong_type'])
def test_required_fields(valid_data: dict, field: str, invalid: str) -> None:
    if invalid == 'missing':
        del valid_data[field]
    elif invalid == 'null':
        valid_data[field] = None
    else:
        valid_data[field] = object()
    message = f'{field} has wrong type' if invalid == 'wrong_type' else f'{field} was not provided'
    with pytest.raises(TypeError, match=message):
        ChipInfoEntry.from_dict(valid_data)


@pytest.mark.parametrize('omit_socket', [False, True])
def test_optional_socket(valid_data: dict, *, omit_socket: bool) -> None:
    if omit_socket:
        del valid_data['socket_image']
    else:
        valid_data['socket_image'] = None
    entry = ChipInfoEntry.from_dict(valid_data)
    assert entry.socket_image is None
    assert entry.pin1_location_text == 'No socket'


@pytest.mark.parametrize(('core_type', 'core_number', 'bits', 'blank'), _CORE_TYPES)
def test_core_architecture(entry: ChipInfoEntry, core_type: str, core_number: int, bits: int, blank: int) -> None:
    chip = replace(entry, core_type=core_type)
    assert chip.core_bits == bits
    assert chip.rom_blank_word == blank
    assert chip.programming_variables.core_type == core_number
    assert chip.programming_variables.flags.flag_18f_single_panel_access_mode == (core_type == 'bit16_a')


@pytest.mark.parametrize('property_name', ['programming_variables', 'core_bits', 'rom_blank_word'])
def test_unknown_core(entry: ChipInfoEntry, property_name: str) -> None:
    chip = replace(entry, core_type='unknown')
    with pytest.raises(ValueError, match='Failed to'):
        getattr(chip, property_name)


@pytest.mark.parametrize(('sequence', 'wire_value', 'delay'), [
    ('Vcc', 0, False), ('VccVpp1', 1, False), ('VccVpp2', 2, False),
    ('Vpp1Vcc', 3, False), ('Vpp2Vcc', 4, False),
    ('VccFastVpp1', 1, True), ('VccFastVpp2', 2, True),
])
def test_programming_variables(entry: ChipInfoEntry, sequence: str, wire_value: int, *, delay: bool) -> None:
    chip = replace(entry, power_sequence=sequence, cal_word=True, band_gap=True)
    assert chip.programming_variables == ProgrammingVariables(
        rom_size_words=4096, eeprom_size=128, core_type=7,
        flags=ProgrammingVariablesFlags(
            flag_calibration_value_in_rom=True, flag_band_gap_fuse=True,
            flag_18f_single_panel_access_mode=False, flag_vcc_vpp_delay=delay,
        ),
        program_delay=10, power_sequence=wire_value, erase_mode=3,
        program_retries=2, over_program=3,
    )
    assert chip.rom_size == 8192


def test_programming_flags_disabled(entry: ChipInfoEntry) -> None:
    chip = replace(entry, power_sequence='Vcc', cal_word=False, band_gap=False)
    assert chip.programming_variables.flags.to_int() == 0


@pytest.mark.parametrize(('size', 'expected'), [(0, False), (128, True)])
def test_has_eeprom(entry: ChipInfoEntry, size: int, *, expected: bool) -> None:
    assert replace(entry, eeprom_size=size).has_eeprom is expected


@pytest.mark.parametrize(('socket', 'expected'), [
    ('8pin', 'socket pin 13'), ('14pin', 'socket pin 13'), ('18pin', 'socket pin 2'),
    ('28Npin', 'socket pin 1'), ('40pin', 'socket pin 1'),
    ('dip8', 'socket pin 13'), ('dip14', 'socket pin 13'), ('dip18', 'socket pin 2'),
    ('dip28', 'socket pin 1'), ('dip40', 'socket pin 1'), (None, 'No socket'),
])
def test_socket_locations(entry: ChipInfoEntry, socket: str | None, expected: str) -> None:
    assert replace(entry, socket_image=socket).pin1_location_text == expected


def test_encode_fuses_across_words(entry: ChipInfoEntry) -> None:
    before = deepcopy(entry.to_dict())
    settings = {'MODE': 'Both', 'WDT': 'Disabled'}
    assert entry.encode_fuse_data(settings) == [0x3ffc, 0x3ff5]
    assert entry.to_dict() == before
    assert settings == {'MODE': 'Both', 'WDT': 'Disabled'}


def test_encode_no_settings_returns_blank_copy(entry: ChipInfoEntry) -> None:
    result = entry.encode_fuse_data({})
    assert result == [0x3fff, 0x3fff]
    result[0] = 0
    assert entry.fuse_blank == [0x3fff, 0x3fff]


@pytest.mark.parametrize(('settings', 'message'), [
    ({'UNKNOWN': 'Enabled'}, 'Unknown fuse "UNKNOWN"'),
    ({'WDT': 'UNKNOWN'}, 'Invalid fuse setting: "WDT" = "UNKNOWN"'),
])
def test_invalid_fuse_settings(entry: ChipInfoEntry, settings: dict, message: str) -> None:
    with pytest.raises(FuseError, match=message):
        entry.encode_fuse_data(settings)


@pytest.mark.parametrize('reverse_options', [False, True])
def test_decode_most_specific_settings(entry: ChipInfoEntry, *, reverse_options: bool) -> None:
    if reverse_options:
        entry.fuses = {name: dict(reversed(list(options.items()))) for name, options in entry.fuses.items()}
    values = [0x3ffc, 0x3ff5]
    before = deepcopy(entry.to_dict())
    assert entry.decode_fuse_data(values) == {'MODE': 'Both', 'WDT': 'Disabled'}
    assert values == [0x3ffc, 0x3ff5]
    assert entry.to_dict() == before


def test_decode_all_ones_default(entry: ChipInfoEntry) -> None:
    chip = replace(entry, core_type='bit16_a', fuse_blank=[0xffff], fuses={
        'WDT': {'Enabled': [(0, 0xffff)], 'Disabled': [(0, 0xfffe)]},
    })
    assert chip.decode_fuse_data([0xffff]) == {'WDT': 'Enabled'}


def test_decode_unrecognized_setting(entry: ChipInfoEntry) -> None:
    chip = replace(entry, fuses={'WDT': {'Disabled': [(0, 0x3ffe)]}})
    with pytest.raises(FuseError, match='Could not identify fuse setting'):
        chip.decode_fuse_data([0x3fff])


def test_no_fuses(entry: ChipInfoEntry) -> None:
    chip = replace(entry, fuses={}, fuse_blank=[])
    assert chip.decode_fuse_data([]) == {}
    assert chip.encode_fuse_data({}) == []
    assert chip.fuse_doc == ''


def test_fuse_documentation(entry: ChipInfoEntry) -> None:
    assert entry.fuse_doc == "'MODE' : ('Default', 'First', 'Both')\n'WDT' : ('Enabled', 'Disabled')\n"
