import threading
from collections.abc import Iterator
from dataclasses import replace
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
import serial
from intelhex import IntelHex

from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.exceptions import InvalidResponseError, InvalidValueError
from picpro.FlashData import FlashData
from picpro.protocol.IConnection import IConnection
from picpro.protocol.IProgrammingInterface import IProgrammingInterface
from picpro.protocol.p014.Connection import Connection as P014Connection
from picpro.protocol.p016.Connection import Connection as P016Connection
from picpro.protocol.p018.Connection import Connection as P018Connection
from picpro.protocol.p18a.Connection import Connection as P18AConnection
from tests.MockedDevice import MockedDevice

CONNECTION_TYPES: dict[bytes, type[IConnection]] = {
    b'P014': P014Connection,
    b'P016': P016Connection,
    b'P018': P018Connection,
    b'P18A': P18AConnection,
}


@pytest.fixture(params=[b'P014', b'P016', b'P018', b'P18A'], ids=['P014', 'P016', 'P018', 'P18A'])
def protocol(request: pytest.FixtureRequest) -> bytes:
    return cast('bytes', request.param)


@pytest.fixture
def connection_type(protocol: bytes) -> type[IConnection]:
    return CONNECTION_TYPES[protocol]


def wire_command(protocol: bytes, p18a_command: int) -> int:
    """Commands after READ CONFIG shift by one in protocols with READ CALIBRATION."""
    return p18a_command + (protocol != b'P18A' and p18a_command >= 14)


@pytest.fixture
def mock_serial_device(protocol: bytes) -> Iterator[MockedDevice]:
    """Fixture to return a mocked serial device."""
    device = MockedDevice(protocol)

    worker = threading.Thread(target=device.work_thread.listen_for_commands, daemon=True)
    worker.start()
    try:
        yield device
    finally:
        device.close()
        worker.join(timeout=1)
        assert not worker.is_alive(), 'Fake device worker did not stop'



@pytest.fixture
@patch('serial.Serial', autospec=True)
def mock_connection(mock_serial: serial.Serial, mock_serial_device: MockedDevice, connection_type: type[IConnection]) -> IConnection:
    """Test communication with a mocked serial device."""
    mock_serial.return_value = mock_serial_device

    with patch('picpro.protocol.IConnection.time.sleep'):
        return connection_type('/dev/ttyUSB0')

@pytest.fixture
def mock_programming_interface(mock_connection: IConnection, chip_info_entry: ChipInfoEntry) -> IProgrammingInterface:
    return mock_connection.get_programming_interface(replace(chip_info_entry))


def test_programming_interface_icsp(mock_connection: IConnection, chip_info_entry: ChipInfoEntry) -> None:
    mock_connection.get_programming_interface(chip_info_entry, icsp_mode=True).close()

@patch('serial.Serial', side_effect=serial.SerialException('Port unavailable'))
def test_failed_connection(serial_factory: MagicMock, connection_type: type[IConnection]) -> None:
    with pytest.raises(ConnectionError):
        connection_type('/dev/ttyNever')
    assert serial_factory.call_count == 1

def test_echo(mock_connection: IConnection) -> None:
    echo_message = b'Hello world'
    result = mock_connection.echo(echo_message)
    assert result == echo_message

def test_wait_until_chip_in_socket(mock_connection: IConnection) -> None:
    mock_connection.wait_until_chip_in_socket()

def test_wait_until_chip_out_of_socket(mock_connection: IConnection) -> None:
    mock_connection.wait_until_chip_out_of_socket()

def test_programmer_version(mock_connection: IConnection) -> None:
    result = mock_connection.programmer_version()
    assert result == 3

def test_programmer_protocol(mock_connection: IConnection) -> None:
    result = mock_connection.programmer_protocol()
    assert result == mock_connection.expected_programmer_protocol


def test_get_programming_interface(mock_connection: IConnection, chip_info_entry: ChipInfoEntry) -> None:
    result = mock_connection.get_programming_interface(chip_info_entry)
    assert isinstance(result, IProgrammingInterface)


