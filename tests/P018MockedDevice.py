
from typing import List, Optional, Union
import threading
import time

class P018MockedDeviceThread(threading.Thread):
    def __init__(self, device: 'P018MockedDevice'):
        super().__init__()
        self.device = device

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

    def run(self):
        while True:
            data = self.read()



class P018MockedDevice:
    _dtr: bool = False
    input_buffer: bytes
    output_buffer: bytes
    """Mocked serial device that simulates RS232 behavior."""

    def __init__(self) -> None:
        self.work_thread = P018MockedDeviceThread(self)
        self.work_thread.start()
        self.input_buffer = b''
        self.output_buffer = b''
        self.is_open = True

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
        if  data == b'\x01':  # Ready?
            self.output_buffer += b'Q'
        elif data == b'\x02': # echo
            self.output_buffer += data
        elif data == b'P': # Go to jump table
            self.output_buffer += b'P'
        elif data == b'\x15':  # programmer_version
            self.output_buffer += b'\x03'
        elif data == b'\x16':  # programmer_protocol
            self.output_buffer += b'P018'
        elif data == b'\x13':  # wait_until_chip_in_socket
            self.output_buffer += b'A'
            self.output_buffer += b'Y'
        elif data == b'\x14': # wait_until_chip_out_of_socket
            self.output_buffer += b'A'
            self.output_buffer += b'Y'


        self.input_buffer += data

    def read(self, length: int = 1) -> bytes:
        """Simulate reading a line from the serial port."""
        #while not self.output_buffer:  # Wait for data
        #    time.sleep(0.1)
        requested_data = self.output_buffer[:length]
        self.output_buffer = self.output_buffer[length:]
        return requested_data

    def close(self) -> None:
        """Simulate closing the serial port."""
        self.work_thread.join()
        self.is_open = False

    def mock_send(self, data: bytes) -> None:
        """Simulate the device sending data to the serial port."""
        self.output_buffer += data

    def reset_input_buffer(self) -> None:
        self.input_buffer = b''

    def _reset(self):
        self.output_buffer = b''
        self.input_buffer = b''
        # Device sends its version on device reset
        self.output_buffer += b'B3'