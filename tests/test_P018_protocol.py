import serial
import threading
import pytest
import time

from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.protocol.IProgrammingInterface import IProgrammingInterface
from tests.P018MockedDevice import P018MockedDevice
from unittest.mock import patch
from picpro.protocol.p018.Connection import Connection



@pytest.fixture  # type: ignore
def mock_serial_device() -> P018MockedDevice:
    """Fixture to return a mocked serial device."""
    device = P018MockedDevice()

    # Simulate device response in a background thread
    """
    def simulate_device() -> None:
        time.sleep(0.2)
        device.mock_send(b"Hello from Mocked Device\n")

    threading.Thread(target=simulate_device, daemon=True).start()
    """

    return device

@pytest.fixture  # type: ignore
@patch("serial.Serial", autospec=True)
def mock_connection(mock_serial: serial.Serial, mock_serial_device: P018MockedDevice) -> Connection:
    """Test communication with a mocked serial device."""
    mock_serial.return_value = mock_serial_device

    return Connection("/dev/ttyUSB0")

def test_echo(mock_connection: Connection) -> None:
    echo_message = 'Hello world'.encode()
    result = mock_connection.echo(echo_message)
    print(result)
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