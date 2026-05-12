import threading
from unittest.mock import patch

import pytest
import serial

from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.FlashData import FlashData
from picpro.protocol.IProgrammingInterface import IProgrammingInterface
from picpro.protocol.p18a.Connection import Connection
from picpro.protocol.p18a.ProgrammingInterface import ProgrammingInterface
from tests.P018aMockedDevice import P018aMockedDevice


@pytest.fixture(scope='session')
def mock_serial_device() -> P018aMockedDevice:
    """Fixture to return a mocked serial device."""
    device = P018aMockedDevice()

    threading.Thread(target=device.work_thread.listen_for_commands, daemon=True).start()

    return device


@pytest.fixture(scope='module')
@patch('serial.Serial', autospec=True)
def mock_connection(mock_serial: serial.Serial, mock_serial_device: P018aMockedDevice) -> Connection:
    """Test communication with a mocked serial device."""
    mock_serial.return_value = mock_serial_device

    return Connection('/dev/ttyUSB0')

@pytest.fixture(scope='module')
def mock_programming_interface(mock_connection: Connection, chip_info_entry: ChipInfoEntry) -> IProgrammingInterface:
    return mock_connection.get_programming_interface(chip_info_entry)


def test_programming_interface_icsp(mock_connection: Connection, chip_info_entry: ChipInfoEntry) -> None:
    mock_connection.get_programming_interface(chip_info_entry, icsp_mode=True).close()

def test_failed_connection() -> None:
    with pytest.raises(ConnectionError):
        Connection('/dev/ttyNever')

def test_echo(mock_connection: Connection) -> None:
    echo_message = b'Hello world'
    result = mock_connection.echo(echo_message)
    assert result == echo_message

def test_wait_until_chip_in_socket(mock_connection: Connection) -> None:
    mock_connection.wait_until_chip_in_socket()

def test_wait_until_chip_out_of_socket(mock_connection: Connection) -> None:
    mock_connection.wait_until_chip_out_of_socket()

def test_programmer_version(mock_connection: Connection) -> None:
    result = mock_connection.programmer_version()
    assert result == 3

def test_programmer_protocol(mock_connection: Connection) -> None:
    result = mock_connection.programmer_protocol()
    assert result == mock_connection.expected_programmer_protocol


def test_get_programming_interface(mock_connection: Connection, chip_info_entry: ChipInfoEntry) -> None:
    result = mock_connection.get_programming_interface(chip_info_entry)
    assert isinstance(result, IProgrammingInterface)


def test_set_programming_voltages_command_true(mock_programming_interface: ProgrammingInterface) -> None:
    mock_programming_interface.connection.command_start()
    mock_programming_interface.set_programming_voltages_command(on=True)
    mock_programming_interface.connection.command_end()

def test_set_programming_voltages_command_false(mock_programming_interface: ProgrammingInterface) -> None:
    mock_programming_interface.connection.command_start()
    mock_programming_interface.set_programming_voltages_command(on=False)
    mock_programming_interface.connection.command_end()


def test_cycle_programming_voltages(mock_programming_interface: ProgrammingInterface) -> None:
    mock_programming_interface.cycle_programming_voltages()

def test_program_rom(mock_programming_interface: ProgrammingInterface, flash_data: FlashData) -> None:
    mock_programming_interface.program_rom(flash_data.rom_data)

def test_program_eeprom(mock_programming_interface: ProgrammingInterface, flash_data: FlashData) -> None:
    mock_programming_interface.program_eeprom(flash_data.eeprom_data)

def test_program_id_fuses(mock_programming_interface: ProgrammingInterface, flash_data: FlashData) -> None:
    mock_programming_interface.program_id_fuses(flash_data.id_data, flash_data.fuse_data)

def test_program_calibration(mock_programming_interface: ProgrammingInterface) -> None:
    mock_programming_interface.program_calibration(calibrate=0x1234, fuse=0x5678)

def test_read_config(mock_programming_interface: ProgrammingInterface, flash_data: FlashData) -> None:
    result = mock_programming_interface.read_config()
    assert result.chip_id == 0
    assert result.id == flash_data.id_data + b'\x00' * 4
    assert result.fuses[0] == flash_data.fuse_data[0]
    assert result.fuses[1:] == [0] * 6
    assert result.calibrate == 0x1234

def test_read_rom(mock_programming_interface: ProgrammingInterface, flash_data: FlashData) -> None:
    result = mock_programming_interface.read_rom()
    assert result == flash_data.rom_data

def test_read_eeprom(mock_programming_interface: ProgrammingInterface, flash_data: FlashData) -> None:
    result = mock_programming_interface.read_eeprom()
    assert result == flash_data.eeprom_data

def test_rom_is_not_blank(mock_programming_interface: ProgrammingInterface) -> None:
    high_byte = bytes([(mock_programming_interface.chip_info.rom_blank_word >> 8) & 0xFF])
    assert mock_programming_interface.rom_is_blank(high_byte) is False

def test_eeprom_is_not_blank(mock_programming_interface: ProgrammingInterface) -> None:
    assert mock_programming_interface.eeprom_is_blank() is False

def test_erase_chip(mock_programming_interface: ProgrammingInterface) -> None:
    mock_programming_interface.erase_chip()

def test_rom_is_blank(mock_programming_interface: ProgrammingInterface) -> None:
    high_byte = bytes([(mock_programming_interface.chip_info.rom_blank_word >> 8) & 0xFF])
    assert mock_programming_interface.rom_is_blank(high_byte) is True

def test_eeprom_is_blank(mock_programming_interface: ProgrammingInterface) -> None:
    assert mock_programming_interface.eeprom_is_blank() is True

def test_program_debug_vector(mock_programming_interface: ProgrammingInterface) -> None:
    mock_programming_interface.program_debug_vector(0x123456)

def test_read_debug_vector(mock_programming_interface: ProgrammingInterface) -> None:
    assert mock_programming_interface.read_debug_vector() == 0x123456

def test_close(mock_serial_device: P018aMockedDevice) -> None:
    # !FIXME Hack , order of test matter and we need to close our device after last test to stop its thread...
    mock_serial_device.close()
