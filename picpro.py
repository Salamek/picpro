#!/usr/bin/python
"""The picpro module provides a simple program-level and command-line-level interface to the PIC programmers made by kitsrus.com.

This module is released under the GPL by its author.
This work would not have been possible without the programming protocol documentation kindly provided by kitsrus
as well as the assistance of people at kitsrus.com and in the community.
Send comments or bug reports related to this module to tetsujin@users.sf.net
"""

# There should never be a problem with the standard imports.  But...
try:
    import getopt
    import os.path
    import re
    import struct
    import sys
    import time
except ImportError:
    print("Failed to import standard Python libraries.  Please make sure your Python installation is complete and up-to-date.")
    sys.exit(1)

try:
    import serial
except ImportError:
    print("Unable to find Python Serial library.  Please download and install the serial library from http://www.sf.net/projects/pyserial")
    sys.exit(1)

from pic_k150_programmer.ChipInfoReader import ChipInfoReader
from pic_k150_programmer.HexFileReader import HexFileReader
from pic_k150_programmer.ProtocolInterface import ProtocolInterface
from pic_k150_programmer.exceptions import FuseError, InvalidResponseError
from pic_k150_programmer.tools import range_filter_records, swab_record, merge_records, hex_int

module_location = os.path.dirname(os.path.realpath(__file__)) + os.sep


def print_usage_and_abort():
    print(handle_command_line.__doc__)
    sys.exit(1)


def handle_command_line(cmd_args):
    # @TODO Rewrite this shit
    """micropro: program a PIC using the Kits R Us serial/USB PIC programmer.

Arguments:
    "-p x" (or "--port=x"): use serial port x
    "--pic_type=x": specify type of PIC to be programmed (use '16F84A',
                  not 'PIC16F84A')
    "-i file.hex" (or "--input=file.hex"): specify name of HEX file to use
    "--fuse=fuse_name:value": (optional) specify a value for a programming flag
    "--ID=PIC_id": (optional) specify ID to be programmed to PIC.
    "--program": (default) Program the PIC
    "--verify": Verify only, do not program
    "-h" (or "--help"): display this message"""

    try:
        opts, args = getopt.getopt(cmd_args[1:], 'p:i:h',
                                   ['port=', 'pic_type=', 'input=',
                                    'fuse=', 'ID=', 'help',
                                    'icsp', 'program', 'verify'])

        if not args:
            print_usage_and_abort()

        handle_parsed_command_line(opts)
    except getopt.GetoptError:
        print_usage_and_abort()


def handle_parsed_command_line(opts):
    fuses = {}
    pic_id = None
    port = None
    pic_type = None
    hex_file_name = None
    program_flag = False
    verify_flag = False
    icsp_mode = False

    for (opt, value) in opts:
        try:
            if (opt == '-h') or (opt == '--help'):
                print_usage_and_abort()
            elif (opt == '-p') or (opt == '--port'):
                port = value
            elif (opt == '-i') or (opt == '--input'):
                hex_file_name = value
            elif opt == '--pic_type':
                pic_type = value
            elif opt == '--fuse':
                split = value.split(':')
                fuses[split[0]] = split[1]
            elif opt == '--ID':
                pic_id = value
            elif opt == '--verify':
                verify_flag = True
            elif opt == '--program':
                program_flag = True
            elif opt == '--icsp':
                icsp_mode = True
            else:
                print('Error: Unrecognized option "{}".'.format(opt))
                sys.exit(1)
        except SystemExit:
            raise
        except Exception:
            print('Error: Invalid usage of option "{}".'.format(opt))
            print_usage_and_abort()

    program = (program_flag or not verify_flag)

    program_pic(port, pic_type, hex_file_name, program, fuses=fuses, pic_id=pic_id, icsp_mode=icsp_mode)


