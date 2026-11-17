from pathlib import Path
from typing import TextIO, cast
from zipfile import Path as ZipPath
from zipfile import ZipFile

import pytest
import yaml

from picpro.ChipDataReader import ChipDataReader
from picpro.ChipInfoReader import ChipInfoReader

_DATA_DIR = Path(__file__).resolve().parents[1] / 'picpro' / 'data'
_CHIP_YAML = """\
chip_name: testchip
include: true
socket_image: dip28
erase_mode: 3
flash_chip: true
power_sequence: VccFastVpp1
program_delay: 10
program_tries: 1
over_program: 0
core_type: bit14_c
rom_size: 8192
eeprom_size: 128
cp_warn: false
cal_word: false
band_gap: false
icsp_only: false
chip_id: 0xba0
fuses_blank:
  1: 0x3fff
  0: 0x3ffe
fuses:
  BOREN:
    Enabled:
      1: 0x3fff
      0: 0x3fff
    Disabled:
      1: 0x3fbf
      0: 0x3fbf
  Clock Monitor:
    Enabled:
      1: 0x3fff
    Disabled:
      1: 0x3ffe
"""


@pytest.fixture
def chip_dir(tmp_path: Path) -> Path:
    (tmp_path / 'testchip.yml').write_text(_CHIP_YAML, encoding='utf-8')
    return tmp_path


@pytest.mark.parametrize('name', ['testchip', 'TESTCHIP', 'TestChip'])
def test_get_chip(chip_dir: Path, name: str) -> None:
    chip = ChipDataReader(chip_dir).get_chip(name)
    assert chip.to_dict() == {
        'chip_name': 'testchip', 'include': True, 'socket_image': 'dip28',
        'erase_mode': 3, 'flash_chip': True, 'power_sequence': 'VccFastVpp1',
        'program_delay': 10, 'program_tries': 1, 'over_program': 0,
        'core_type': 'bit14_c', 'rom_size': 8192, 'eeprom_size': 128,
        'cp_warn': False, 'cal_word': False, 'band_gap': False,
        'icsp_only': False, 'chip_id': 0xba0,
        'fuse_blank': [0x3ffe, 0x3fff],
        'fuses': {
            'BOREN': {
                'Enabled': [(1, 0x3fff), (0, 0x3fff)],
                'Disabled': [(1, 0x3fbf), (0, 0x3fbf)],
            },
            'Clock Monitor': {'Enabled': [(1, 0x3fff)], 'Disabled': [(1, 0x3ffe)]},
        },
    }
    assert chip.programming_variables.rom_size_words == 4096
    assert chip.pin1_location_text == 'socket pin 1'
    assert chip.encode_fuse_data({'BOREN': 'Disabled', 'Clock Monitor': 'Disabled'}) == [0x3fbe, 0x3fbe]


def test_missing_chip(chip_dir: Path) -> None:
    with pytest.raises(KeyError) as exc:
        ChipDataReader(chip_dir).get_chip('UNKNOWN')
    assert exc.value.args == ('UNKNOWN',)


def test_empty_directory(tmp_path: Path) -> None:
    reader = ChipDataReader(tmp_path)
    assert reader.chip_entries == {}
    with pytest.raises(KeyError):
        reader.get_chip('testchip')


def test_list_entries_sorted_and_ignore_other_files(tmp_path: Path) -> None:
    for name in ['beta', 'alpha']:
        (tmp_path / f'{name}.yml').write_text(_CHIP_YAML.replace('testchip', name), encoding='utf-8')
    (tmp_path / 'notes.txt').write_text('not YAML', encoding='utf-8')
    entries = ChipDataReader(tmp_path).chip_entries
    assert list(entries) == ['alpha', 'beta']
    for name, chip in entries.items():
        assert chip.chip_name == name
        assert chip == ChipDataReader(tmp_path).get_chip(name)


@pytest.mark.parametrize('socket_line', ['socket_image: null\n', ''])
def test_optional_socket(chip_dir: Path, socket_line: str) -> None:
    content = _CHIP_YAML.replace('socket_image: dip28\n', socket_line)
    (chip_dir / 'testchip.yml').write_text(content, encoding='utf-8')
    chip = ChipDataReader(chip_dir).get_chip('testchip')
    assert chip.socket_image is None
    assert chip.pin1_location_text == 'No socket'


