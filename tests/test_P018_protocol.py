import serial
import threading
import pytest
import time
from unittest.mock import patch
from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.FlashData import FlashData
from picpro.protocol.IProgrammingInterface import IProgrammingInterface
from tests.P018MockedDevice import P018MockedDevice

from picpro.protocol.p018.Connection import Connection
from picpro.protocol.p018.ProgrammingInterface import ProgrammingInterface


@pytest.fixture(scope="session")  # type: ignore
def mock_serial_device() -> P018MockedDevice:
    """Fixture to return a mocked serial device."""
    device = P018MockedDevice()

    threading.Thread(target=device.work_thread.listen_for_commands, daemon=True).start()

    return device


@pytest.fixture(scope="module")  # type: ignore
@patch("serial.Serial", autospec=True)
def mock_connection(mock_serial: serial.Serial, mock_serial_device: P018MockedDevice) -> Connection:
    """Test communication with a mocked serial device."""
    mock_serial.return_value = mock_serial_device

    return Connection("/dev/ttyUSB0")

@pytest.fixture(scope="module")  # type: ignore
def mock_programming_interface(mock_connection: Connection, chip_info_entry: ChipInfoEntry) -> IProgrammingInterface:
    return mock_connection.get_programming_interface(chip_info_entry)


def test_echo(mock_connection: Connection) -> None:
    echo_message = 'Hello world'.encode()
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
    mock_programming_interface.set_programming_voltages_command(True)
    mock_programming_interface.connection.command_end()

def test_set_programming_voltages_command_false(mock_programming_interface: ProgrammingInterface) -> None:
    mock_programming_interface.connection.command_start()
    mock_programming_interface.set_programming_voltages_command(False)
    mock_programming_interface.connection.command_end()


def test_cycle_programming_voltages(mock_programming_interface: ProgrammingInterface) -> None:
    mock_programming_interface.cycle_programming_voltages()

def test_program_rom(mock_programming_interface: ProgrammingInterface, flash_data: FlashData) -> None:
    mock_programming_interface.program_rom(flash_data.rom_data)

def test_program_eeprom(mock_programming_interface: ProgrammingInterface, flash_data: FlashData) -> None:
    mock_programming_interface.program_eeprom(flash_data.eeprom_data)

def test_program_id_fuses(mock_programming_interface: ProgrammingInterface, flash_data: FlashData) -> None:
    mock_programming_interface.program_id_fuses(flash_data.id_data, flash_data.fuse_data)

def test_close(mock_serial_device: P018MockedDevice) -> None:
    # !FIXME Hack , order of test matter and we need to close our device after last test to stop its thread...
    mock_serial_device.close()