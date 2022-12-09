import struct
import time
from typing import Union, List, Optional
import serial
from picpro.IChipInfoEntry import IChipInfoEntry
from picpro.exceptions import InvalidValueError, InvalidResponseError, InvalidCommandSequenceError


class ProtocolInterface:
    """A convenient interface to the DIY serial/USB PIC programmer kits"""

    def __init__(self, port: serial.Serial):
        self.port = port
        # We need to set the port timeout to a small value and use
        # polling to simulate variable timeouts.  Why?  Because any
        # time you set the timeout in the serial library, DTR goes
        # high, which resets any programmer other than the 149!
        self.port.timeout = .1
        self.chip_info: Union[IChipInfoEntry, None] = None
        self.fuses_set = False
        self.firmware_type: Union[int, None] = None
        self.reset()

    def _read(self, count: int = 1, timeout: Union[int, float, None] = 5) -> bytes:
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
            read_result = self.port.read(count)
            count = (count - len(read_result))
            result = result + read_result

        return result

    def _expect(self, expected: bytes, timeout: Union[int, float, None] = 10) -> None:
        """Raise an exception if the expected response byte is not sent by the PIC programmer before timeout."""
        response = self._read(len(expected), timeout=timeout)
        if response != expected:
            raise InvalidResponseError('expected "{!r}" received {!r}'.format(expected, response))

    def _need_chip_info(self) -> None:
        if not self.chip_info:
            raise InvalidCommandSequenceError('Chip info is not set')

    def _need_fuses(self) -> None:
        if not self.fuses_set:
            raise InvalidCommandSequenceError('Fuses not set')

    def reset(self) -> bool:
        """Resets the PIC Programmer's on-board controller."""
        self.chip_info = None
        self.fuses_set = False
        self.firmware_type = None

        self.port.setDTR(True)
        time.sleep(.1)
        self.port.flushInput()
        # Detect whether this unit operates with DTR high, or DTR low.
        self.port.setDTR(False)
        time.sleep(.1)
        # Input was just flushed.  If the unit operates with DTR low,
        # then the unit is now on, and we should be seeing a 2 byte
        # response.
        response = self._read(2, timeout=.3)
        if response == b'':
            # Apparently the unit operates with DTR high, so...
            self.port.setDTR(True)
            time.sleep(.1)
            response = self._read(2, timeout=.3)

        if len(response) >= 1:
            result = response[0].to_bytes(1, 'little') == b'B'
        else:
            result = False
        if result and len(response) == 2:
            self.firmware_type = response[1]
        return result

    def _command_start(self, cmd: Optional[int] = None) -> bool:
        # Send command 1: if we're at the jump table already this will
        # get us out.  If we're awaiting command start, this will
        # still echo 'Q' and await another command start.

        self.port.write(b'\x01')
        self._expect(b'Q')

        # Start command, go to jump table.
        self.port.write(b'P')

        # Check for acknowledgement
        ack = self._read(1)
        result = (ack == b'P')
        if not result:
            raise InvalidResponseError('No acknowledgement for command start.')

        result = True
        # Send command number, if specified
        if cmd is not None:
            self.port.write(cmd.to_bytes(1, 'little'))
        return result

    def _null_command(self) -> None:
        cmd = 0
        self.port.write(cmd)

    def _command_end(self) -> bool:
        cmd = b'\x01'
        self.port.write(cmd)
        ack = self._read(1, timeout=10)
        result = (ack == b'Q')
        if not result:
            if ack != b'':
                raise InvalidResponseError('Unexpected response ("{!r}") in command end.'.format(ack))
            raise InvalidResponseError('No acknowledgement for command end.')
        return result

    def echo(self, msg: bytes = b'X') -> bytes:
        """Instructs the PIC programmer to echo back the message
        string.  Returns the PIC programmer's response."""
        cmd = b'\x02'
        self._command_start()
        result = b''

        for c in msg:
            self.port.write(cmd)
            self.port.write(c.to_bytes(1, 'little'))
            response = self._read(1)
            result = result + response
        self._command_end()
        return result

    def init_programming_vars(self, chip_info: IChipInfoEntry, icsp_mode: bool = False) -> bool:
        """Inform PIC programmer of general parameters of PIC to be
         programmed.  Necessary for use of various other commands."""

        programing_vars = chip_info.programming_vars

        if icsp_mode:
            if programing_vars.power_sequence == 2:
                programing_vars.power_sequence = 1
            elif programing_vars.power_sequence == 4:
                programing_vars.power_sequence = 3

        cmd = 3
        self._command_start(cmd)

        flags = (
                (programing_vars.flag_calibration_value_in_rom and 1) |
                (programing_vars.flag_band_gap_fuse and 2) |
                (programing_vars.flag_18f_single_panel_access_mode and 4) |
                (programing_vars.flag_vcc_vpp_delay and 8)
        )

        command_payload = struct.pack(
            '>HHBBBBBBB',
            programing_vars.rom_size,
            programing_vars.eeprom_size,
            programing_vars.core_type,
            flags,
            programing_vars.program_delay,
            programing_vars.power_sequence,
            programing_vars.erase_mode,
            programing_vars.program_retries,
            programing_vars.over_program
        )

        self.port.write(command_payload)
        response = self._read(1)
        self._command_end()

        result = (response == b'I')
        if result:
            self.chip_info = chip_info
        else:
            self.chip_info = None
        return result

    def _set_programming_voltages_command(self, on: bool) -> bool:
        """Turn the PIC programming voltages on or off.  Must be called as part of other commands which read or write PIC data."""
        cmd_on = 4
        cmd_off = 5

        self._need_chip_info()
        if on:
            self.port.write(cmd_on.to_bytes(1, 'little'))
            expect = b'V'
        else:
            self.port.write(cmd_off.to_bytes(1, 'little'))
            expect = b'v'
        response = self._read(1)
        return response == expect

    def cycle_programming_voltages(self) -> bool:
        cmd = 6
        self._need_chip_info()
        self._command_start(cmd)
        response = self._read(1)
        self._command_end()
        return response == b'V'

    def program_rom(self, data: bytearray) -> bool:
        """Write data to ROM.  data should be a binary string of data, high byte first."""
        cmd = 7
        self._need_chip_info()

        word_count = (len(data) // 2)
        if self.chip_info.programming_vars.rom_size < word_count:  # type: ignore
            raise InvalidValueError('Data too large for PIC ROM')

        if ((word_count * 2) % 32) != 0:
            raise InvalidValueError('ROM data must be a multiple of 32 bytes in size.')

        self._command_start()
        self._set_programming_voltages_command(True)

        self.port.write(cmd.to_bytes(1, 'little'))

        word_count_message = struct.pack('>H', word_count)
        self.port.write(word_count_message)
        self._expect(b'Y', timeout=20)

        try:
            for i in range(0, (word_count * 2), 32):
                to_write = data[i:(i + 32)]
                self.port.write(to_write)
                self._expect(b'Y', timeout=20)
            self._expect(b'P', timeout=20)
        except InvalidResponseError:
            self.port.flushInput()  # We don't get current address for now.
            return False

        self._set_programming_voltages_command(False)
        self._command_end()
        return True

    def program_eeprom(self, data: bytes) -> bool:
        """Write data to EEPROM.  Data size must be small enough to fit in EEPROM."""
        cmd = 8
        self._need_chip_info()

        byte_count = len(data)
        if self.chip_info.programming_vars.eeprom_size < byte_count:  # type: ignore
            raise InvalidValueError('Data too large for PIC EEPROM')

        if (byte_count % 2) != 0:
            raise InvalidValueError('EEPROM data must be a multiple of 2 bytes in size.')

        self._command_start()
        self._set_programming_voltages_command(True)
        self.port.write(cmd.to_bytes(1, 'little'))

        byte_count_message = struct.pack('>H', byte_count)
        self.port.write(byte_count_message)

        self._expect(b'Y', timeout=20)
        for i in range(0, byte_count, 2):
            self.port.write(data[i:(i + 2)])
            self._expect(b'Y', timeout=20)
        # We must send an extra two bytes, which will have no effect.
        # Why?  I'm not sure.  See protocol doc, and read it backwards.
        # I'm sending zeros because if we did wind up back at the
        # command jump table, then the zeros will have no effect.
        self.port.write(b'\x00\x00')
        self._expect(b'P', timeout=20)

        self._set_programming_voltages_command(False)
        self._command_end()
        return True

    def program_id_fuses(self, pic_id: bytes, fuses: List[int]) -> bool:
        """Program PIC ID and fuses.  For 16-bit processors, fuse values
        are not committed until program_18fxxxx_fuse() is called."""
        cmd = 9
        self._need_chip_info()

        core_bits = self.chip_info.get_core_bits()  # type: ignore
        if core_bits == 16:
            if len(pic_id) != 8:
                raise InvalidValueError('Should have 8-byte ID for 16 bit core.')
            if len(fuses) != 7:
                raise InvalidValueError('Should have 7 fuses for 16 bit core.')
            command_body = (b'00' + pic_id + struct.pack('<HHHHHHH', *fuses))
            response_ok = b'Y'
        else:
            if len(fuses) != 1:
                raise InvalidValueError('Should have one fuse for 14 bit core.')
            if len(pic_id) != 4:
                raise InvalidValueError('Should have 4-byte ID for 14 bit core.')
            # Command starts with dual '0' for 14 bit
            command_body = (b'00' + pic_id + b'FFFF' + struct.pack('<H', fuses[0]) + (b'\xff\xff' * 6))
            response_ok = b'Y'

        self._command_start()
        self._set_programming_voltages_command(True)
        self.port.write(cmd.to_bytes(1, 'little'))
        self.port.write(command_body)

        response = self._read(timeout=20)

        self._set_programming_voltages_command(False)
        self._command_end()

        if response == response_ok:
            self.fuses_set = True

        return response == response_ok

    def program_calibration(self, calibrate: int, fuse: int) -> bytes:
        """
        Program calibration
        Args:
            calibrate:
            fuse:

        Returns:

        """
        cmd = 10
        self._need_chip_info()

        self._command_start()
        self._set_programming_voltages_command(True)
        self.port.write(cmd.to_bytes(1, 'little'))

        """
        Calibration High (Byte)
        Calibration Low  (Byte)
        FUSE High (Byte)
        FUSE Low  (Byte)
        """
        calibration = calibrate.to_bytes(2, 'big') + fuse.to_bytes(2, 'big')
        self.port.write(calibration)

        response = self._read(timeout=10)  # C= calibration fail, F = Fuse fail, Y = OK
        self._set_programming_voltages_command(False)
        self._command_end()
        response_ok = b'Y'

        return response

    def read_rom(self) -> bytes:
        """Returns contents of PIC ROM as a string of big-endian values."""
        cmd = 11
        self._need_chip_info()

        # vars['rom_size'] is in words.  So multiply by two to get bytes.
        rom_size = self.chip_info.programming_vars.rom_size * 2  # type: ignore

        self._command_start()
        self._set_programming_voltages_command(True)
        self.port.write(cmd.to_bytes(1, 'little'))

        response = self._read(rom_size)
        self._set_programming_voltages_command(False)
        self._command_end()
        return response

    def read_eeprom(self) -> bytes:
        """Returns data stored in PIC EEPROM."""
        cmd = 12
        self._need_chip_info()

        eeprom_size = self.chip_info.programming_vars.eeprom_size  # type: ignore

        self._command_start()
        self._set_programming_voltages_command(True)
        self.port.write(cmd.to_bytes(1, 'little'))
        response = self._read(eeprom_size)
        self._set_programming_voltages_command(False)
        self._command_end()
        return response

    def read_config(self) -> dict:
        """Reads chip ID and programmed ID, fuses, and calibration."""
        cmd = 13
        self._command_start()
        self._set_programming_voltages_command(True)
        self.port.write(cmd.to_bytes(1, 'little'))
        ack = self._read(1)
        if ack != b'C':
            raise InvalidResponseError('No acknowledgement from read_config()')
        response = self._read(26)
        self._set_programming_voltages_command(False)
        self._command_end()

        config = struct.unpack('<HccccccccHHHHHHHH', response)
        result = {'chip_id': config[0],
                  'id': b''.join(config[1:9]),
                  'fuses': list(config[9:16]),
                  'calibrate': config[16]}
        return result

    def erase_chip(self) -> bool:
        """Erases all data from chip."""
        cmd = 14
        self._need_chip_info()

        self._command_start()
        self._set_programming_voltages_command(True)
        self.port.write(cmd.to_bytes(1, 'little'))
        response = self._read(1)
        self._set_programming_voltages_command(False)
        self._command_end()
        return response == b'Y'

    def rom_is_blank(self, high_byte: bytes) -> bool:
        """Returns True if PIC ROM is blank."""
        cmd = 15
        self._need_chip_info()

        expected_b_bytes = (self.chip_info.programming_vars.rom_size // 256) - 1  # type: ignore
        self._command_start(cmd)
        self.port.write(high_byte)
        while True:
            response = self._read(1)
            if response == b'Y':
                self._command_end()
                return True
            if response == b'N':
                self._command_end()
                return False
            if response == b'C':
                self._command_end()
                return False
            if response == b'B':
                if expected_b_bytes <= 0:
                    raise InvalidResponseError('Received wrong number of "B" bytes in rom_is_blank()')
            else:
                raise InvalidResponseError('Unexpected byte in rom_is_blank(): {!r}'.format(response))

    def eeprom_is_blank(self) -> bool:
        """Returns True if PIC EEPROM is blank."""
        cmd = 16
        self._command_start(cmd)
        response = self._read(1)
        self._command_end()
        if response not in [b'Y', b'N']:
            raise InvalidResponseError('Unexpected response in eeprom_is_blank(): {!r}'.format(response))

        return response == b'Y'

    def program_18fxxxx_fuse(self) -> bool:
        """Commits fuse values previously loaded using program_id_fuses()"""
        cmd = 17
        self._need_chip_info()
        self._need_fuses()
        self._command_start(cmd)
        # It appears the command will return 'B' on chips for which
        # this isn't appropriate?
        response = self._read(1)
        result = response == b'Y'
        self._command_end()

        return result

    def wait_until_chip_in_socket(self) -> bool:
        """Blocks until a chip is inserted in the programming socket."""
        cmd = 18
        self._command_start(cmd)
        self._expect(b'A')

        self._expect(b'Y', timeout=None)
        self._command_end()
        return True

    def wait_until_chip_out_of_socket(self) -> bool:
        """Blocks until chip is removed from programming socket."""
        cmd = 19

        self._command_start(cmd)
        self._expect(b'A')

        self._expect(b'Y', timeout=None)
        self._command_end()
        return True

    def programmer_firmware_version(self) -> bytes:
        """Returns the PIC programmer's numeric firmware version."""
        cmd = 20
        self._command_start(cmd)
        response = self._read(1)
        self._command_end()
        result, = struct.unpack('B', response)
        return result

    def programmer_protocol(self) -> bytes:
        """Returns the PIC programmer's protocol version in text form."""
        cmd = 21
        self._command_start(cmd)
        # Protocol doc isn't clear on the format of command 22's output.
        # Presumably it will always be exactly 4 bytes.
        response = self._read(4)
        self._command_end()
        return response

    def program_debug_vector(self, address: bytes) -> bool:
        """Sets the PIC's debugging vector."""
        cmd = 22
        self._need_chip_info()

        be4_address = struct.pack('>I', address)
        self._command_start(cmd)
        self.port.write(be4_address[1:4])
        response = self._read(1)
        self._command_end()

        if response not in [b'Y', b'N']:
            raise InvalidResponseError('Unexpected response in program_debug_vector(): {!r}'.format(response))

        return response == b'Y'

    def read_debug_vector(self) -> bytes:
        """Returns the value of the PIC's debugging vector."""
        cmd = 23
        self._need_chip_info()

        self._command_start(cmd)
        response = self._read(4)
        be4_address = b'\x00' + response[1:4]
        result, = struct.unpack('>I', be4_address)
        self._command_end()

        return result
