import pytest
from pathlib import Path

from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.ChipInfoReader import ChipInfoReader
from picpro.ProgrammingVariables import ProgrammingVariables
from picpro.exceptions import FuseError


def test_be_constructed_with(chip_data_path: Path) -> None:
    ChipInfoReader(chip_data_path)


def test_not_file() -> None:
    with pytest.raises(FileNotFoundError):
        ChipInfoReader(Path('Muhehe'))


def test_get_chip(chip_info_reader: ChipInfoReader) -> None:

    expect = {
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


def test_get_chip_programing_vars(chip_info_reader: ChipInfoReader) -> None:

    expect = ProgrammingVariables(
        rom_size=4096,
        eeprom_size=0,
        core_type=7,
        flag_calibration_value_in_rom=False,
        flag_band_gap_fuse=False,
        flag_vcc_vpp_delay=True,
        flag_18f_single_panel_access_mode=False,
        program_delay=10,
        power_sequence=1,
        erase_mode=3,
        program_retries=1,
        over_program=0,
        fuse_blank=[16383, 16383]
    )

    chip_info = chip_info_reader.get_chip('16f737')

    assert chip_info.programming_vars == expect


def test_get_chip_multiple_fuses(chip_info_reader: ChipInfoReader) -> None:
    chip_info_entry = chip_info_reader.get_chip('16f737')
    expect = {
        'chip_name': '16f737',
        'include': True,
        'socket_image': '28Npin',
        'erase_mode': 3,
        'flash_chip': True,
        'power_sequence': 'VccFastVpp1',
        'program_delay': 10,
        'core_type': 'bit14_c',
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

    assert chip_info_entry.to_dict() == expect


def test_has_eeprom(chip_info_entry: ChipInfoEntry) -> None:
    assert chip_info_entry.has_eeprom == True


def test_pin1_location_text(chip_info_entry: ChipInfoEntry) -> None:
    assert chip_info_entry.pin1_location_text == 'socket pin 13'


def test_fuse_doc(chip_info_entry: ChipInfoEntry) -> None:
    expected = """'WDT' : ('Enabled', 'Disabled')
'PWRTE' : ('Disabled', 'Enabled')
'MCLRE' : ('Enabled', 'Disabled')
'BODEN' : ('Enabled', 'Disabled')
'Code Protect ROM' : ('Disabled', 'Enabled')
'Code Protect EEP' : ('Disabled', 'Enabled')
'Bandgap' : ('Highest', 'Mid High', 'Mid Low', 'Lowest')
'Oscillator' : ('RC CLKGP4 RCGP5', 'RC IOGP4 RCGP5', 'INTOSC CLKGP4 IOGP5', 'INTOSC IOGP4 IOGP5', 'EC IOGP4 CLKINGP5', 'HS', 'XT', 'LP')
"""
    assert chip_info_entry.fuse_doc == expected


def test_decode_fuse_data(chip_info_entry: ChipInfoEntry) -> None:
    expected = {
        'BODEN': 'Enabled',
        'Bandgap': 'Highest',
        'Code Protect EEP': 'Disabled',
        'Code Protect ROM': 'Disabled',
        'MCLRE': 'Enabled',
        'Oscillator': 'RC CLKGP4 RCGP5',
        'PWRTE': 'Disabled',
        'WDT': 'Enabled'
    }
    assert chip_info_entry.decode_fuse_data([12799, 16383, 16383, 65535, 65535, 65535, 65535]) == expected


def test_decode_fuse_data_bad(chip_info_entry: ChipInfoEntry) -> None:
    with pytest.raises(FuseError):
        chip_info_entry.decode_fuse_data([99999])

def test_encode_fuse_data(chip_info_entry: ChipInfoEntry) -> None:
    fuse_data = {
        'BODEN': 'Enabled',
        'Bandgap': 'Highest',
        'Code Protect EEP': 'Disabled',
        'Code Protect ROM': 'Disabled',
        'MCLRE': 'Enabled',
        'Oscillator': 'RC CLKGP4 RCGP5',
        'PWRTE': 'Disabled',
        'WDT': 'Enabled'
    }

    expected = [12799]
    assert chip_info_entry.encode_fuse_data(fuse_data) == expected

def test_encode_fuse_data_bad_fuse(chip_info_entry: ChipInfoEntry) -> None:
    fuse_data = {
        'BlaBla': 'Enabled',
    }

    with pytest.raises(FuseError):
        chip_info_entry.encode_fuse_data(fuse_data)


def test_encode_fuse_data_bad_settings(chip_info_entry: ChipInfoEntry) -> None:
    fuse_data = {
        'BODEN': 'BlaBla',
    }

    with pytest.raises(FuseError):
        chip_info_entry.encode_fuse_data(fuse_data)