
import serial
import threading
import time

class P018MockedDevice:
    """Mocked serial device that simulates RS232 behavior."""

    def __init__(self):
        self.input_buffer = []
        self.output_buffer = []
        self.is_open = True

    def write(self, data):
        """Simulate writing data to the serial port."""
        self.input_buffer.append(data)

    def readline(self):
        """Simulate reading a line from the serial port."""
        while not self.output_buffer:  # Wait for data
            time.sleep(0.1)
        return self.output_buffer.pop(0)

    def close(self):
        """Simulate closing the serial port."""
        self.is_open = False

    def mock_send(self, data):
        """Simulate the device sending data to the serial port."""
        self.output_buffer.append(data)

    def mock_clear(self):
        """Reset the mock device buffers."""
        self.input_buffer.clear()
        self.output_buffer.clear()