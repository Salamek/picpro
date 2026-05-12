
import pytest

from picpro.ChipInfoEntry import ChipInfoEntry

_base_valid_data = {
    'chip_name': '10f200',
    'include': True,
    'socket_image': '0pin',
    'erase_mode': 6,
    'flash_chip': True,
    'power_sequence': 'VccVpp1',
    'program_delay': 20,
    'core_type': 'newf12b',
    'rom_size': 256,
    'eeprom_size': 0,
    'fuse_blank': [4095],
    'cp_warn': False,
    'cal_word': True,
    'band_gap': False,
    'icsp_only': True,
    'chip_id': 65535,
    'fuses': {
        'WDT': {
            'Enabled': [(0, 16383)],
            'Disabled': [(0, 16379)],
        },
        'Code Protect': {
            'Disabled': [(0, 16383)],
            'Enabled': [(0, 16375)],
        },
        'MCLRE': {
            'Enabled': [(0, 16383)],
            'Disabled': [(0, 16367)],
        },
    },
    'program_tries': 1,
    'over_program': 0,
}

def test_from_dict() -> None:
    ChipInfoEntry.from_dict(_base_valid_data)

def test_core_bits_16() -> None:
    _base_valid_data['core_type'] = 'bit16_b'
    chip_info = ChipInfoEntry.from_dict(_base_valid_data)

    assert chip_info.core_bits == 16

def test_core_bits_14() -> None:
    _base_valid_data['core_type'] = 'bit14_b'
    chip_info = ChipInfoEntry.from_dict(_base_valid_data)
    assert chip_info.core_bits == 14

def test_core_bits_12() -> None:
    _base_valid_data['core_type'] = 'bit12_b'
    chip_info = ChipInfoEntry.from_dict(_base_valid_data)
    assert chip_info.core_bits == 12

def test_wrong_value_from_dict() -> None:
    _base_valid_data['core_type'] = 10
    with pytest.raises(TypeError, match=r'core_type has wrong type, expected str'):
        ChipInfoEntry.from_dict(_base_valid_data)

def test_unknown_core_type() -> None:
    _base_valid_data['core_type'] = 'bullshit'
    chip_info = ChipInfoEntry.from_dict(_base_valid_data)
    with pytest.raises(ValueError, match=r'Failed to identify core_type.'):
        _a = chip_info.programming_variables

def test_unknown_core_bits() -> None:
    _base_valid_data['core_type'] = 'bullshit'
    chip_info = ChipInfoEntry.from_dict(_base_valid_data)
    with pytest.raises(ValueError, match=r'Failed to detect core bits.'):
        _a = chip_info.core_bits
