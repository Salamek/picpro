import struct
import dataclasses
from typing import Optional, Union
import time

@dataclasses.dataclass
class ProgramingVarsFlags:  # @TODO use this in code too
    flag_calibration_value_in_rom: bool
    flag_band_gap_fuse: bool
    flag_18f_single_panel_access_mode: bool
    flag_vcc_vpp_delay: bool

    @classmethod
    def from_int(cls, flags: int) -> 'ProgramingVarsFlags':
        return cls(
            flag_calibration_value_in_rom = bool(flags & 1),
            flag_band_gap_fuse= bool(flags & 2),
            flag_18f_single_panel_access_mode= bool(flags & 4),
            flag_vcc_vpp_delay= bool(flags & 8),
        )


    def to_int(self) -> int:
        return (
                (self.flag_calibration_value_in_rom and 1) |
                (self.flag_band_gap_fuse and 2) |
                (self.flag_18f_single_panel_access_mode and 4) |
                (self.flag_vcc_vpp_delay and 8)
        )


@dataclasses.dataclass
class ProgramingVars:  # @TODO use this in code too
    rom_size_words: int
    eeprom_size: int
    core_type: int
    flags: ProgramingVarsFlags
    program_delay: int
    power_sequence: int
    erase_mode: int
    program_retries: int
    over_program: int

    @classmethod
    def from_bytes(cls, data: bytes) -> 'ProgramingVars':
        (
            rom_size_words,
            eeprom_size,
            core_type,
            flags,
            program_delay,
            power_sequence,
            erase_mode,
            program_retries,
            over_program
        ) = struct.unpack('>HHBBBBBBB', data)

        if not rom_size_words:
            raise ValueError('rom_size_words cannot be empty')

        if rom_size_words % 32 != 0:
            raise ValueError('rom_size_words has to be multiple of 32')

        if eeprom_size and eeprom_size % 32 != 0:
            raise ValueError('eeprom_size has to be multiple of 32')

        if core_type not in range(1, 14):  # note: 13 is max
            raise ValueError('Unknown core_type')

        if power_sequence not in range(0, 5):  # note: 13 is max
            raise ValueError('Unknown power_sequence')

        if not program_retries:
            raise ValueError('program_retries has to be at least 1')

        return cls(
            rom_size_words=rom_size_words,
            eeprom_size=eeprom_size,
            core_type=core_type,
            flags=ProgramingVarsFlags.from_int(flags),
            program_delay=program_delay,
            power_sequence=power_sequence,
            erase_mode=erase_mode,
            program_retries=program_retries,
            over_program=over_program
        )

    def to_bytes(self) -> bytes:
        return struct.pack(
            '>HHBBBBBBB',
            self.rom_size_words,
            self.eeprom_size,
            self.core_type,
            self.flags.to_int(),
            self.program_delay,
            self.power_sequence,
            self.erase_mode,
            self.program_retries,
            self.over_program
        )


class P018aMockedDeviceThread:
    in_jump_table: bool
    is_programming_voltages_on: bool
    programing_vars: Optional[ProgramingVars]
    def __init__(self, device: 'P018aMockedDevice'):
        self.device = device
        self.is_programming_voltages_on = False
        self.in_jump_table = False
        self.programing_vars = None

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
        for i in range(0, number_of_packets):
            received_rom_data += self.read(32)
            self.write(b'Y')

        if len(received_rom_data) == send_rom_size:
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
        for i in range(0, eeprom_packets):
            received_eeprom_data += self.read(2)
            self.write(b'Y')

        # We need to eat two bytes send here by protocol, comment from protocol:
        # We must send an extra two bytes, which will have no effect.
        # Why?  I'm not sure.  See protocol doc, and read it backwards.
        # I'm sending zeros because if we did wind up back at the
        # command jump table, then the zeros will have no effect.
        self.read(2)

        if len(received_eeprom_data) == send_eeprom_size:
            self.write(b'P')
        else:
            self.write(b'N')

    def _program_id_fuzes(self) -> None:
        # program_eeprom
        if not self.programing_vars or not self.is_programming_voltages_on:
            # programing_vars and is_programming_voltages_on has to be set for successful program
            self.write(b'N')
            return

        fuse_settings = self.read(24) # @TODO decode this and do checks
        # @TODO implement FuseTransaction
        print('TODO', fuse_settings)
        self.write(b'Y')

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
                    try:
                        self.programing_vars = ProgramingVars.from_bytes(settings)
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
                    self.is_programming_voltages_on = not self.is_programming_voltages_on
                    self.write(b'V')
                elif data == b'\x07':
                    self._program_rom()
                elif data == b'\x08':
                    self._program_eeprom()
                elif data == b'\x09':
                    self._program_id_fuzes()
                elif data == b'\x12' or data == b'\x13':
                    # wait_until_chip_in_socket/ wait_until_chip_out_of_socket
                    self.write(b'AY')
                elif data == b'\x14':
                    # programmer_version
                    self.write(b'\x03')
                elif data == b'\x15':
                    # get protocol
                    self.write(b'P18A')
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


class P018aMockedDevice:
    _dtr: bool = False
    input_buffer: bytes
    output_buffer: bytes
    """Mocked serial device that simulates RS232 behavior."""

    def __init__(self) -> None:
        self.input_buffer = b''
        self.output_buffer = b''
        self.is_open = True
        self.work_thread = P018aMockedDeviceThread(self)

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