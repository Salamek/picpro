from collections import deque
from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
import serial

from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.exceptions import InvalidResponseError
from picpro.protocol.enums import ResponseEnum
from picpro.protocol.IConnection import IConnection


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        now = self.now
        self.now += 0.01
        return now

    def sleep(self, duration: float) -> None:
        self.sleeps.append(duration)
        self.now += duration


class ScriptedSerial:
    """A serial transport with scripted reads, reset polarity, and no real waits."""

    def __init__(self) -> None:
        self.responses: deque[bytes] = deque()
        self.startup = {False: b'B\x03'}
        self.events: list[tuple[str, bool | None]] = []
        self.writes: list[bytes] = []
        self.read_sizes: list[int] = []
        self.closed = False
        self.close_count = 0
        self.read_error: serial.SerialException | None = None
        self._dtr = False

    @property
    def dtr(self) -> bool:
        return self._dtr

    @dtr.setter
    def dtr(self, value: bool) -> None:
        self._dtr = value
        self.events.append(('dtr', value))
        if value in self.startup:
            self.responses.append(self.startup[value])

    def reset_input_buffer(self) -> None:
        self.events.append(('flush', None))
        self.responses.clear()

    def read(self, size: int) -> bytes:
        if self.read_error is not None:
            raise self.read_error
        self.read_sizes.append(size)
        response = self.responses.popleft() if self.responses else b''
        if len(response) > size:
            self.responses.appendleft(response[size:])
        return response[:size]

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    def close(self) -> None:
        self.closed = True
        self.close_count += 1


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    clock = Clock()
    monkeypatch.setattr('picpro.protocol.IConnection.time', clock)
    return clock


@pytest.fixture
def serial_device() -> ScriptedSerial:
    return ScriptedSerial()


@pytest.fixture
def serial_factory(monkeypatch: pytest.MonkeyPatch, serial_device: ScriptedSerial) -> MagicMock:
    factory = MagicMock(return_value=serial_device)
    monkeypatch.setattr(serial, 'Serial', factory)
    return factory


@pytest.fixture
def connection(serial_factory: MagicMock, serial_device: ScriptedSerial, clock: Clock) -> Iterator[IConnection]:
    connection = IConnection('/dev/fake')
    serial_factory.assert_called_once()
    serial_device.events.clear()
    serial_device.read_sizes.clear()
    clock.now = 0
    clock.sleeps.clear()
    try:
        yield connection
    finally:
        if not serial_device.closed:
            connection.close()


def test_serial_configuration(connection: IConnection, serial_factory: MagicMock) -> None:
    serial_factory.assert_called_once_with(
        port='/dev/fake', baudrate=19200, bytesize=8, parity='N', stopbits=1,
        timeout=0.1, xonxoff=False, rtscts=False,
    )
    assert connection.detected_programmer_version == 3


def test_port_open_failure(serial_factory: MagicMock) -> None:
    error = serial.SerialException('Port busy')
    serial_factory.side_effect = error
    with pytest.raises(ConnectionError, match='Unable to open serial port') as exc:
        IConnection('/dev/missing')
    assert exc.value.__cause__ is error


@pytest.mark.parametrize('high_polarity', [False, True])
@pytest.mark.parametrize('version', [0, 1, 2, 3])
def test_reset_detects_polarity_and_version(connection: IConnection, serial_device: ScriptedSerial, clock: Clock,
                                           version: int, *, high_polarity: bool) -> None:
    serial_device.startup = {high_polarity: b'B' + bytes([version])}
    assert connection.reset() is True
    assert connection.detected_programmer_version == version
    expected = [('dtr', True), ('flush', None), ('dtr', False)]
    if high_polarity:
        expected.append(('dtr', True))
    assert serial_device.events == expected
    assert clock.sleeps == [0.1] * (3 if high_polarity else 2)


@pytest.mark.parametrize('response', [b'', b'B', b'C\x03', b'?\x03'])
@pytest.mark.parametrize('high_polarity', [False, True])
def test_reset_rejects_missing_or_bad_header(connection: IConnection, serial_device: ScriptedSerial,
                                            response: bytes, *, high_polarity: bool) -> None:
    serial_device.startup = {high_polarity: response}
    with pytest.raises(InvalidResponseError):
        connection.reset()


@pytest.mark.usefixtures('serial_factory', 'clock')
@pytest.mark.parametrize('response', [b'', b'B', b'?\x03'])
def test_failed_initial_reset_closes_port(serial_device: ScriptedSerial, response: bytes) -> None:
    serial_device.startup = {False: response}
    with pytest.raises(InvalidResponseError):
        IConnection('/dev/fake')
    assert serial_device.closed
    assert serial_device.close_count == 1


@pytest.mark.usefixtures('serial_factory', 'clock')
def test_transport_failure_during_initial_reset_closes_port(serial_device: ScriptedSerial) -> None:
    error = serial.SerialException('Device disconnected')
    serial_device.read_error = error
    with pytest.raises(serial.SerialException, match='Device disconnected') as exc:
        IConnection('/dev/fake')
    assert exc.value is error
    assert serial_device.closed


@pytest.mark.parametrize('timeout', [None, 1.0])
def test_read_assembles_fragments(connection: IConnection, serial_device: ScriptedSerial, timeout: float | None) -> None:
    serial_device.responses.extend([b'a', b'', b'bc'])
    assert connection.read(3, timeout=timeout) == b'abc'
    assert serial_device.read_sizes == [3, 2, 2]


def test_read_leaves_extra_bytes_for_next_read(connection: IConnection, serial_device: ScriptedSerial) -> None:
    serial_device.responses.append(b'abcd')
    assert connection.read(2) == b'ab'
    assert connection.read(2) == b'cd'


