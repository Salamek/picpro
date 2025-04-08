import struct
import time
from types import TracebackType
from typing import Optional, Type, Union
import serial
from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.exceptions import InvalidResponseError
from picpro.protocol.IProgrammingInterface import IProgrammingInterface
from picpro.protocol.p18a.ProgrammingInterface import ProgrammingInterface


class IConnection:
    detected_programmer_version: int

    def __init__(self, port: str):
        try:
            self.serial_connection = serial.Serial(
                port=port,
                baudrate=19200,
                bytesize=8,
                parity='N',
                stopbits=1,
                timeout=0.1,
                xonxoff=False,
                rtscts=False
            )
        except serial.SerialException as e:
            raise ConnectionError('Unable to open serial port "{}".'.format(port)) from e

        self.cmd_wait_until_chip_in_socket = 0
        self.cmd_wait_until_chip_out_of_socket = 0
        self.cmd_programmer_version = 0
        self.cmd_programmer_protocol = 0

        self.reset()

    def read(self, count: int = 1, timeout: Optional[Union[int, float]] = 5) -> bytes:
        # _read(count, timeout)
        # Read bytes from the port.  Stop when the requested number of
        # bytes have been received, or the timeout has passed.  In order
        # to sidestep issues with the serial library this is done by
        # polling the serial port's read() method.
        result = b''
        init_time = time.time()
        end_time = None
        if timeout is not None:
            end_time = init_time + timeout
        while (count > 0) and ((end_time is None) or (time.time() < end_time)):
            read_result = self.serial_connection.read(count)
            count = count - len(read_result)
            result = result + read_result

        return result

    def expect(self, expected: bytes, timeout: Optional[Union[int, float]] = 5, send_command_end: bool = False) -> None:
        """Raise an exception if the expected response byte is not sent by the PIC programmer before timeout."""
        response = self.read(len(expected), timeout=timeout)
        if send_command_end:
            self.command_end()
        if response != expected:
            raise InvalidResponseError('Expected "{!r}", received {!r}.'.format(expected, response))

    def command_start(self, cmd: Optional[int] = None) -> None:
        # Send command 1: if we're at the jump table already this will
        # get us out.  If we're awaiting command start, this will
        # still echo 'Q' and await another command start.

        self.serial_connection.write(b'\x01')
        self.expect(b'Q')

        # Start command, go to jump table.
        self.serial_connection.write(b'P')

        # Check for acknowledgement
        ack = self.read(1)
        result = ack == b'P'
        if not result:
            raise InvalidResponseError('No acknowledgement for command start.')

        # Send command number, if specified
        if cmd is not None:
            self.serial_connection.write(cmd.to_bytes(1, 'little'))

    def command_end(self) -> bool:
        cmd = b'\x01'
        self.serial_connection.write(cmd)
        ack = self.read(1, timeout=10)
        result = ack == b'Q'
        if not result:
            if ack != b'':
                raise InvalidResponseError('Unexpected response ("{!r}") in command end.'.format(ack))
            raise InvalidResponseError('No acknowledgement for command end.')
        return result

    def reset(self) -> bool:
        """Resets the PIC Programmer's on-board controller."""

        self.serial_connection.dtr = True
        time.sleep(.1)
        self.serial_connection.reset_input_buffer()
        # Detect whether this unit operates with DTR high, or DTR low.
        self.serial_connection.dtr = False
        time.sleep(.1)
        # Input was just flushed.  If the unit operates with DTR low,
        # then the unit is now on, and we should be seeing a 2 byte
        # response.
        response = self.read(2, timeout=.3)
        if response == b'':
            # Apparently the unit operates with DTR high, so...
            self.serial_connection.dtr = True
            time.sleep(.1)
            response = self.read(2, timeout=.3)

        if len(response) >= 1:
            result = response[0].to_bytes(1, 'little') == b'B'
        else:
            result = False

        if not result:
            raise InvalidResponseError

        if len(response) == 2:
            self.detected_programmer_version = response[1]
        return result

    def echo(self, msg: bytes = b'X') -> bytes:
        """Instructs the PIC programmer to echo back the message
        string.  Returns the PIC programmer's response."""
        cmd = b'\x02'
        self.command_start()
        result = b''

        for c in msg:
            self.serial_connection.write(cmd)
            self.serial_connection.write(c.to_bytes(1, 'little'))
            response = self.read(1)
            result = result + response
        self.command_end()
        return result

    @property
    def expected_programmer_protocol(self) -> bytes:
        raise NotImplementedError

    def close(self) -> None:
        self.serial_connection.close()

    def wait_until_chip_in_socket(self) -> None:
        """Blocks until a chip is inserted in the programming socket."""
        cmd = 18
        self.command_start(cmd)
        self.expect(b'A')

        self.expect(b'Y', timeout=None, send_command_end=True)

    def wait_until_chip_out_of_socket(self) -> None:
        """Blocks until chip is removed from programming socket."""
        cmd = 19

        self.command_start(cmd)
        self.expect(b'A')

        self.expect(b'Y', timeout=None, send_command_end=True)

    def programmer_version(self) -> bytes:
        """Returns the PIC programmer's numeric version.
        K128     = 0  (Byte)
        K149-A   = 1  (Byte)
        K149-B   = 2  (Byte)
        K150     = 3  (Byte)
        """
        cmd = 20
        self.command_start(cmd)
        response = self.read(1)
        self.command_end()
        result, = struct.unpack('B', response)
        return result

    def programmer_protocol(self) -> bytes:
        """Returns the PIC programmer's protocol version in text form."""
        cmd = 21
        self.command_start(cmd)
        # Protocol doc isn't clear on the format of command 22's output.
        # Presumably it will always be exactly 4 bytes.
        response = self.read(4)
        self.command_end()
        return response

    def get_programming_interface(self, chip_info: ChipInfoEntry, icsp_mode: bool = False) -> IProgrammingInterface:
        return ProgrammingInterface(self, chip_info, icsp_mode)

    def __enter__(self) -> 'IConnection':
        return self

    def __exit__(self, exc_type: Optional[Type[BaseException]],
                 exc_value: Optional[BaseException],
                 traceback: Optional[TracebackType]) -> None:
        self.close()
