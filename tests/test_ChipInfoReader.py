from pathlib import Path
from zipfile import Path as ZipPath
from zipfile import ZipFile

import pytest

from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.ChipInfoReader import ChipInfoReader
from picpro.exceptions import FormatError, FuseError
from picpro.ProgrammingVariables import ProgrammingVariables, ProgrammingVariablesFlags


def test_be_constructed_with(chip_data_path: Path) -> None:
    ChipInfoReader(chip_data_path)


def test_not_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ChipInfoReader(tmp_path / 'missing.cid')


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
        'rom_size': 512,
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

    chip_info = chip_info_reader.get_chip('10F200')

    assert chip_info.to_dict() == expect


def test_get_chip_programing_vars(chip_info_reader: ChipInfoReader) -> None:
    flags = ProgrammingVariablesFlags(
        flag_calibration_value_in_rom=False,
        flag_band_gap_fuse=False,
        flag_vcc_vpp_delay=True,
        flag_18f_single_panel_access_mode=False,
    )

    expect = ProgrammingVariables(
        rom_size_words=4096,
        eeprom_size=0,
        core_type=7,
        flags=flags,
        program_delay=10,
        power_sequence=1,
        erase_mode=3,
        program_retries=1,
        over_program=0,
    )

    chip_info = chip_info_reader.get_chip('16f737')

    assert chip_info.programming_variables == expect


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
        'rom_size': 8192,
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
                'Disabled': [(0, 16379)],
            },
            'PWRTE': {
                'Disabled': [(0, 16383)],
                'Enabled': [(0, 16375)],
            },
            'MCLRE': {
                'Enabled': [(0, 16383)],
                'Disabled': [(0, 16351)],
            },
            'BOREN': {
                'Enabled': [(0, 16383), (1, 16383)],
                'Sleep OFF': [(0, 16383), (1, 16319)],
                'SBOREN': [(0, 16319), (1, 16383)],
                'Disabled': [(0, 16319), (1, 16319)],
            },
            'Brownout Voltage': {
                '2.0V': [(0, 16383)],
                '2.7V': [(0, 16255)],
                '4.2V': [(0, 16127)],
                '4.5V': [(0, 15999)],
            },
            'CCP2 Mux': {
                'RC1': [(0, 16383)],
                'RB3': [(0, 12287)],
            },
            'Code Protect': {
                'Disabled': [(0, 16383)],
                'Enabled': [(0, 8191)],
            },
            'Oscillator': {
                'EXTRC_CLKOUT': [(0, 16383)],
                'EXTRC_IO': [(0, 16382)],
                'INTRC_CLKOUT': [(0, 16381)],
                'INTRC_IO': [(0, 16380)],
                'EXTCLK': [(0, 16367)],
                'HS': [(0, 16366)],
                'XT': [(0, 16365)],
                'LP': [(0, 16364)],
            },
            'Clock Monitor': {
                'Enabled': [(1, 16383)],
                'Disabled': [(1, 16382)],
            },
            'Int/Ext Switch': {
                'Enabled': [(1, 16383)],
                'Disabled': [(1, 16381)],
            },
        },
        'program_tries': 1,
        'over_program': 0,
    }

    assert chip_info_entry.to_dict() == expect


def test_has_eeprom(chip_info_entry: ChipInfoEntry) -> None:
    assert chip_info_entry.has_eeprom


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
        'WDT': 'Enabled',
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
        'WDT': 'Enabled',
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


@pytest.fixture
def cid_block(chip_data_path: Path) -> str:
    return chip_data_path.read_text(encoding='utf-8').split('\n\n')[0]


@pytest.fixture
def cid_file(tmp_path: Path) -> Path:
    return tmp_path / 'chips.cid'


@pytest.mark.parametrize('name', ['12f675', '12F675'])
def test_case_insensitive_lookup(chip_info_reader: ChipInfoReader, name: str) -> None:
    assert chip_info_reader.get_chip(name).chip_name == '12f675'


def test_missing_chip(chip_info_reader: ChipInfoReader) -> None:
    with pytest.raises(KeyError):
        chip_info_reader.get_chip('unknown')


@pytest.mark.parametrize('content', ['', '\n\n', ' \t\n\n \n'])
def test_empty_file(cid_file: Path, content: str) -> None:
    cid_file.write_text(content, encoding='utf-8')
    assert ChipInfoReader(cid_file).chip_entries == {}


@pytest.mark.parametrize('ending', ['', '\n', '\n\n'])
def test_block_boundaries_and_whitespace(cid_file: Path, cid_block: str, ending: str) -> None:
    padded = '\n'.join(f' \t{line}\t ' for line in cid_block.splitlines())
    cid_file.write_text('\n\n' + padded + ending, encoding='utf-8')
    reader = ChipInfoReader(cid_file)
    assert list(reader.chip_entries) == ['10f200']
    chip = reader.get_chip('10f200')
    assert chip.core_type == 'newf12b'
    assert chip.rom_size == 512
    assert chip.programming_variables.rom_size_words == 256
    assert chip.power_sequence == 'VccVpp1'


@pytest.mark.parametrize(('raw', 'expected'), [('Y', True), ('y', True), ('1', True), ('N', False), ('n', False), ('0', False)])
def test_boolean_values(cid_file: Path, cid_block: str, raw: str, *, expected: bool) -> None:
    cid_file.write_text(cid_block.replace('INCLUDE=Y', f'INCLUDE={raw}'), encoding='utf-8')
    assert ChipInfoReader(cid_file).get_chip('10f200').include is expected


