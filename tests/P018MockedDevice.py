
from typing import Optional, Union
import time


class P018MockedDeviceThread:
    in_jump_table: bool
    def __init__(self, device: 'P018MockedDevice'):
        self.device = device
        self.in_jump_table = False

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
            read_result = self.device.input_buffer[:count]
            self.device.input_buffer =  self.device.input_buffer[count:]
            count = count - len(read_result)
            result = result + read_result

        return result

    def write(self, data: bytes) -> None:
        self.device.mock_send(data)

    def listen_for_commands(self) -> None:
        while self.device.is_open:
            data = self.read()
            if self.in_jump_table:
                # In jump table
                if data == b'\x01':
                    # Exit jump table
                    self.in_jump_table = False
                    self.write(b'Q')
                elif data == b'\x02':
                    # Echo command
                    self.write(self.read())
                elif data == b'\x03':
                    # Set programming vars
                    settings = self.read(11)
                    if settings == b'\x04\x00\x00\x80\x06\x03P\x04\x02\x01\x00':
                        self.write(b'I')
                    else:
                        self.write(b'X')
                elif data == b'\x04':
                    self.write(b'V')
                elif data == b'\x05':
                    self.write(b'v')
                elif data == b'\x06':
                    self.write(b'V')
                elif data == b'\x13' or data == b'\x14':
                    self.write(b'AY')
                elif data == b'\x15':
                    # programmer_version
                    self.write(b'\x03')
                elif data == b'\x16':
                    # get protocol
                    self.write(b'P018')
                else:
                    self.write(b'F')
            else:
                # Outside of jump table, command start waiting
                if data == b'\x01':
                    # Exist jump table
                    self.in_jump_table = False
                    self.write(b'Q')
                elif data == b'P':
                    # Enter jump table
                    self.in_jump_table = True
                    self.write(b'P')
                else:
                    self.write(b'O')


class P018MockedDevice:
    _dtr: bool = False
    input_buffer: bytes
    output_buffer: bytes
    """Mocked serial device that simulates RS232 behavior."""

    def __init__(self) -> None:
        self.input_buffer = b''
        self.output_buffer = b''
        self.is_open = True
        self.work_thread = P018MockedDeviceThread(self)

    @property
    def dtr(self) -> bool:
        return self._dtr

    @dtr.setter
    def dtr(self, dtr: bool) -> None:
        # DTR means device reset
        if dtr:
            self._reset()
        self._dtr = dtr

    def write(self, data: bytes) -> None:
        """Simulate writing data to the serial port."""
        self.input_buffer += data

    def read(self, length: int = 1) -> bytes:
        """Simulate reading a line from the serial port."""
        requested_data = self.output_buffer[:length]
        self.output_buffer = self.output_buffer[length:]
        return requested_data

    def close(self) -> None:
        """Simulate closing the serial port."""
        self.is_open = False

    def mock_send(self, data: bytes) -> None:
        """Simulate the device sending data to the serial port."""
        self.output_buffer += data

    def reset_input_buffer(self) -> None:
        self.input_buffer = b''

    def _reset(self) -> None:
        self.output_buffer = b''
        self.input_buffer = b''
        # Device sends its version on device reset
        self.output_buffer += b'B3'