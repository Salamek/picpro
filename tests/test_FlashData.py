import os
import pytest
from pathlib import Path

from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.FlashData import FlashData
from picpro.HexFileReader import HexFileReader




def test_be_constructed_with(chip_info_entry: ChipInfoEntry, hex_file_reader: HexFileReader) -> None:
    FlashData(chip_info_entry, hex_file_reader)


def test_rom_data(flash_data: FlashData) -> None:
    expected = bytes.fromhex('280f3fff3fff3fff00a0080300a11283180c2877082100830ea00e2000090064168330080085019f308c00811283100510851105160516853007009923ff1683009012833020008401800a841f84282430100090207c1683140c1283170b141001b0178b301402301c0328321285138b0063000000641985283701b0207c178b19852837301402301c03284001b101b21005108511051832140518b214851932150501b0300102301c032852120501b0300502301c03285816050ab2300806321d03284801b01d85286a301402301c03286328370ab1300a06311d03284701b01d85286f301402301c03287028370064100c0ab0207c280a30af008e303c008f00083fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff3fff')
    assert flash_data.rom_data == expected


def test_eeprom_data(flash_data: FlashData) -> None:
    expected = bytes.fromhex('ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff')
    assert flash_data.eeprom_data == expected


def test_id_data(flash_data: FlashData) -> None:
    expected = bytes.fromhex('0000070f')
    assert flash_data.id_data == expected


def test_fuse_data(flash_data: FlashData) -> None:
    expected = [16204]
    assert flash_data.fuse_data == expected