@pytest.mark.parametrize('count', [0, 3])
def test_zero_timeout_does_not_read(connection: IConnection, serial_device: ScriptedSerial, count: int) -> None:
    assert connection.read(count, timeout=0) == b''
    assert serial_device.read_sizes == []


def test_empty_read_does_not_touch_serial(connection: IConnection, serial_device: ScriptedSerial) -> None:
    assert connection.read(0, timeout=None) == b''
    assert serial_device.read_sizes == []


def test_timeout_returns_partial_data(connection: IConnection, serial_device: ScriptedSerial) -> None:
    serial_device.responses.append(b'a')
    assert connection.read(3, timeout=0.025) == b'a'
    assert serial_device.read_sizes == [3, 2]


def test_timeout_without_data(connection: IConnection) -> None:
    assert connection.read(2, timeout=0.025) == b''


@pytest.mark.parametrize('end_command', [False, True])
def test_expect_accepts_response(connection: IConnection, serial_device: ScriptedSerial, *, end_command: bool) -> None:
    serial_device.responses.extend([b'Y', b'Q'])
    connection.expect(ResponseEnum.YES, send_command_end=end_command)
    assert serial_device.writes == ([b'\x01'] if end_command else [])


@pytest.mark.parametrize('response', [b'N', b'?', b''])
def test_expect_rejects_other_responses(connection: IConnection, serial_device: ScriptedSerial, response: bytes) -> None:
    serial_device.responses.append(response)
    with pytest.raises(InvalidResponseError, match='Expected'):
        connection.expect(ResponseEnum.YES, timeout=0.025)


def test_expect_ends_command_before_reporting_failure(connection: IConnection, serial_device: ScriptedSerial) -> None:
    serial_device.responses.extend([b'N', b'Q'])
    with pytest.raises(InvalidResponseError, match='Expected'):
        connection.expect(ResponseEnum.YES, send_command_end=True)
    assert serial_device.writes == [b'\x01']


@pytest.mark.parametrize('command', [None, 0, 7, 255])
def test_command_start_framing(connection: IConnection, serial_device: ScriptedSerial, command: int | None) -> None:
    serial_device.responses.extend([b'Q', b'P'])
    connection.command_start(command)
    expected = [b'\x01', b'P']
    if command is not None:
        expected.append(bytes([command]))
    assert serial_device.writes == expected


@pytest.mark.parametrize('response', [b'N', b'?', b''])
def test_command_start_requires_idle_ack(connection: IConnection, serial_device: ScriptedSerial, response: bytes) -> None:
    serial_device.responses.append(response)
    with pytest.raises(InvalidResponseError):
        connection.command_start(7)
    assert serial_device.writes == [b'\x01']


@pytest.mark.parametrize('response', [b'N', b'?', b''])
def test_command_start_requires_jump_table_ack(connection: IConnection, serial_device: ScriptedSerial, response: bytes) -> None:
    serial_device.responses.extend([b'Q', response])
    with pytest.raises(InvalidResponseError, match='No acknowledgement for command start'):
        connection.command_start(7)
    assert serial_device.writes == [b'\x01', b'P']


def test_command_end_framing(connection: IConnection, serial_device: ScriptedSerial) -> None:
    serial_device.responses.append(b'Q')
    assert connection.command_end() is True
    assert serial_device.writes == [b'\x01']


@pytest.mark.parametrize('response', [b'N', b'?', b''])
def test_command_end_rejects_bad_ack(connection: IConnection, serial_device: ScriptedSerial, response: bytes) -> None:
    serial_device.responses.append(response)
    message = 'Unexpected response' if response else 'No acknowledgement for command end'
    with pytest.raises(InvalidResponseError, match=message):
        connection.command_end()


@pytest.mark.parametrize('message', [b'', b'abc', b'\x00P\x01\xff'])
def test_echo_frames_each_byte(connection: IConnection, serial_device: ScriptedSerial, message: bytes) -> None:
    serial_device.responses.extend([b'Q', b'P', *[bytes([value]) for value in message], b'Q'])
    assert connection.echo(message) == message
    expected = [b'\x01', b'P']
    for value in message:
        expected.extend([b'\x02', bytes([value])])
    expected.append(b'\x01')
    assert serial_device.writes == expected


def test_default_echo(connection: IConnection, serial_device: ScriptedSerial) -> None:
    serial_device.responses.extend([b'Q', b'P', b'X', b'Q'])
    assert connection.echo() == b'X'


def test_close(connection: IConnection, serial_device: ScriptedSerial) -> None:
    connection.close()
    assert serial_device.closed
    assert serial_device.close_count == 1


def test_context_manager_closes_connection(connection: IConnection, serial_device: ScriptedSerial) -> None:
    with connection as active:
        assert active is connection
        assert not serial_device.closed
    assert serial_device.closed


def test_context_manager_preserves_exception(connection: IConnection, serial_device: ScriptedSerial) -> None:
    error = RuntimeError('Operation failed')
    with pytest.raises(RuntimeError, match='Operation failed') as exc, connection:
        raise error
    assert exc.value is error
    assert serial_device.closed


@pytest.mark.parametrize('method', ['wait_until_chip_in_socket', 'wait_until_chip_out_of_socket', 'programmer_version', 'programmer_protocol'])
def test_revision_specific_operations_require_implementation(connection: IConnection, method: str) -> None:
    with pytest.raises(NotImplementedError):
        getattr(connection, method)()


def test_protocol_identifier_requires_implementation(connection: IConnection) -> None:
    with pytest.raises(NotImplementedError):
        _ = connection.expected_programmer_protocol


def test_programming_interface_requires_implementation(connection: IConnection, chip_info_entry: ChipInfoEntry) -> None:
    with pytest.raises(NotImplementedError):
        connection.get_programming_interface(chip_info_entry)