def test_set_programming_voltages_command_true(mock_programming_interface: IProgrammingInterface) -> None:
    mock_programming_interface.connection.command_start()
    mock_programming_interface.set_programming_voltages_command(on=True)
    mock_programming_interface.connection.command_end()

def test_set_programming_voltages_command_false(mock_programming_interface: IProgrammingInterface) -> None:
    mock_programming_interface.connection.command_start()
    mock_programming_interface.set_programming_voltages_command(on=False)
    mock_programming_interface.connection.command_end()


def test_cycle_programming_voltages(mock_programming_interface: IProgrammingInterface) -> None:
    mock_programming_interface.cycle_programming_voltages()

def test_program_rom(mock_programming_interface: IProgrammingInterface, flash_data: FlashData) -> None:
    mock_programming_interface.program_rom(flash_data.rom_data)

def test_program_eeprom(mock_programming_interface: IProgrammingInterface, flash_data: FlashData) -> None:
    mock_programming_interface.program_eeprom(flash_data.eeprom_data)

def test_program_id_fuses(mock_programming_interface: IProgrammingInterface, flash_data: FlashData) -> None:
    mock_programming_interface.program_id_fuses(flash_data.id_data, flash_data.fuse_data)

def test_program_calibration(mock_programming_interface: IProgrammingInterface) -> None:
    mock_programming_interface.program_calibration(calibrate=0x1234, fuse=0x5678)

def test_read_config(mock_programming_interface: IProgrammingInterface, flash_data: FlashData) -> None:
    mock_programming_interface.program_id_fuses(flash_data.id_data, flash_data.fuse_data)
    mock_programming_interface.program_calibration(calibrate=0x1234, fuse=0x31ff)
    result = mock_programming_interface.read_config()
    assert result.chip_id == 0
    assert result.id == flash_data.id_data + b'\x00' * 4
    assert result.fuses[0] == 0x31ff
    assert result.fuses[1:] == [0] * 6
    assert result.calibrate == 0x1234

def test_read_rom(mock_programming_interface: IProgrammingInterface, flash_data: FlashData) -> None:
    mock_programming_interface.program_rom(flash_data.rom_data)
    result = mock_programming_interface.read_rom()
    assert result == flash_data.rom_data

def test_read_eeprom(mock_programming_interface: IProgrammingInterface, flash_data: FlashData) -> None:
    mock_programming_interface.program_eeprom(flash_data.eeprom_data)
    result = mock_programming_interface.read_eeprom()
    assert result == flash_data.eeprom_data

def test_rom_is_not_blank(mock_programming_interface: IProgrammingInterface) -> None:
    high_byte = bytes([(mock_programming_interface.chip_info.rom_blank_word >> 8) & 0xFF])
    mock_programming_interface.program_rom(b'\x00' * 32)
    assert mock_programming_interface.rom_is_blank(high_byte) is False

def test_eeprom_is_not_blank(mock_programming_interface: IProgrammingInterface) -> None:
    mock_programming_interface.program_eeprom(b'\x00\x01')
    assert mock_programming_interface.eeprom_is_blank() is False

def test_erase_chip(mock_programming_interface: IProgrammingInterface) -> None:
    mock_programming_interface.erase_chip()

def test_rom_is_blank(mock_programming_interface: IProgrammingInterface) -> None:
    high_byte = bytes([(mock_programming_interface.chip_info.rom_blank_word >> 8) & 0xFF])
    assert mock_programming_interface.rom_is_blank(high_byte) is True

def test_eeprom_is_blank(mock_programming_interface: IProgrammingInterface) -> None:
    assert mock_programming_interface.eeprom_is_blank() is True

def test_program_debug_vector(mock_programming_interface: IProgrammingInterface) -> None:
    mock_programming_interface.program_debug_vector(0x123456)

def test_read_debug_vector(mock_programming_interface: IProgrammingInterface) -> None:
    mock_programming_interface.program_debug_vector(0x123456)
    assert mock_programming_interface.read_debug_vector() == 0x123456