def test_explicit_programming_defaults(cid_file: Path, cid_block: str) -> None:
    cid_file.write_text(cid_block + '\nProgramTries=12\nOverProgram=10', encoding='utf-8')
    chip = ChipInfoReader(cid_file).get_chip('10f200')
    assert chip.program_tries == 12
    assert chip.over_program == 10


def test_legacy_metadata_optional(cid_file: Path, cid_block: str) -> None:
    content = cid_block.replace('ProgramFlag2=1\n', '').replace('PanelSizing=0\n', '')
    cid_file.write_text(content, encoding='utf-8')
    chip = ChipInfoReader(cid_file).get_chip('10f200')
    assert chip.program_tries == 1
    assert chip.over_program == 0


def test_socket_image_alias(cid_file: Path, cid_block: str) -> None:
    cid_file.write_text(cid_block.replace('KITSRUS.COM=0pin', 'SocketImage=8pin'), encoding='utf-8')
    assert ChipInfoReader(cid_file).get_chip('10f200').socket_image == '8pin'


def test_blank_fuses_whitespace(cid_file: Path, cid_block: str) -> None:
    cid_file.write_text(cid_block.replace('FUSEblank=0FFF', 'FUSEblank= 0fFf  \t 3fFf '), encoding='utf-8')
    assert ChipInfoReader(cid_file).get_chip('10f200').fuse_blank == [0x0fff, 0x3fff]


def test_fuse_options_start_at_specified_word(chip_info_reader: ChipInfoReader) -> None:
    block: dict = {'fuses': {}}
    chip_info_reader.parse_line(block, 'LIST12 FUSE2 "Mode" "Mixed Case"=aBcD&1234&fFfF "Off"=0000&0000&0000', 1)
    assert block['fuses'] == {
        'Mode': {
            'Mixed Case': [(1, 0xabcd), (2, 0x1234), (3, 0xffff)],
            'Off': [(1, 0), (2, 0), (3, 0)],
        },
    }


def test_blank_parse_line_ignored(chip_info_reader: ChipInfoReader) -> None:
    block: dict = {'fuses': {}}
    chip_info_reader.parse_line(block, ' \t', 1)
    assert block == {'fuses': {}}


@pytest.mark.parametrize(('original', 'replacement'), [
    ('INCLUDE=Y', 'Unknown=1'),
    ('INCLUDE=Y', 'garbage line'),
    ('ROMsize=000100', 'ROMsize=nothex'),
    ('ProgramDelay=20', 'ProgramDelay=notdecimal'),
    ('INCLUDE=Y', 'INCLUDE=maybe'),
    ('CoreType=NewF12B\n', ''),
    ('LIST1 FUSE1 "WDT" "Enabled"=3FFF "Disabled"=3FFB', 'LIST1 FUSE0 "WDT" "Enabled"=3FFF'),
    ('LIST1 FUSE1 "WDT" "Enabled"=3FFF "Disabled"=3FFB', 'LIST1 FUSE1 "WDT" "Enabled"=nothex'),
    ('LIST1 FUSE1 "WDT" "Enabled"=3FFF "Disabled"=3FFB', 'LIST1 FUSE1 "WDT" "Enabled"=3FFG'),
    ('LIST1 FUSE1 "WDT" "Enabled"=3FFF "Disabled"=3FFB', 'LIST1 FUSE1 "WDT" garbage "Enabled"=3FFF'),
    ('LIST1 FUSE1 "WDT" "Enabled"=3FFF "Disabled"=3FFB', 'LIST1 FUSE1 "WDT" "Enabled"=3FFF garbage "Disabled"=3FFB'),
])
def test_invalid_block_skipped_and_next_block_loaded(cid_file: Path, cid_block: str, caplog: pytest.LogCaptureFixture,
                                                     original: str, replacement: str) -> None:
    bad = cid_block.replace(original, replacement).replace('10F200', 'BAD')
    good = cid_block.replace('10F200', 'GOOD')
    cid_file.write_text(bad + '\n\n' + good, encoding='utf-8')
    reader = ChipInfoReader(cid_file)
    assert list(reader.chip_entries) == ['good']
    assert reader.get_chip('good').rom_size == 512
    assert len(caplog.records) == 1
    assert 'ignoring whole block' in caplog.records[0].getMessage()
    assert caplog.records[0].exc_info is not None
    assert isinstance(caplog.records[0].exc_info[1], FormatError)


@pytest.mark.parametrize('missing_field', [False, True])
def test_invalid_last_block_skipped(cid_file: Path, cid_block: str, caplog: pytest.LogCaptureFixture, *, missing_field: bool) -> None:
    bad = cid_block.replace('10F200', 'BAD')
    bad = bad.replace('CoreType=NewF12B\n', '') if missing_field else bad + '\nUnknown=1'
    cid_file.write_text(cid_block + '\n\n' + bad, encoding='utf-8')
    assert list(ChipInfoReader(cid_file).chip_entries) == ['10f200']
    assert len(caplog.records) == 1


def test_read_from_zip_resource(cid_file: Path, cid_block: str) -> None:
    archive_path = cid_file.with_suffix('.zip')
    with ZipFile(archive_path, 'w') as archive:
        archive.writestr('chips.cid', cid_block)
    with ZipFile(archive_path) as archive:
        reader = ChipInfoReader(ZipPath(archive, 'chips.cid'))
    chip = reader.get_chip('10F200')
    assert chip.chip_name == '10f200'
    assert chip.rom_size == 512
    assert chip.fuses['WDT']['Disabled'] == [(0, 0x3ffb)]
