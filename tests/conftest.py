import os
from pathlib import Path
import pytest
import serial
import threading
from intelhex import IntelHex
from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.FlashData import FlashData
from picpro.ChipInfoReader import ChipInfoReader
from tests.P018MockedDevice import P018MockedDevice


@pytest.fixture(scope="module")  # type: ignore
def chip_data_path() -> Path:
    this_dir = Path(os.path.dirname(os.path.realpath(__file__)))
    return this_dir.joinpath('test_chip_data.cid')

@pytest.fixture(scope="module")  # type: ignore
def chip_info_reader(chip_data_path: Path) -> ChipInfoReader:
    return ChipInfoReader(chip_data_path)

@pytest.fixture(scope="module")  # type: ignore
def chip_info_entry(chip_info_reader: ChipInfoReader) -> ChipInfoEntry:
    return chip_info_reader.get_chip('12F675')

@pytest.fixture(scope="module")  # type: ignore
def hex_file_path() -> Path:
    this_dir = Path(os.path.dirname(os.path.realpath(__file__)))
    return this_dir.joinpath('test.hex')

@pytest.fixture(scope="module")  # type: ignore
def hex_file(hex_file_path: Path) -> IntelHex:
    return IntelHex(str(hex_file_path))

@pytest.fixture(scope="module")  # type: ignore
def flash_data(chip_info_entry: ChipInfoEntry, hex_file: IntelHex) -> FlashData:
    return FlashData(chip_info_entry, hex_file)

