import struct
from typing import List, Optional
from picpro.protocol.IProgrammingInterface import IProgrammingInterface
from picpro.protocol.IFuseTransaction import IFuseTransaction
from picpro.exceptions import InvalidResponseError, InvalidValueError
from picpro.protocol.ChipConfig import ChipConfig


# @TODO Missing commands to implement: 14 and 25.
class FuseTransaction(IFuseTransaction):
    def program_18fxxxx_fuse(self, fuses: List[int]) -> None:
        """Commits fuse values previously loaded using program_id_fuses()"""
        cmd = 18

        command_body = (b'\x00' * 10) + struct.pack('<HHHHHHH', *fuses)  # send all 0 in id, and then the fuse values
        self.programming_interface.connection.command_start()
        self.programming_interface.set_programming_voltages_command(True)
        self.programming_interface.connection.serial_connection.write(cmd.to_bytes(1, 'little'))
        self.programming_interface.connection.serial_connection.write(command_body)
        # It appears the command will return 'B' on chips for which
        # this isn't appropriate?
        response = self.programming_interface.connection.read(1)
        result = response == b'Y'
        self.programming_interface.set_programming_voltages_command(False)
        self.programming_interface.connection.command_end()

        if not result:
            raise InvalidResponseError


class ProgrammingInterface(IProgrammingInterface):

    def _init_programming_vars(self, icsp_mode: bool = False) -> None:
        """Inform PIC programmer of general parameters of PIC to be
         programmed.  Necessary for use of various other commands."""

        programing_vars = self.chip_info.programming_vars

        if icsp_mode:
            if programing_vars.power_sequence == 2:
                programing_vars.power_sequence = 1
            elif programing_vars.power_sequence == 4:
                programing_vars.power_sequence = 3

        cmd = 3
        self.connection.command_start(cmd)

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

        self.connection.serial_connection.write(command_payload)
        self.connection.expect(b'I', send_command_end=True)

    def set_programming_voltages_command(self, on: bool) -> None:
        """Turn the PIC programming voltages on or off.  Must be called as part of other commands which read or write PIC data."""
        cmd_on = 4
        cmd_off = 5

        if on:
            self.connection.serial_connection.write(cmd_on.to_bytes(1, 'little'))
            expect = b'V'
        else:
            self.connection.serial_connection.write(cmd_off.to_bytes(1, 'little'))
            expect = b'v'

        self.connection.expect(expect)

    def close(self) -> None:
        # Looks like this is not needed?
        # Calling _init_programming_vars does this and there is nothing to clean up
        pass

    def cycle_programming_voltages(self) -> None:
        cmd = 6
        self.connection.command_start(cmd)
        self.connection.expect(b'V', send_command_end=True)

    def program_rom(self, data: bytes) -> None:
        """Write data to ROM.  data should be a binary string of data, high byte first."""
        cmd = 7

        word_count = len(data) // 2
        rom_size = self.chip_info.rom_size
        if rom_size < word_count:
            raise InvalidValueError('Data too large for PIC ROM {} > {}.'.format(word_count, rom_size))

        if ((word_count * 2) % 32) != 0:
            raise InvalidValueError('ROM data must be a multiple of 32 bytes in size.')

        self.connection.command_start()
        self.set_programming_voltages_command(True)

        self.connection.serial_connection.write(cmd.to_bytes(1, 'little'))

        word_count_message = struct.pack('>H', word_count)
        self.connection.serial_connection.write(word_count_message)
        self.connection.expect(b'Y', timeout=20)

        try:
            for i in range(0, (word_count * 2), 32):
                to_write = data[i:(i + 32)]
                self.connection.serial_connection.write(to_write)
                self.connection.expect(b'Y', timeout=20)
            self.connection.expect(b'P', timeout=20)
        except InvalidResponseError:
            self.connection.serial_connection.flushInput()  # We don't get current address for now.
            raise

        self.set_programming_voltages_command(False)
        self.connection.command_end()

    def program_eeprom(self, data: bytes) -> None:
        """Write data to EEPROM.  Data size must be small enough to fit in EEPROM."""
        cmd = 8

        byte_count = len(data)
        if self.chip_info.eeprom_size < byte_count:
            raise InvalidValueError('Data too large for PIC EEPROM.')

        if (byte_count % 2) != 0:
            raise InvalidValueError('EEPROM data must be a multiple of 2 bytes in size.')

        self.connection.command_start()
        self.set_programming_voltages_command(True)
        self.connection.serial_connection.write(cmd.to_bytes(1, 'little'))

        byte_count_message = struct.pack('>H', byte_count)
        self.connection.serial_connection.write(byte_count_message)

        self.connection.expect(b'Y', timeout=20)
        for i in range(0, byte_count, 2):
            self.connection.serial_connection.write(data[i:(i + 2)])
            self.connection.expect(b'Y', timeout=20)
        # We must send an extra two bytes, which will have no effect.
        # Why?  I'm not sure.  See protocol doc, and read it backwards.
        # I'm sending zeros because if we did wind up back at the
        # command jump table, then the zeros will have no effect.
        self.connection.serial_connection.write(b'\x00\x00')
        self.connection.expect(b'P', timeout=20)

        self.set_programming_voltages_command(False)
        self.connection.command_end()

    def program_id_fuses(self, pic_id: bytes, fuses: List[int]) -> Optional[FuseTransaction]:
        """Program PIC ID and fuses.  For 16-bit processors, fuse values
        are not committed until program_18fxxxx_fuse() is called."""
        cmd = 9

        core_bits = self.chip_info.core_bits
        if core_bits == 16:
            if len(pic_id) != 8:
                raise InvalidValueError('Should have 8-byte ID for 16 bit core.')
            if len(fuses) != 7:
                raise InvalidValueError('Should have 7 fuses for 16 bit core.')
            command_body = b'00' + pic_id + struct.pack('<HHHHHHH', *fuses)
            response_ok = b'Y'
        else:
            if len(fuses) != 1:
                raise InvalidValueError('Should have one fuse for 14 bit core.')
            if len(pic_id) != 4:
                raise InvalidValueError('Should have 4-byte ID for 14 bit core.')
            # Command starts with dual '0' for 14 bit
            command_body = (b'00' + pic_id + b'FFFF' + struct.pack('<H', fuses[0]) + (b'\xff\xff' * 6))
            response_ok = b'Y'
        self.connection.command_start()
        self.set_programming_voltages_command(True)
        self.connection.serial_connection.write(cmd.to_bytes(1, 'little'))
        self.connection.serial_connection.write(command_body)

        response = self.connection.read(timeout=20)

        self.set_programming_voltages_command(False)
        self.connection.command_end()

        is_ok = response == response_ok
        if not is_ok:
            raise InvalidResponseError

        if core_bits == 16:
            # 16 requires program_18fxxxx_fuse to be called after to end transaction
            return FuseTransaction(self)

        return None

    def program_calibration(self, calibrate: int, fuse: int) -> None:
        """
        Program calibration
        Args:
            calibrate:
            fuse:

        Returns:

        """
        cmd = 10

        self.connection.command_start()
        self.set_programming_voltages_command(True)
        self.connection.serial_connection.write(cmd.to_bytes(1, 'little'))

        # Calibration High (Byte)
        # Calibration Low  (Byte)
        # FUSE High (Byte)
        # FUSE Low  (Byte)

        calibration = calibrate.to_bytes(2, 'big') + fuse.to_bytes(2, 'big')
        self.connection.serial_connection.write(calibration)

        response = self.connection.read(timeout=10)  # C= calibration fail, F = Fuse fail, Y = OK
        self.set_programming_voltages_command(False)
        self.connection.command_end()
        # response_ok = b'Y'
        if response != b'Y':
            raise InvalidResponseError

    def read_rom(self) -> bytes:
        """Returns contents of PIC ROM as a string of big-endian values."""
        cmd = 11

        # vars['rom_size'] is in words.  So multiply by two to get bytes.
        rom_size = self.chip_info.rom_size * 2

        self.connection.command_start()
        self.set_programming_voltages_command(True)
        self.connection.serial_connection.write(cmd.to_bytes(1, 'little'))

        response = self.connection.read(rom_size, timeout=180)
        self.set_programming_voltages_command(False)
        self.connection.command_end()
        return response

    def read_eeprom(self) -> bytes:
        """Returns data stored in PIC EEPROM."""
        cmd = 12

        eeprom_size = self.chip_info.eeprom_size

        self.connection.command_start()
        self.set_programming_voltages_command(True)
        self.connection.serial_connection.write(cmd.to_bytes(1, 'little'))
        response = self.connection.read(eeprom_size)
        self.set_programming_voltages_command(False)
        self.connection.command_end()
        return response

    def read_config(self) -> ChipConfig:
        """Reads chip ID and programmed ID, fuses, and calibration."""
        cmd = 13
        self.connection.command_start()
        self.set_programming_voltages_command(True)
        self.connection.serial_connection.write(cmd.to_bytes(1, 'little'))
        ack = self.connection.read(1)
        if ack != b'C':
            raise InvalidResponseError('No acknowledgement from read_config().')
        response = self.connection.read(26)
        self.set_programming_voltages_command(False)
        self.connection.command_end()

        return ChipConfig.from_bytes(response)

    def erase_chip(self) -> None:
        """Erases all data from chip."""
        cmd = 15

        self.connection.command_start()
        self.set_programming_voltages_command(True)
        self.connection.serial_connection.write(cmd.to_bytes(1, 'little'))
        response = self.connection.read(1)
        self.set_programming_voltages_command(False)
        self.connection.command_end()
        if response != b'Y':
            raise InvalidResponseError

    def rom_is_blank(self, high_byte: bytes) -> bool:
        """Returns True if PIC ROM is blank."""
        cmd = 16

        expected_b_bytes = (self.chip_info.rom_size // 256) - 1
        self.connection.command_start(cmd)
        self.connection.serial_connection.write(high_byte)
        while True:
            response = self.connection.read(1)
            if response == b'Y':
                self.connection.command_end()
                return True
            if response == b'N':
                self.connection.command_end()
                return False
            if response == b'C':
                self.connection.command_end()
                return False
            if response == b'B':
                if expected_b_bytes <= 0:
                    raise InvalidResponseError('Received wrong number of "B" bytes in rom_is_blank().')
            else:
                raise InvalidResponseError('Unexpected byte in rom_is_blank(): {!r}.'.format(response))

    def eeprom_is_blank(self) -> bool:
        """Returns True if PIC EEPROM is blank."""
        cmd = 17
        self.connection.command_start(cmd)
        response = self.connection.read(1)
        self.connection.command_end()
        if response not in [b'Y', b'N']:
            raise InvalidResponseError('Unexpected response in eeprom_is_blank(): {!r}.'.format(response))

        return response == b'Y'

    def program_debug_vector(self, address: bytes) -> None:
        """Sets the PIC's debugging vector."""
        cmd = 23

        be4_address = struct.pack('>I', address)
        self.connection.command_start(cmd)
        self.connection.serial_connection.write(be4_address[1:4])
        response = self.connection.read(1)
        self.connection.command_end()

        if response not in [b'Y', b'N']:
            raise InvalidResponseError('Unexpected response in program_debug_vector(): {!r}.'.format(response))

        if response != b'Y':
            raise InvalidResponseError

    def read_debug_vector(self) -> bytes:
        """Returns the value of the PIC's debugging vector."""
        cmd = 24

        self.connection.command_start(cmd)
        response = self.connection.read(4)
        be4_address = b'\x00' + response[1:4]
        result, = struct.unpack('>I', be4_address)
        self.connection.command_end()

        return result