def program_pic(port, pic_type, hex_file_name='', program=True, fuses=None, pic_id=None, icsp_mode=False):
    """Given a serial port ID, PIC type, hex file name, and other optional
       data, attempt to program the hex file data to a PIC in the programmer."""
    try:
        s = serial.Serial(port=port, baudrate=19200,
                          bytesize=8, parity='N', stopbits=1,
                          timeout=10, xonxoff=0, rtscts=0)
    except serial.SerialException:
        print('Unable to open serial port "{}".'.format(port))
        print('Be sure port identifier is valid and that you have access to it.')
        return False

    # Get chip info
    chip_info_filename = module_location + 'chipinfo.cid'
    try:
        chip_info_reader = ChipInfoReader(chip_info_filename)
    except IOError:
        print('Unable to locate chipinfo.cid file.')
        print('Please verify that file is present in the same directory as this script, '
              'and that the filename is in lowercase characters, and that you have access to read the file.')
        return False

    try:
        chip_info = chip_info_reader.get_chip(pic_type)
    except KeyError:
        print('Unable to find chip type "{}" in data file.'.format(pic_type))
        print('Please check that the spelling is correct and that data file is up to date.')
        return False

    # Generate blank ROM and EEPROM of appropriate size.
    rom_blank_word = 0xffff << chip_info.get_core_bits()
    rom_blank_word = (~rom_blank_word & 0xffff)
    rom_blank_bytes = struct.pack('>H', rom_blank_word)
    rom_blank = rom_blank_bytes * chip_info.vars['rom_size']

    eeprom_blank_byte = '\xff'
    eeprom_blank = eeprom_blank_byte * chip_info.vars['eeprom_size']

    # Read hex file.
    try:
        hex_file = HexFileReader(hex_file_name)
    except IOError:
        print('Unable to find hex file "{}".'.format(hex_file_name))
        print('Please verify that the file exists and that you have access to it.')
        return False

    rom_word_base = 0x0000
    config_word_base = 0x4000
    eeprom_word_base = 0x4200
    rom_word_end = config_word_base
    config_word_end = 0x4010
    eeprom_word_end = 0xffff

    # Filter hex file data into ROM, config, and EEPROM:
    rom_records = range_filter_records(hex_file.records, rom_word_base, rom_word_end)

    config_records = range_filter_records(hex_file.records, config_word_base, config_word_end)

    eeprom_records = range_filter_records(hex_file.records, eeprom_word_base, eeprom_word_end)

    # Try to detect whether the ROM data is big-endian or
    # little-endian.  If it is little-endian, swap bytes.
    swap_bytes = None
    for record in rom_records:
        if record[0] % 2 != 0:
            raise ValueError('ROM record starts on odd address.')
        for x in range(0, len(record[1]), 2):
            if (x + 2) < len(record[1]):
                be_word, = struct.unpack('>H', record[1][x:x + 2])
                le_word, = struct.unpack('<H', record[1][x:x + 2])

                be_ok = ((be_word & rom_blank_word) == be_word)
                le_ok = ((le_word & rom_blank_word) == le_word)

                if be_ok and not le_ok:
                    swap_bytes = False
                    break
                elif le_ok and not be_ok:
                    swap_bytes = True
                    break
                elif not (le_ok or be_ok):
                    raise ValueError('Invalid ROM word: {}, ROMblank: {}'.format(hex(le_word), hex(rom_blank_word)))
        if swap_bytes is not None:
            break
    if swap_bytes:
        rom_records = map(swab_record, rom_records)
        config_records = map(swab_record, config_records)

    # EEPROM is stored in the hex file with one byte per word, so we
    # need to pick one of the two bytes out of each word to program.
    # If swap_bytes is true, then file is little-endian, and we want
    # the first byte of each EEPROM word.  Else we want the second.
    if swap_bytes:
        pick_byte = 0
    else:
        pick_byte = 1

    def _map_records(eeprom_record):
        return (
            (eeprom_word_base + ((eeprom_record[0] - eeprom_word_base) / 2)),
            (''.join([eeprom_record[1][record_index] for record_index in range(pick_byte, len(eeprom_record[1]), 2)]))
        )

    eeprom_records = map(_map_records, eeprom_records)

    # FINALLY!  We create the byte-level data...
    rom_data = merge_records(rom_records, rom_blank)
    eeprom_data = merge_records(eeprom_records, eeprom_blank, 0x4200)

    # Extract fuse data, pic_id data, etc. from fuse records
    if pic_id is not None:
        id_data = pic_id
    else:
        id_data = merge_records(
            range_filter_records(config_records, 0x4000, 0x4008),
            ('\x00' * 8))
        # If this is a 16-bit core, leave id_data as-is.  Else we need to
        # take every other byte according to endian-ness.
        if chip_info.get_core_bits() != 16:
            id_data = ''.join([id_data[x] for x in range(pick_byte, 8, 2)])

    # Pull fuse data from config records
    fuse_list = list(map(lambda word: struct.pack('>H', word).decode('ASCI'), chip_info.vars['FUSEblank']))  # @FIXME decode
    fuse_data = ''.join(fuse_list)
    fuse_data = merge_records(
        range_filter_records(
            config_records,
            0x400e,
            0x4010
        ),
        fuse_data,
        0x400e
    )

    # Go through each fuse listed in chip info.
    # Determine its current setting in fuse_value, and accumulate a new
    # fuse_value by incorporating values specified in (fuses).
    fuse_values = [hex_int(struct.unpack('>H', fuse_data[x:x + 2])[0]) for x in range(0, len(fuse_data), 2)]
    # for i in xrange(0, len(fuse_blank)):
    # fuse_value[i] = struct.unpack('>H', fuse_data[i*2, i*2+2])
    if fuses:
        fuse_settings = chip_info.decode_fuse_data(fuse_values)
        fuse_settings.update(fuses)
        try:
            fuse_values = chip_info.encode_fuse_data(fuse_settings)
        except FuseError:
            print('Invalid fuse setting.  Fuse names and valid settings for this chip are as follows:')
            print(chip_info.fuse_doc())
            return False

    try:
        # Perhaps now, at last, we can program some kind of a PIC.
        # Start up protocol interface
        prot_interface = ProtocolInterface(s)

        # Verify that communications are functioning
        response = prot_interface.echo(hex_file_name)
        if response != hex_file_name:
            print('Invalid response received from PIC programmer.')
            print('Please check that device is properly connected and working.')
    except InvalidResponseError:
        print('Unable to initialize connection to programmer.')
        print('Please check that device is properly connected and working.')
        return False

    # Initialize programming variables
    programming_vars = chip_info.get_programming_vars()
    if icsp_mode:
        power_sequence = programming_vars['power_sequence']
        if power_sequence == 2:
            power_sequence = 1
        elif power_sequence == 4:
            power_sequence = 3
        programming_vars['power_sequence'] = power_sequence

    prot_interface.init_programming_vars(**programming_vars)

    try:
        # Instruct user to insert chip
        if not icsp_mode:
            print('Waiting for user to insert chip into socket with pin 1 at {}'.format(chip_info.pin1_location_text()))
            prot_interface.wait_until_chip_in_socket()
            print('Chip detected.')
        else:
            print('Accessing chip connected to ICSP port.')

        # If write mode is active, program the ROM, EEPROM, ID and fuses.
        if program:
            # Write ROM, EEPROM, ID and fuses
            print('Erasing Chip')
            if not prot_interface.erase_chip():
                print('Erasure failed.')

            print('Programming ROM')
            if not prot_interface.program_rom(rom_data):
                print('ROM programming failed.')

            if chip_info.has_eeprom():
                print('Programming EEPROM')
            if not prot_interface.program_eeprom(eeprom_data):
                print('EEPROM programming failed.')

            print('Programming ID and fuses')
            if not prot_interface.program_id_fuses(id_data, fuse_values):
                print('Programming ID and fuses failed.')

        # Verify programmed data.
        # Behold, my godlike powers of verification:
        print('Verifying ROM')
        pic_rom_data = prot_interface.read_rom()
        verification_result = True

        if pic_rom_data == rom_data:
            print('ROM verified.')
        else:
            print('ROM verification failed.')
            verification_result = False

        if chip_info.has_eeprom():
            print('Verifying EEPROM')
            pic_eeprom_data = prot_interface.read_eeprom()
            if pic_eeprom_data == eeprom_data:
                print('EEPROM verified.')
            else:
                print('EEPROM verification failed.')
                verification_result = False

        if verification_result and (chip_info.get_core_bits() == 16):
            print('Committing 18Fxxxx fuse data.')
            prot_interface.program_18fxxxx_fuse()

    except InvalidResponseError:
        print('Error: Communication failure.  This may be a bug in this script or a problem with your programmer hardware.')
        return False

    return verification_result


# Ugh, as much as I hate having to put this in at all, I despise
# having to put it at the end...
if __name__ == '__main__':
    handle_command_line(sys.argv)