@pytest.mark.parametrize('list_entries', [False, True])
def test_invalid_yaml(chip_dir: Path, *, list_entries: bool) -> None:
    (chip_dir / 'testchip.yml').write_text('chip_name: [unterminated', encoding='utf-8')
    reader = ChipDataReader(chip_dir)
    if list_entries:
        with pytest.raises(yaml.YAMLError):
            _ = reader.chip_entries
    else:
        with pytest.raises(yaml.YAMLError):
            reader.get_chip('testchip')


@pytest.mark.parametrize('rom_line', ['', 'rom_size: wrong\n'])
def test_invalid_required_field(chip_dir: Path, rom_line: str) -> None:
    content = _CHIP_YAML.replace('rom_size: 8192\n', rom_line)
    (chip_dir / 'testchip.yml').write_text(content, encoding='utf-8')
    with pytest.raises(TypeError, match='rom_size'):
        ChipDataReader(chip_dir).get_chip('testchip')


@pytest.mark.parametrize('list_entries', [False, True])
@pytest.mark.parametrize('invalid_yaml', [False, True])
def test_files_closed(chip_dir: Path, monkeypatch: pytest.MonkeyPatch, *, list_entries: bool, invalid_yaml: bool) -> None:
    if invalid_yaml:
        (chip_dir / 'testchip.yml').write_text('chip_name: [unterminated', encoding='utf-8')
    original_open = Path.open
    opened: list[TextIO] = []

    def track_open(path: Path, mode: str = 'r', encoding: str | None = None) -> TextIO:
        stream = cast('TextIO', original_open(path, mode, encoding=encoding))
        opened.append(stream)
        return stream

    monkeypatch.setattr(Path, 'open', track_open)
    reader = ChipDataReader(chip_dir)
    def read_chip() -> None:
        if list_entries:
            _ = reader.chip_entries
        else:
            reader.get_chip('testchip')

    try:
        if invalid_yaml:
            with pytest.raises(yaml.YAMLError):
                read_chip()
        else:
            read_chip()
        assert opened
        assert all(stream.closed for stream in opened)
    finally:
        for stream in opened:
            stream.close()


def test_packaged_yaml_matches_cid() -> None:
    yaml_reader = ChipDataReader(_DATA_DIR / 'chip-data.d')
    yaml_entries = yaml_reader.chip_entries
    cid_entries = ChipInfoReader(_DATA_DIR / 'chipdata.cid').chip_entries
    assert yaml_entries.keys() == cid_entries.keys()
    assert yaml_entries
    for name, chip in yaml_entries.items():
        expected = cid_entries[name].to_dict()
        actual = chip.to_dict()
        # YAML uses DIP aliases and null for ICSP-only devices.
        expected.pop('socket_image')
        actual.pop('socket_image')
        assert actual == expected, name
        if chip.icsp_only:
            assert chip.socket_image is None, name
            assert chip.pin1_location_text == 'No socket', name
        else:
            assert chip.pin1_location_text == cid_entries[name].pin1_location_text, name
        assert chip.programming_variables == cid_entries[name].programming_variables, name
        assert yaml_reader.get_chip(name.upper()) == chip, name


def test_missing_data_directory(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match='Chip data directory does not exist'):
        ChipDataReader(tmp_path / 'missing')


def test_read_yaml_from_zip_resources(tmp_path: Path) -> None:
    archive_path = tmp_path / 'chips.zip'
    with ZipFile(archive_path, 'w') as archive:
        archive.writestr('definitions/testchip.yml', _CHIP_YAML)
        archive.writestr('definitions/notes.txt', 'ignore this')
        archive.writestr('definitions/subdir.yml/', '')
    with ZipFile(archive_path) as archive:
        reader = ChipDataReader(ZipPath(archive, 'definitions/'))
        chip = reader.get_chip('TESTCHIP')
        assert chip.rom_size == 8192
        assert chip.fuse_blank == [0x3ffe, 0x3fff]
        assert list(reader.chip_entries) == ['testchip']
        assert reader.chip_entries['testchip'] == chip
