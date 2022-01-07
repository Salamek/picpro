#!/usr/bin/python
"""Main entry-point into the 'pic_k150_programmer' CLI application.

The picpro3 provides a simple program-level and command-line-level interface to the PIC programmers made by kitsrus.com. (K150 and compatible)

License: GPL2
Website: https://gitlab.salamek.cz/sadam/pic_k150_programmer.git

Command details:
    program             Program PIC chip.
    verify              Verify PIC flash.

Usage:
    pic-k150-programmer program -p PORT -i HEX_FILE -t PIC_TYPE [--id=PIC_ID] [--fuse=FUSE_NAME:FUSE_VALUE...] [--icsp]
    pic-k150-programmer verify -p PORT -i HEX_FILE -t PIC_TYPE [--icsp]
    pic-k150-programmer (-h | --help)


Options:
    --icsp                           Enable ISCP programming.
    --fuse=FUSE_NAME:FUSE_VALUE      Set fuse value directly.
    --id=PIC_ID                      Set PIC id to be programmed in pic.
    -p PORT --port=PORT              Set serial port where programmer is connected.
    -t PIC_TYPE --pic_type=PIC_TYPE  Pic type you are programming/reading.
    -i HEX_FILE --hex_file=HEX_FILE  Hex file to flash or to read.
"""

import os.path
import struct
import sys
import signal
import serial
from functools import wraps
from docopt import docopt
from pic_k150_programmer.ChipInfoReader import ChipInfoReader
from pic_k150_programmer.HexFileReader import HexFileReader
from pic_k150_programmer.ProtocolInterface import ProtocolInterface
from pic_k150_programmer.HexInt import HexInt
from pic_k150_programmer.exceptions import FuseError, InvalidResponseError
from pic_k150_programmer.tools import range_filter_records, swab_record, merge_records

module_location = os.path.dirname(os.path.realpath(__file__)) + os.sep

OPTIONS = docopt(__doc__)


def command(name: str = None):
    """Decorator that registers the chosen command/function.

    If a function is decorated with @command but that function name is not a valid "command" according to the docstring,
    a KeyError will be raised, since that's a bug in this script.

    If a user doesn't specify a valid command in their command line arguments, the above docopt(__doc__) line will print
    a short summary and call sys.exit() and stop up there.

    If a user specifies a valid command, but for some reason the developer did not register it, an AttributeError will
    raise, since it is a bug in this script.

    Finally, if a user specifies a valid command and it is registered with @command below, then that command is "chosen"
    by this decorator function, and set as the attribute `chosen`. It is then executed below in
    `if __name__ == '__main__':`.

    Positional arguments:
    func -- the function to decorate
    """

    def function_wrap(func):

        @wraps(func)
        def wrapped():
            return func()

        command_name = name if name else func.__name__

        # Register chosen function.
        if command_name not in OPTIONS:
            raise KeyError('Cannot register {}, not mentioned in docstring/docopt.'.format(command_name))
        if OPTIONS[command_name]:
            command.chosen = func

        return wrapped

    return function_wrap


@command()
def program():
    fuses = {}
    for fuse_cmd in OPTIONS['--fuse']:
        fuse_name, fuse_value = fuse_cmd.split(':')
        fuses[fuse_name] = fuse_value

    program_pic(
        OPTIONS['--port'],
        OPTIONS['--pic_type'],
        OPTIONS['--hex_file'],
        True,
        fuses=fuses,
        pic_id=OPTIONS['--id'],
        icsp_mode=OPTIONS['--icsp']
    )


@command()
def verify():

    program_pic(
        OPTIONS['--port'],
        OPTIONS['--pic_type'],
        OPTIONS['--hex_file'],
        False,
        icsp_mode=OPTIONS['--icsp']
    )


def program_pic(port, pic_type, hex_file_name='', is_program=True, fuses=None, pic_id=None, icsp_mode=False):
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
    #chip_info_filename = module_location + 'chipinfo.cid'
    chip_info_filename = module_location + 'chipdata.cid'
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

    eeprom_blank_byte = b'\xff'
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
            (bytearray([eeprom_record[1][record_index] for record_index in range(pick_byte, len(eeprom_record[1]), 2)]))
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
            (b'\x00' * 8))
        # If this is a 16-bit core, leave id_data as-is.  Else we need to
        # take every other byte according to endian-ness.
        if chip_info.get_core_bits() != 16:
            id_data = bytearray([id_data[x] for x in range(pick_byte, 8, 2)])

    # Pull fuse data from config records
    fuse_data_list = list(map(lambda word: struct.pack('>H', word), chip_info.vars['FUSEblank']))
    fuse_data = b''.join(fuse_data_list)
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
    fuse_values = [HexInt(struct.unpack('>H', fuse_data[x:x + 2])[0]) for x in range(0, len(fuse_data), 2)]
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
        hex_file_name_encode = hex_file_name.encode('UTF-8')
        response = prot_interface.echo(hex_file_name_encode)
        if response != hex_file_name_encode:
            print('Invalid response received from PIC programmer. ({} != {})'.format(response, hex_file_name_encode))
            print('Please check that device is properly connected and working.')
            return False
    except InvalidResponseError as e:
        print('Unable to initialize connection to programmer. {}'.format(e))
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

    #print('Programmer version is: {}'.format(prot_interface.programmer_firmware_version()))

    try:
        # Instruct user to insert chip
        if not icsp_mode:
            print('Waiting for user to insert chip into socket with pin 1 at {}'.format(chip_info.pin1_location_text()))
            prot_interface.wait_until_chip_in_socket()
            print('Chip detected.')
        else:
            print('Accessing chip connected to ICSP port.')

        """
        chip_config = prot_interface.read_config()
        print('Chip config: {}'.format(chip_config))

        prot_interface._set_programming_voltages_command(True)
        if not prot_interface.rom_is_blank(0x3F):
            print('ROM is EMPTY')
        else:
            print('ROM IS NOT EMPTY')
        prot_interface.cycle_programming_voltages()
        prot_interface._set_programming_voltages_command(False)
        """

        # If write mode is active, program the ROM, EEPROM, ID and fuses.
        if is_program:
            # Write ROM, EEPROM, ID and fuses

            print('Erasing Chip')
            if not prot_interface.erase_chip():
                print('Erasure failed.')
                return False

            prot_interface.cycle_programming_voltages()

            print('Programming ROM')
            if not prot_interface.program_rom(rom_data):
                print('ROM programming failed.')
                return False

            if chip_info.has_eeprom():
                print('Programming EEPROM')
                if not prot_interface.program_eeprom(eeprom_data):
                    print('EEPROM programming failed.')
                    return False

            print('Programming ID and fuses')
            if not prot_interface.program_id_fuses(id_data, fuse_values):
                print('Programming ID and fuses failed.')
                return False

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
                print('{} {} ({})'.format(pic_eeprom_data, eeprom_data, len(eeprom_data)))
                print('EEPROM verification failed.')
                verification_result = False

        if verification_result and (chip_info.get_core_bits() == 16):
            print('Committing 18Fxxxx fuse data.')
            prot_interface.program_18fxxxx_fuse()

    except InvalidResponseError as e:
        print('Error: Communication failure.  This may be a bug in this script or a problem with your programmer hardware. ({})'.format(e))
        return False

    return verification_result


def main():
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))  # Properly handle Control+C
    getattr(command, 'chosen')()  # Execute the function specified by the user.


if __name__ == '__main__':
    main()

