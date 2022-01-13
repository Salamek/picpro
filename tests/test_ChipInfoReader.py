import os
import pytest
from picpro.ChipInfoReader import ChipInfoReader


@pytest.fixture(scope="function")  # type: ignore
def chip_data_path() -> str:
    this_dir = os.path.dirname(os.path.realpath(__file__))
    return os.path.join(this_dir, 'test_chip_data.cid')


def test_be_constructed_with(chip_data_path: str) -> None:
    ChipInfoReader(chip_data_path)


def test_not_file() -> None:
    with pytest.raises(FileNotFoundError):
        ChipInfoReader('Muhehe')


def test_get_chip(chip_data_path: str) -> None:
    chip_info_reader = ChipInfoReader(chip_data_path)

    expect = {
        'chip_name': '10f200',
        'include': True,
        'socket_image': '0pin',
        'erase_mode': 6,
        'flash_chip': True,
        'power_sequence': 'VccVpp1',
        'program_delay': 20,
        'core_type': None,
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
                'Disabled': [(0, 16379)]
            },
            'Code Protect': {
                'Disabled': [(0, 16383)],
                'Enabled': [(0, 16375)]
            },
            'MCLRE': {
                'Enabled': [(0, 16383)],
                'Disabled': [(0, 16367)]
            }
        },
        'program_tries': 1,
        'over_program': 0
    }

    chip_info = chip_info_reader.get_chip('10F200')

    assert chip_info.to_dict() == expect


def test_get_chip_multiple_fuses(chip_data_path: str) -> None:
    chip_info_reader = ChipInfoReader(chip_data_path)

    expect = {
        'chip_name': '16f737',
        'include': True,
        'socket_image': '28Npin',
        'erase_mode': 3,
        'flash_chip': True,
        'power_sequence': 'VccFastVpp1',
        'program_delay': 10,
        'core_type': 7,
        'rom_size': 4096,
        'eeprom_size': 0,
        'fuse_blank': [16383, 16383],
        'cp_warn': False,
        'cal_word': False,
        'band_gap': False,
        'icsp_only': False,
        'chip_id': 2976,
        'fuses': {
            'WDT': {
                'Enabled': [(0, 16383)],
                'Disabled': [(0, 16379)]
            },
            'PWRTE': {
                'Disabled': [(0, 16383)],
                'Enabled': [(0, 16375)]
            },
            'MCLRE': {
                'Enabled': [(0, 16383)],
                'Disabled': [(0, 16351)]
            },
            'BOREN': {
                'Enabled': [(0, 16383), (1, 16383)],
                'Sleep OFF': [(0, 16383), (1, 16319)],
                'SBOREN': [(0, 16319), (1, 16383)],
                'Disabled': [(0, 16319), (1, 16319)]
            },
            'Brownout Voltage': {
                '2.0V': [(0, 16383)],
                '2.7V': [(0, 16255)],
                '4.2V': [(0, 16127)],
                '4.5V': [(0, 15999)]
            },
            'CCP2 Mux': {
                'RC1': [(0, 16383)],
                'RB3': [(0, 12287)]
            },
            'Code Protect': {
                'Disabled': [(0, 16383)],
                'Enabled': [(0, 8191)]
            },
            'Oscillator': {
                'EXTRC_CLKOUT': [(0, 16383)],
                'EXTRC_IO': [(0, 16382)],
                'INTRC_CLKOUT': [(0, 16381)],
                'INTRC_IO': [(0, 16380)],
                'EXTCLK': [(0, 16367)],
                'HS': [(0, 16366)],
                'XT': [(0, 16365)],
                'LP': [(0, 16364)]
            },
            'Clock Monitor': {
                'Enabled': [(1, 16383)],
                'Disabled': [(1, 16382)]
            },
            'Int/Ext Switch': {
                'Enabled': [(1, 16383)],
                'Disabled': [(1, 16381)]
            }
        },
        'program_tries': 1,
        'over_program': 0
    }

    chip_info = chip_info_reader.get_chip('16F737')

    assert chip_info.to_dict() == expect
