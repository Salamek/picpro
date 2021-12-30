import struct
import time
from typing import Union

from pic_k150_programmer.DataString import DataString
from pic_k150_programmer.exceptions import InvalidValueError, InvalidResponseError, InvalidCommandSequenceError


class ProtocolInterface:
    """A convenient interface to the DIY serial/USB PIC programmer kits"""

    def __init__(self, port):
        self.port = port
        # We need to set the port timeout to a small value and use
        # polling to simulate variable timeouts.  Why?  Because any
        # time you set the timeout in the serial library, DTR goes
        # high, which resets any programmer other than the 149!
        self.port.timeout = .1
        self.vars_set = False
        self.fuses_set = False
        self.firmware_type = None
        self.vars = None
        self.reset()

    def _read(self, count: int = 1, timeout: Union[int, float, None] = 5):
        # _read(count, timeout)
        # Read bytes from the port.  Stop when the requested number of
        # bytes have been received, or the timeout has passed.  In order
        # to sidestep issues with the serial library this is done by
        # polling the serial port's read() method.
        result = ''
        init_time = time.time()
        end_time = None
        if timeout is not None:
            end_time = init_time + timeout
        while (count > 0) and ((end_time is None) or (time.time() < end_time)):
            read_result = self.port.read(count)
            count = (count - len(read_result))
            result = result + read_result

        return result

    def _core_bits(self):
        self._need_vars()
        core_type = self.vars['core_type']

        if core_type in [1, 2]:
            return 16
        elif core_type in [3, 5, 6, 7, 8, 9, 10]:
            return 14
        elif core_type in [4]:
            return 12
        else:
            return None

    def _expect(self, expected, timeout: Union[int, float, None] = 10):
        """Raise an exception if the expected response byte is not sent by the PIC programmer before timeout."""
        response = self._read(len(expected), timeout=timeout)
        if response != expected:
            raise InvalidResponseError('expected "{}" received {}'.format(expected, response))

    def _need_vars(self):
        if not self.vars_set:
            raise InvalidCommandSequenceError('Vars not set')

    def _need_fuses(self):
        if not self.fuses_set:
            raise InvalidCommandSequenceError('Fuses not set')

    def reset(self):
        """Resets the PIC Programmer's on-board controller."""
        self.vars_set = False
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
        if response == '':
            # Apparently the unit operates with DTR high, so...
            self.port.setDTR(True)
            time.sleep(.1)
            response = self._read(2, timeout=.3)

        if len(response) >= 1:
            result = (response[0] == 'B')
        else:
            result = False
        if result and (len(response) == 2):
            self.firmware_type, = struct.unpack('B', response[1])
        return result

    def _command_start(self, cmd=None):
        # Send command 1: if we're at the jump table already this will
        # get us out.  If we're awaiting command start, this will
        # still echo 'Q' and await another command start.
        self.port.write('\x01')
        self._expect('Q')

        # Start command, go to jump table.
        self.port.write('P')

        # Check for acknowledgement
        ack = self._read(1)
        result = (ack == 'P')
        if not result:
            raise InvalidResponseError('No acknowledgement for command start.')

        # Send command number, if specified
        if cmd is not None:
            self.port.write(chr(cmd))
        return result

    def _null_command(self):
        cmd = 0
        self.port.write(chr(cmd))
        return None

    def _command_end(self):
        cmd = 1
        self.port.write(chr(cmd))
        ack = self._read(1, timeout=10)
        result = (ack == 'Q')
        if not result:
            if ack != '':
                raise InvalidResponseError('Unexpected response ("{}") in command end.'.format(ack))
            else:
                raise InvalidResponseError('No acknowledgement for command end.')
        return result

    def echo(self, msg='X'):
        """Instructs the PIC programmer to echo back the message
        string.  Returns the PIC programmer's response."""
        cmd = 2
        self._command_start()
        result = ''
        for c in msg:
            self.port.write(chr(cmd))
            self.port.write(c)
            response = self._read(1)
            result = result + response
        self._command_end()
        return result

    def init_programming_vars(
            self,
            rom_size,
            eeprom_size,
            core_type,
            flag_calibration_value_in_rom,
            flag_band_gap_fuse,
            flag_18f_single_panel_access_mode,
            flag_vcc_vpp_delay,
            program_delay,
            power_sequence,
            erase_mode,
            program_retries,
            over_program):
        """Inform PIC programmer of general parameters of PIC to be
         programmed.  Necessary for use of various other commands."""

        cmd = 3
        self._command_start(cmd)

        flags = ((flag_calibration_value_in_rom and 1) | (flag_band_gap_fuse and 2) | (flag_18f_single_panel_access_mode and 4) | (flag_vcc_vpp_delay and 8))

        command_payload = struct.pack(
            '>HHBBBBBBB',
            rom_size,
            eeprom_size,
            core_type,
            flags,
            program_delay,
            power_sequence,
            erase_mode,
            program_retries,
            over_program
        )

        self.port.write(command_payload)
        response = self._read(1)
        self._command_end()

        result = (response == 'I')
        if result:
            self.vars = {
                'rom_size': rom_size,
                'eeprom_size': eeprom_size,
                'core_type': core_type,
                'flag_calibration_value_in_ROM': flag_calibration_value_in_rom,
                'flag_band_gap_fuse': flag_band_gap_fuse,
                'flag_18f_single_panel_access_mode': flag_18f_single_panel_access_mode,
                'flag_vcc_vpp_delay': flag_vcc_vpp_delay,
                'program_delay': program_delay,
                'power_sequence': power_sequence,
                'erase_mode': erase_mode,
                'program_retries': program_retries,
                'over_program': over_program
            }
            self.vars_set = True
        else:
            del self.vars
            self.vars_set = False
        return result

    def _set_programming_voltages_command(self, on):
        """Turn the PIC programming voltages on or off.  Must be called as part of other commands which read or write PIC data."""
        cmd_on = 4
        cmd_off = 5

        self._need_vars()
        if on:
            self.port.write(chr(cmd_on))
            expect = 'V'
        else:
            self.port.write(chr(cmd_off))
            expect = 'v'
        response = self._read(1)
        return response == expect

    def cycle_programming_voltages(self):
        cmd = 6
        self._need_vars()
        self._command_start(cmd)
        response = self._read(1)
        self._command_end()
        return response == 'V'

    def program_rom(self, data):
        """Write data to ROM.  data should be a binary string of data, high byte first."""
        cmd = 7
        self._need_vars()

        word_count = (len(data) // 2)
        if self.vars['rom_size'] < word_count:
            raise InvalidValueError('Data too large for PIC ROM')

        if ((word_count * 2) % 32) != 0:
            raise InvalidValueError('ROM data must be a multiple of 32 bytes in size.')

        self._command_start()
        self._set_programming_voltages_command(True)
        self.port.write(chr(cmd))

        word_count_message = struct.pack('>H', word_count)
        self.port.write(word_count_message)

        self._expect('Y', timeout=20)
        try:
            for i in range(0, (word_count * 2), 32):
                self.port.write(data[i:(i + 32)])
                self._expect('Y', timeout=20)
            self._expect('P', timeout=20)
        except InvalidResponseError:
            self.port.flushInput()  # We don't get current address for now.
            return False

        self._set_programming_voltages_command(False)
        self._command_end()
        return True

    def program_eeprom(self, data):
        """Write data to EEPROM.  Data size must be small enough to fit in EEPROM."""
        cmd = 8
        self._need_vars()

        byte_count = len(data)
        if self.vars['eeprom_size'] < byte_count:
            raise InvalidValueError('Data too large for PIC EEPROM')

        if (byte_count % 2) != 0:
            raise InvalidValueError('EEPROM data must be a multiple of 2 bytes in size.')

        self._command_start()
        self._set_programming_voltages_command(True)
        self.port.write(chr(cmd))

        byte_count_message = struct.pack('>H', byte_count)
        self.port.write(byte_count_message)

        self._expect('Y', timeout=20)
        for i in range(0, byte_count, 2):
            self.port.write(data[i:(i + 2)])
            self._expect('Y', timeout=20)
        # We must send an extra two bytes, which will have no effect.
        # Why?  I'm not sure.  See protocol doc, and read it backwards.
        # I'm sending zeros because if we did wind up back at the
        # command jump table, then the zeros will have no effect.
        self.port.write('\x00\x00')
        self._expect('P', timeout=20)

        self._set_programming_voltages_command(False)
        self._command_end()
        return True

    def program_id_fuses(self, pic_id, fuses):
        """Program PIC ID and fuses.  For 16-bit processors, fuse values
        are not committed until program_18fxxxx_fuse() is called."""
        cmd = 9
        self._need_vars()

        core_bits = self._core_bits()
        if core_bits == 16:
            if len(pic_id) != 8:
                raise InvalidValueError('Should have 8-byte ID for 16 bit core.')
            if len(fuses) != 7:
                raise InvalidValueError('Should have 7 fuses for 16 bit core.')
            command_body = ('00' + pic_id + struct.pack('<HHHHHHH', *fuses).decode('ASCI'))  # @FIXME Add ASCI
            response_ok = 'Y'
        else:
            if len(fuses) != 1:
                raise InvalidValueError('Should have one fuse for 14 bit core.')
            if len(pic_id) != 4:
                raise InvalidValueError('Should have 4-byte ID for 14 bit core.')
            # Command starts with dual '0' for 14 bit
            command_body = ('00' + pic_id + 'FFFF' + struct.pack('<H', fuses[0]).decode('ASCI') + ('\xff\xff' * 6))  # @FIXME Add ASCI
            response_ok = 'Y'

        self._command_start()
        self._set_programming_voltages_command(True)
        self.port.write(chr(cmd))

        self.port.write(command_body)

        response = self._read(timeout=20)

        self._set_programming_voltages_command(False)
        self._command_end()

        if response == response_ok:
            self.fuses_set = True

        return response == response_ok

    def read_rom(self):
        """Returns contents of PIC ROM as a string of big-endian values."""
        cmd = 11
        self._need_vars()

        # vars['rom_size'] is in words.  So multiply by two to get bytes.
        rom_size = self.vars['rom_size'] * 2

        self._command_start()
        self._set_programming_voltages_command(True)
        self.port.write(chr(cmd))

        response = self._read(rom_size)

        self._set_programming_voltages_command(False)
        self._command_end()
        return DataString(response)

    def read_eeprom(self):
        """Returns data stored in PIC EEPROM."""
        cmd = 12
        self._need_vars()

        eeprom_size = self.vars['eeprom_size']

        self._command_start()
        self._set_programming_voltages_command(True)
        self.port.write(chr(cmd))
        response = self._read(eeprom_size)
        self._set_programming_voltages_command(False)
        self._command_end()
        return DataString(response)

    def read_config(self):
        """Reads chip ID and programmed ID, fuses, and calibration."""
        cmd = 13
        self._command_start()
        self._set_programming_voltages_command(True)
        self.port.write(chr(cmd))
        ack = self._read(1)
        if ack != 'C':
            raise InvalidResponseError('No acknowledgement from read_config()')
        response = self._read(26)
        self._set_programming_voltages_command(False)
        self._command_end()

        config = struct.unpack('<HccccccccHHHHHHHH', response)
        result = {'chip_id': config[0],
                  'id': ''.join(config[1:9]),
                  'fuses': list(config[9:16]),
                  'calibrate': config[16]}
        return result

    def erase_chip(self):
        """Erases all data from chip."""
        cmd = 14
        self._need_vars()

        self._command_start(cmd)
        response = self._read(1)
        self._command_end()
        return response == 'Y'

    def rom_is_blank(self, high_byte):
        """Returns True if PIC ROM is blank."""
        cmd = 15
        self._need_vars()

        expected_b_bytes = (self.vars['rom_size'] // 256) - 1
        self._command_start(cmd)
        self.port.write(high_byte)
        while True:
            response = self._read(1)
            if response == 'Y':
                self._command_end()
                return True
            if response == 'N':
                self._command_end()
                return False
            if response == 'C':
                self._command_end()
                return False
            if response == 'B':
                if expected_b_bytes <= 0:
                    raise InvalidResponseError('Received wrong number of "B" bytes in rom_is_blank()')
            else:
                raise InvalidResponseError('Unexpected byte in rom_is_blank(): {}'.format(response))

    def eeprom_is_blank(self):
        """Returns True if PIC EEPROM is blank."""
        cmd = 16
        self._command_start(cmd)
        response = self._read(1)
        self._command_end()
        if (response != 'Y') and (response != 'N'):
            raise InvalidResponseError('Unexpected response in eeprom_is_blank(): {}'.format(response))

        return response == 'Y'

    def program_18fxxxx_fuse(self):
        """Commits fuse values previously loaded using program_id_fuses()"""
        cmd = 17

        self._need_vars()
        self._need_fuses()
        self._command_start(cmd)
        # It appears the command will return 'B' on chips for which
        # this isn't appropriate?
        response = self._read(1)
        result = response == 'Y'
        self._command_end()

        return result

    def wait_until_chip_in_socket(self):
        """Blocks until a chip is inserted in the programming socket."""
        cmd = 18

        self._command_start(cmd)
        self._expect('A')

        self._expect('Y', timeout=None)
        self._command_end()
        return True

    def wait_until_chip_out_of_socket(self):
        """Blocks until chip is removed from programming socket."""
        cmd = 19

        self._command_start(cmd)
        self._expect('A')

        self._expect('Y', timeout=None)
        self._command_end()
        return True

    def programmer_firmware_version(self):
        """Returns the PIC programmer's numeric firmware version."""
        cmd = 20
        self._command_start(cmd)
        response = self._read(1)
        self._command_end()
        result, = struct.unpack('B', response)
        return result

    def programmer_protocol(self):
        """Returns the PIC programmer's protocol version in text form."""
        cmd = 21
        self._command_start(cmd)
        # Protocol doc isn't clear on the format of command 22's output.
        # Presumably it will always be exactly 4 bytes.
        response = self._read(4)
        self._command_end()
        return response

    def program_debug_vector(self, address):
        """Sets the PIC's debugging vector."""
        cmd = 22
        self._need_vars()

        be4_address = struct.pack('>I', address)
        self._command_start(cmd)
        self.port.write(be4_address[1:4])
        response = self._read(1)
        self._command_end()

        if (response != 'Y') and (response != 'N'):
            raise InvalidResponseError('Unexpected response in program_debug_vector(): {}'.format(response))

        return response == 'Y'

    def read_debug_vector(self):
        """Returns the value of the PIC's debugging vector."""
        cmd = 23
        self._need_vars()

        self._command_start(cmd)
        response = self._read(4)
        be4_address = '\x00' + response[1:4]
        result, = struct.unpack('>I', be4_address)
        self._command_end()

        return result
