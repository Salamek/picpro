import os
from pathlib import Path
import pytest

from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.FlashData import FlashData
from picpro.HexFileReader import HexFileReader
from picpro.ChipInfoReader import ChipInfoReader


@pytest.fixture(scope="function")  # type: ignore
def chip_data_path() -> Path:
    this_dir = Path(os.path.dirname(os.path.realpath(__file__)))
    return this_dir.joinpath('test_chip_data.cid')

@pytest.fixture(scope="function")  # type: ignore
def chip_info_reader(chip_data_path: Path) -> ChipInfoReader:
    return ChipInfoReader(chip_data_path)

@pytest.fixture(scope="function")  # type: ignore
def chip_info_entry(chip_info_reader: ChipInfoReader) -> ChipInfoEntry:
    return chip_info_reader.get_chip('12F675')

@pytest.fixture(scope="function")  # type: ignore
def hex_file_path() -> Path:
    this_dir = Path(os.path.dirname(os.path.realpath(__file__)))
    return this_dir.joinpath('test.hex')

@pytest.fixture(scope="function")  # type: ignore
def hex_file_reader(hex_file_path: Path) -> HexFileReader:
    return HexFileReader(hex_file_path)

@pytest.fixture(scope="function")  # type: ignore
def flash_data(chip_info_entry: ChipInfoEntry, hex_file_reader: HexFileReader) -> FlashData:
    return FlashData(chip_info_entry, hex_file_reader)