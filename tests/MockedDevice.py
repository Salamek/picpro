import struct
import threading

from picpro.ProgrammingVariables import ProgrammingVariables
from picpro.protocol.ChipConfig import ChipConfig


class MockedDeviceThread:
    in_jump_table: bool
    is_programming_voltages_on: bool
    programing_vars: ProgrammingVariables | None
    chip_config: ChipConfig | None

    def __init__(self, device: 'MockedDevice') -> None:
        self.device = device
        self.is_programming_voltages_on = False
        self.in_jump_table = False
        self.programing_vars = None
        self.chip_config = None
        self.rom_data: bytes | None = None
        self.eeprom_data: bytes | None = None
        self.debug_vector: int = 0
        self.pending_fuses: list[int] | None = None
        self.current_command: int | None = None
        # One-shot wire response overrides for exercising host error handling.
        self.response_overrides: dict[tuple[int, bytes], bytes] = {}

    def read(self, count: int = 1, timeout: float | None = 5) -> bytes:
        return self.device.receive(count, timeout)

    def write(self, data: bytes) -> None:
        if self.current_command is not None:
            data = self.response_overrides.pop((self.current_command, data), data)
        self.device.mock_send(data)

    def _program_rom(self) -> None:
        # program_rom
        if not self.programing_vars or not self.is_programming_voltages_on:
            # programing_vars and is_programming_voltages_on has to be set for successful program
            self.write(b'N')
            return
        # As other two bytes comes size of send data in words
        size = self.read(2)
        send_rom_size_words, = struct.unpack('>H', size)
        send_rom_size = send_rom_size_words * 2
        if send_rom_size_words > self.programing_vars.rom_size_words or not send_rom_size_words:
            # Error send data is bigger or empty
            self.write(b'N')
            return

        self.write(b'Y')
        # Now it starts sending the rom data in 32byte packets
        number_of_packets = int(send_rom_size / 32)
        received_rom_data = b''
        for _i in range(number_of_packets):
            received_rom_data += self.read(32)
            self.write(b'Y')

        if len(received_rom_data) == send_rom_size:
            self.rom_data = received_rom_data
            self.write(b'P')
        else:
            self.write(b'N')

    def _program_eeprom(self) -> None:
        # program_eeprom
        if not self.programing_vars or not self.is_programming_voltages_on:
            # programing_vars and is_programming_voltages_on has to be set for successful program
            self.write(b'N')
            return

        size = self.read(2)
        send_eeprom_size, = struct.unpack('>H', size)
        if send_eeprom_size > self.programing_vars.eeprom_size or not send_eeprom_size:
            # Error send data is bigger or empty
            self.write(b'N')
            return
        self.write(b'Y')

        # Now read Eeprom in 2? bytes wtf? why? (due to minimal eeprom size to be 2 bytes in PIC? huh?
        eeprom_packets = int(send_eeprom_size / 2)
        received_eeprom_data = b''
        for _i in range(eeprom_packets):
            received_eeprom_data += self.read(2)
            self.write(b'Y')

        # We need to eat two bytes send here by protocol, comment from protocol:
        # We must send an extra two bytes, which will have no effect.
        # Why?  I'm not sure.  See protocol doc, and read it backwards.
        # I'm sending zeros because if we did wind up back at the
        # command jump table, then the zeros will have no effect.
        self.read(2)

        if len(received_eeprom_data) == send_eeprom_size:
            self.eeprom_data = received_eeprom_data
            self.write(b'P')
        else:
            self.write(b'N')

    def _program_id_fuzes(self) -> None:
        if not self.programing_vars or not self.is_programming_voltages_on:
            self.write(b'N')
            return

        fuse_settings = self.read(24)

        if fuse_settings[:2] != b'00':
            self.write(b'N')
            return

        is_16bit = self.programing_vars.core_type in (1, 2, 13)
        if is_16bit:
            pic_id = fuse_settings[2:10]
            self.pending_fuses = list(struct.unpack('<HHHHHHH', fuse_settings[10:24]))
            fuses = self.chip_config.fuses if self.chip_config else [0xffff] * 7
        else:
            if fuse_settings[6:10] != b'FFFF' or fuse_settings[12:24] != b'\xff\xff' * 6:
                self.write(b'N')
                return
            pic_id = fuse_settings[2:6] + b'\x00' * 4
            fuses = [struct.unpack('<H', fuse_settings[10:12])[0]] + [0] * 6

        calibration = self.chip_config.calibrate if self.chip_config else 0xffff
        self.chip_config = ChipConfig(chip_id=0, id=pic_id, fuses=fuses, calibrate=calibration)
        self.write(b'\x00' if self.device.protocol == b'P014' and not is_16bit else b'Y')

    def _read_config(self) -> None:
        if not self.programing_vars or not self.is_programming_voltages_on:
            self.write(b'N')
            return
        self.write(b'C')
        config = self.chip_config or ChipConfig(chip_id=0, id=b'\xff' * 8, fuses=[0xffff] * 7, calibrate=0xffff)
        self.write(config.to_bytes())

    def _program_calibration(self) -> None:
        if not self.programing_vars or not self.is_programming_voltages_on:
            self.write(b'N')
            return
        data = self.read(4)
        calibrate = struct.unpack('>H', data[0:2])[0]
        if self.chip_config is None:
            self.chip_config = ChipConfig(chip_id=0, id=b'\x00' * 8, fuses=[0] * 7, calibrate=calibrate)
        else:
            self.chip_config.calibrate = calibrate
        self.chip_config.fuses[0] = struct.unpack('>H', data[2:4])[0]
        self.write(b'Y')

    def _read_rom(self) -> None:
        if not self.programing_vars:
            return
        rom_bytes = self.programing_vars.rom_size_words * 2
        data = self.rom_data or b''
        self.write(data + self.blank_rom_word * ((rom_bytes - len(data)) // 2))

    def _read_eeprom(self) -> None:
        if not self.programing_vars:
            return
        self.write((self.eeprom_data or b'').ljust(self.programing_vars.eeprom_size, b'\xff'))

    def _erase_chip(self) -> None:
        if not self.programing_vars or not self.is_programming_voltages_on:
            self.write(b'N')
            return
        self.rom_data = None
        self.eeprom_data = None
        self.chip_config = None
        self.pending_fuses = None
        self.write(b'Y')

    def _rom_is_blank(self) -> None:
        high_byte = self.read(1)
        if high_byte != self.blank_rom_word[:1]:
            self.write(b'B')
            return
        assert self.programing_vars is not None
        self.write(b'\xff' * ((self.programing_vars.rom_size_words - 1) // 256))
        data = self.rom_data or b''
        self.write(b'Y' if data == self.blank_rom_word * (len(data) // 2) else b'N')

    def _eeprom_is_blank(self) -> None:
        data = self.eeprom_data or b''
        self.write(b'Y' if data == b'\xff' * len(data) else b'N')

    def _program_18fxxxx_fuse(self) -> None:
        if not self.programing_vars or not self.is_programming_voltages_on:
            self.write(b'N')
            return
        data = self.read(24)
        if self.programing_vars.core_type not in (1, 2, 13) or self.pending_fuses is None:
            self.write(b'B')
            return
        fuses = list(struct.unpack('<HHHHHHH', data[10:24]))
        if self.chip_config is None:
            self.chip_config = ChipConfig(chip_id=0, id=b'\x00' * 8, fuses=fuses, calibrate=0)
        else:
            self.chip_config.fuses = fuses
        self.pending_fuses = None
        self.write(b'Y')

    def _program_debug_vector(self) -> None:
        address_bytes = self.read(3)
        self.debug_vector = struct.unpack('>I', b'\x00' + address_bytes)[0]
        self.write(b'Y')

    def _read_debug_vector(self) -> None:
        self.write(b'\xef' + self.debug_vector.to_bytes(3, 'big'))

    @property
    def blank_rom_word(self) -> bytes:
        assert self.programing_vars is not None
        core = self.programing_vars.core_type
        bits = 16 if core in (1, 2, 13) else 12 if core in (4, 11) else 14
        return ((1 << bits) - 1).to_bytes(2, 'big')

    def listen_for_commands(self) -> None:  # noqa: PLR0912
        while self.device.is_open:
            data = self.read()
            if not data:
                continue
            self.current_command = data[0] if self.in_jump_table else None
            if self.in_jump_table and self.device.protocol != b'P18A':
                # P014/P016/P018 retain READ CALIBRATION at 14. P18A
                # removed it, shifting commands 15..24 down by one.
                if data == b'\x0e':
                    calibration = self.chip_config.calibrate if self.chip_config else 0xffff
                    self.write(calibration.to_bytes(2, 'big'))
                    continue
                if 15 <= data[0] <= 24:
                    data = bytes([data[0] - 1])
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
                    try:
                        self.programing_vars = ProgrammingVariables.from_bytes(settings)
                        self.write(b'I')
                    except ValueError:
                        self.write(b'N')
                elif data == b'\x04':
                    self.is_programming_voltages_on = True
                    self.write(b'V')
                elif data == b'\x05':
                    self.is_programming_voltages_on = False
                    self.write(b'v')
                elif data == b'\x06':
                    self.is_programming_voltages_on = True
                    self.write(b'V')
                elif data == b'\x07':
                    self._program_rom()
                elif data == b'\x08':
                    self._program_eeprom()
                elif data == b'\x09':
                    self._program_id_fuzes()
                elif data == b'\x0a':
                    self._program_calibration()
                elif data == b'\x0b':
                    self._read_rom()
                elif data == b'\x0c':
                    self._read_eeprom()
                elif data == b'\x0d':
                    self._read_config()
                elif data == b'\x0e':
                    self._erase_chip()
                elif data == b'\x0f':
                    self._rom_is_blank()
                elif data == b'\x10':
                    self._eeprom_is_blank()
                elif data == b'\x11':
                    self._program_18fxxxx_fuse()
                elif data in [b'\x12', b'\x13']:
                    # wait_until_chip_in_socket/ wait_until_chip_out_of_socket
                    self.write(b'A')
                    self.write(b'Y')
                    self.in_jump_table = False
                elif data == b'\x14':
                    # programmer_version
                    self.write(b'\x03')
                elif data == b'\x15':
                    # get protocol
                    self.write(self.device.protocol)
                elif data == b'\x16':
                    self._program_debug_vector()
                elif data == b'\x17':
                    self._read_debug_vector()
                else:
                    self.write(b'F')
            # Outside of jump table, command start waiting
            elif data == b'\x01':
                # Exist jump table
                self.in_jump_table = False
                self.write(b'Q')
            elif data == b'P':
                # Enter jump table
                self.in_jump_table = True
                self.write(b'P')
            else:
                self.write(b'O')


class MockedDevice:
    _dtr: bool = False
    input_buffer: bytes
    output_buffer: bytes
    """Mocked serial device that simulates RS232 behavior."""

    def __init__(self, protocol: bytes) -> None:
        if protocol not in (b'P014', b'P016', b'P018', b'P18A'):
            raise ValueError(protocol)
        self.protocol = protocol
        self.condition = threading.Condition()
        self.input_buffer = b''
        self.output_buffer = b''
        self.is_open = True
        self.work_thread = MockedDeviceThread(self)

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
        with self.condition:
            self.input_buffer += data
            self.condition.notify_all()

    def read(self, length: int = 1) -> bytes:
        """Simulate reading a line from the serial port."""
        with self.condition:
            self.condition.wait_for(lambda: bool(self.output_buffer) or not self.is_open, timeout=0.1)
            requested_data = self.output_buffer[:length]
            self.output_buffer = self.output_buffer[length:]
            return requested_data

    def receive(self, count: int, timeout: float | None) -> bytes:
        with self.condition:
            self.condition.wait_for(lambda: len(self.input_buffer) >= count or not self.is_open, timeout=timeout)
            data = self.input_buffer[:count]
            self.input_buffer = self.input_buffer[count:]
            return data

    def close(self) -> None:
        """Simulate closing the serial port."""
        with self.condition:
            self.is_open = False
            self.condition.notify_all()

    def mock_send(self, data: bytes) -> None:
        """Simulate the device sending data to the serial port."""
        with self.condition:
            self.output_buffer += data
            self.condition.notify_all()

    def reset_input_buffer(self) -> None:
        with self.condition:
            self.output_buffer = b''

    def flushInput(self) -> None:  # noqa: N802 - pyserial compatibility
        self.reset_input_buffer()

    def _reset(self) -> None:
        with self.condition:
            self.output_buffer = b''
            self.input_buffer = b''
            self.work_thread.in_jump_table = False
            self.work_thread.is_programming_voltages_on = False
            self.work_thread.programing_vars = None
            self.work_thread.pending_fuses = None
            self.mock_send(b'B\x03')