@pytest.mark.parametrize('core_type', ['newf12b', 'bit14_b', 'bit16_a'])
def test_memory_round_trip(mock_connection: IConnection, chip_info_entry: ChipInfoEntry, core_type: str) -> None:
    interface = mock_connection.get_programming_interface(replace(chip_info_entry, core_type=core_type))
    chip = interface.chip_info
    blank = chip.rom_blank_word.to_bytes(2, 'big')
    high_byte = blank[:1]
    assert interface.read_rom() == blank * (chip.rom_size // 2)
    assert interface.rom_is_blank(high_byte)
    payload = b'\x00\x01' * 16
    interface.program_rom(payload)
    assert interface.read_rom() == payload + blank * ((chip.rom_size - len(payload)) // 2)
    assert not interface.rom_is_blank(high_byte)
    if chip.eeprom_size:
        assert interface.read_eeprom() == b'\xff' * chip.eeprom_size
        interface.program_eeprom(b'\x12\x34')
        assert interface.read_eeprom() == b'\x12\x34' + b'\xff' * (chip.eeprom_size - 2)
        assert not interface.eeprom_is_blank()
    interface.erase_chip()
    assert interface.rom_is_blank(high_byte)
    assert interface.read_rom() == blank * (chip.rom_size // 2)
    assert interface.read_eeprom() == b'\xff' * chip.eeprom_size
    assert interface.eeprom_is_blank()


def test_programmed_blank_data_is_blank(mock_programming_interface: IProgrammingInterface) -> None:
    interface = mock_programming_interface
    blank = interface.chip_info.rom_blank_word.to_bytes(2, 'big')
    interface.program_rom(blank * 16)
    interface.program_eeprom(b'\xff\xff')
    assert interface.rom_is_blank(blank[:1])
    assert interface.eeprom_is_blank()


def test_pic18_fuse_transaction(mock_connection: IConnection, chip_info_entry: ChipInfoEntry) -> None:
    interface = mock_connection.get_programming_interface(replace(chip_info_entry, core_type='bit16_a', fuse_blank=[0xffff] * 7))
    pic_id = b'12345678'
    fuses = [0x1234, 0x5678, 0x9abc, 0xdef0, 0x1357, 0x2468, 0xabcd]
    transaction = interface.program_id_fuses(pic_id, fuses)
    assert transaction is not None
    config = interface.read_config()
    assert config.id == pic_id
    assert config.fuses == [0xffff] * 7
    transaction.program_18fxxxx_fuse(fuses)
    config = interface.read_config()
    assert config.id == pic_id
    assert config.fuses == fuses


@pytest.mark.parametrize(('sequence', 'expected', 'socket_sequence'), [('VccVpp2', 1, 2), ('Vpp2Vcc', 3, 4), ('VccVpp1', 1, 1)])
def test_icsp_programming_variables(mock_connection: IConnection, chip_info_entry: ChipInfoEntry,
                                    mock_serial_device: MockedDevice, sequence: str, expected: int, socket_sequence: int) -> None:
    chip = replace(chip_info_entry, power_sequence=sequence)
    mock_connection.get_programming_interface(chip, icsp_mode=True)
    received = mock_serial_device.work_thread.programing_vars
    assert received is not None
    assert received.power_sequence == expected
    assert received.rom_size_words == chip.rom_size // 2
    assert received.eeprom_size == chip.eeprom_size
    # ICSP must not change subsequent socket-mode initialization.
    mock_connection.get_programming_interface(chip)
    received = mock_serial_device.work_thread.programing_vars
    assert received is not None
    assert received.power_sequence == socket_sequence


@pytest.mark.parametrize('on', [False, True])
def test_voltage_cycle_finishes_enabled(mock_programming_interface: IProgrammingInterface,
                                         mock_serial_device: MockedDevice, *, on: bool) -> None:
    interface = mock_programming_interface
    interface.connection.command_start()
    interface.set_programming_voltages_command(on=on)
    interface.connection.command_end()
    interface.cycle_programming_voltages()
    assert mock_serial_device.work_thread.is_programming_voltages_on


@pytest.mark.parametrize(('method', 'size', 'message'), [
    ('program_rom', 0, 'multiple of 32'), ('program_eeprom', 0, 'multiple of 2'),
    ('program_rom', 2049, 'too large'), ('program_rom', 31, 'multiple of 32'),
    ('program_eeprom', 130, 'too large'), ('program_eeprom', 1, 'multiple of 2'),
])
def test_reject_invalid_memory_size(mock_programming_interface: IProgrammingInterface,
                                    method: str, size: int, message: str) -> None:
    with pytest.raises(InvalidValueError, match=message):
        getattr(mock_programming_interface, method)(b'\x00' * size)
    assert mock_programming_interface.connection.echo(b'ok') == b'ok'


@pytest.mark.parametrize(('core', 'pic_id', 'fuses', 'message'), [
    ('bit14_b', b'123', [0x3fff], '4-byte ID'),
    ('bit14_b', b'1234', [], 'one fuse'),
    ('bit16_a', b'1234', [0xffff] * 7, '8-byte ID'),
    ('bit16_a', b'12345678', [0xffff], '7 fuses'),
])
def test_reject_invalid_id_fuses(mock_connection: IConnection, chip_info_entry: ChipInfoEntry,
                                 core: str, pic_id: bytes, fuses: list[int], message: str) -> None:
    interface = mock_connection.get_programming_interface(replace(chip_info_entry, core_type=core))
    with pytest.raises(InvalidValueError, match=message):
        interface.program_id_fuses(pic_id, fuses)


def test_reject_wrong_blank_high_byte(mock_programming_interface: IProgrammingInterface) -> None:
    with pytest.raises(InvalidResponseError, match='high_byte is incorrect'):
        mock_programming_interface.rom_is_blank(b'\xff')


@pytest.mark.parametrize(('method', 'args', 'command', 'original', 'failure'), [
    ('program_rom', (b'\x00' * 32,), 7, b'P', b'N'),
    ('program_eeprom', (b'\x00\x01',), 8, b'P', b'N'),
    ('program_id_fuses', (b'1234', [0x3fff]), 9, b'Y', b'N'),
    ('program_calibration', (0x1234, 0x31ff), 10, b'Y', b'C'),
    ('program_calibration', (0x1234, 0x31ff), 10, b'Y', b'F'),
    ('program_calibration', (0x1234, 0x31ff), 10, b'Y', b'!'),
    ('read_config', (), 13, b'C', b'N'),
    ('erase_chip', (), 14, b'Y', b'N'),
    ('rom_is_blank', (b'\x3f',), 15, b'Y', b'I'),
    ('eeprom_is_blank', (), 16, b'Y', b'I'),
    ('program_debug_vector', (0x123456,), 22, b'Y', b'N'),
    ('program_debug_vector', (0x123456,), 22, b'Y', b'I'),
])
def test_device_failure(mock_programming_interface: IProgrammingInterface, mock_serial_device: MockedDevice,
                        method: str, args: tuple, command: int, original: bytes, failure: bytes) -> None:
    if mock_serial_device.protocol == b'P014' and method == 'program_id_fuses':
        original = b'\x00'
    command = wire_command(mock_serial_device.protocol, command)
    mock_serial_device.work_thread.response_overrides[(command, original)] = failure
    with pytest.raises(InvalidResponseError):
        getattr(mock_programming_interface, method)(*args)
    assert not mock_serial_device.work_thread.response_overrides


def test_pic18_fuse_commit_failure(mock_connection: IConnection, chip_info_entry: ChipInfoEntry,
                                   mock_serial_device: MockedDevice) -> None:
    interface = mock_connection.get_programming_interface(replace(chip_info_entry, core_type='bit16_a', fuse_blank=[0xffff] * 7))
    fuses = [0xffff] * 7
    transaction = interface.program_id_fuses(b'12345678', fuses)
    assert transaction is not None
    mock_serial_device.work_thread.response_overrides[(wire_command(mock_serial_device.protocol, 17), b'Y')] = b'B'
    with pytest.raises(InvalidResponseError):
        transaction.program_18fxxxx_fuse(fuses)


def test_connection_timeout(mock_connection: IConnection) -> None:
    assert mock_connection.read(1, timeout=0.01) == b''


def test_small_rom_without_progress_bytes(mock_connection: IConnection, chip_info_entry: ChipInfoEntry) -> None:
    chip = replace(chip_info_entry, core_type='newf12b', rom_size=512, eeprom_size=0)
    interface = mock_connection.get_programming_interface(chip)
    assert interface.rom_is_blank(b'\x0f')
    interface.program_rom(b'\x00' * 512)
    assert interface.read_rom() == b'\x00' * 512
    assert not interface.rom_is_blank(b'\x0f')
    assert interface.read_eeprom() == b''


@pytest.mark.parametrize('address', [0, 0xffffff])
def test_debug_vector_boundaries(mock_programming_interface: IProgrammingInterface, address: int) -> None:
    mock_programming_interface.program_debug_vector(address)
    assert mock_programming_interface.read_debug_vector() == address


def test_initialization_rejected(mock_connection: IConnection, chip_info_entry: ChipInfoEntry,
                                  mock_serial_device: MockedDevice) -> None:
    mock_serial_device.work_thread.response_overrides[(3, b'I')] = b'N'
    with pytest.raises(InvalidResponseError):
        mock_connection.get_programming_interface(replace(chip_info_entry))


def test_reset_preserves_chip_memory(mock_programming_interface: IProgrammingInterface,
                                     mock_serial_device: MockedDevice) -> None:
    interface = mock_programming_interface
    interface.program_rom(b'\x00' * 32)
    with patch('picpro.protocol.IConnection.time.sleep'):
        assert interface.connection.reset()
    assert interface.connection.detected_programmer_version == 3
    assert mock_serial_device.work_thread.programing_vars is None
    assert not mock_serial_device.work_thread.is_programming_voltages_on
    new_interface = interface.connection.get_programming_interface(interface.chip_info)
    assert new_interface.read_rom()[:32] == b'\x00' * 32


def test_completed_commands_disable_voltages(mock_programming_interface: IProgrammingInterface,
                                             mock_serial_device: MockedDevice) -> None:
    interface = mock_programming_interface
    operations = [
        lambda: interface.program_rom(b'\x00' * 32),
        lambda: interface.program_eeprom(b'\x00\x01'),
        lambda: interface.program_id_fuses(b'1234', [0x31ff]),
        lambda: interface.program_calibration(0x1234, 0x31ff),
        interface.read_rom, interface.read_eeprom, interface.read_config, interface.erase_chip,
    ]
    for operation in operations:
        operation()
        assert not mock_serial_device.work_thread.is_programming_voltages_on
        assert not mock_serial_device.work_thread.in_jump_table


@pytest.mark.parametrize('response', [b'Y', b'\x00', b'\xff'])
def test_id_fuse_status_bytes(mock_programming_interface: IProgrammingInterface,
                              mock_serial_device: MockedDevice, response: bytes) -> None:
    # P014 documents 0x00 as success and 0xff as failure for 14-bit
    # ID/fuse programming. Later revisions return ASCII Y instead.
    original = b'\x00' if mock_serial_device.protocol == b'P014' else b'Y'
    mock_serial_device.work_thread.response_overrides[(9, original)] = response
    if response == b'Y' or (mock_serial_device.protocol == b'P014' and response == b'\x00'):
        assert mock_programming_interface.program_id_fuses(b'1234', [0x31ff]) is None
    else:
        with pytest.raises(InvalidResponseError):
            mock_programming_interface.program_id_fuses(b'1234', [0x31ff])
    assert not mock_serial_device.work_thread.response_overrides


def test_program_eeprom_from_word_encoded_hex(mock_programming_interface: IProgrammingInterface) -> None:
    image = IntelHex()
    image.frombytes(b'\x11\x00\x22\x00', offset=0x4200)
    data = FlashData(mock_programming_interface.chip_info, image)
    expected = b'\x11\x22' + b'\xff' * (mock_programming_interface.chip_info.eeprom_size - 2)
    assert data.eeprom_data == expected
    mock_programming_interface.program_eeprom(data.eeprom_data)
    assert mock_programming_interface.read_eeprom() == expected
