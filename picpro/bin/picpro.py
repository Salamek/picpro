#!/usr/bin/python
"""Main entry-point into the 'pic_k150_programmer' CLI application.

The picpro3 provides a simple program-level and command-line-level interface to the PIC programmers made by kitsrus.com. (K150 and compatible)

License: GPL2
Website: https://gitlab.salamek.cz/sadam/pic_k150_programmer.git

Command details:
    program             Program PIC chip.
    verify              Verify PIC flash.
    dump                Dump PIC data as binary.
    chipinfo            Prints chipinfo as JSON in terminal.

Usage:
    picpro program -p PORT -i HEX_FILE -t PIC_TYPE [--id=PIC_ID] [--fuse=FUSE_NAME:FUSE_VALUE...] [--icsp]
    picpro verify -p PORT -i HEX_FILE -t PIC_TYPE [--icsp]
    picpro dump <mem_type> -p PORT -o HEX_FILE -t PIC_TYPE [--icsp]
    picpro chipinfo [<PIC_TYPE>]
    picpro (-h | --help)


Options:
    --icsp                           Enable ISCP programming.
    --fuse=FUSE_NAME:FUSE_VALUE      Set fuse value directly.
    --id=PIC_ID                      Set PIC id to be programmed in pic.
    -p PORT --port=PORT              Set serial port where programmer is connected.
    -t PIC_TYPE --pic_type=PIC_TYPE  Pic type you are programming/reading.
    -i HEX_FILE --hex_file=HEX_FILE  Hex file to flash or to read.
    -o HEX_FILE --hex_file=HEX_FILE  Hex file to write.
"""

import os.path
import struct
import sys
import signal
import json
from functools import wraps
from typing import Union, Optional, Callable, Tuple
import serial
from intelhex import IntelHex
from docopt import docopt
from picpro.ChipInfoReader import ChipInfoReader
from picpro.IChipInfoEntry import IChipInfoEntry
from picpro.HexFileReader import HexFileReader
from picpro.ProtocolInterface import ProtocolInterface
from picpro.exceptions import FuseError, InvalidResponseError
from picpro.tools import range_filter_records, swab_record, merge_records, swab_bytes
import picpro as app_root

APP_ROOT_FOLDER = os.path.abspath(os.path.dirname(app_root.__file__))

OPTIONS = docopt(__doc__)


def command(name: Optional[str] = None) -> Callable:
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

    def function_wrap(func: Callable) -> Callable:

        @wraps(func)
        def wrapped() -> Callable:
            return func()

        command_name = name if name else func.__name__

        # Register chosen function.
        if command_name not in OPTIONS:
            raise KeyError('Cannot register {}, not mentioned in docstring/docopt.'.format(command_name))
        if OPTIONS[command_name]:
            command.chosen = func  # type: ignore

        return wrapped

    return function_wrap


@command()
def program() -> None:
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
def verify() -> None:
    program_pic(
        OPTIONS['--port'],
        OPTIONS['--pic_type'],
        OPTIONS['--hex_file'],
        False,
        icsp_mode=OPTIONS['--icsp']
    )


@command()
def dump() -> None:
    programmer_common_data = programmer_common_bootstrap(
        OPTIONS['--port'],
        OPTIONS['--pic_type'],
        icsp_mode=OPTIONS['--icsp']
    )

    if not programmer_common_data:
        return

    _, protocol_interface = programmer_common_data

    mem_type = OPTIONS['<mem_type>']
    output_file = OPTIONS['--hex_file']

    if mem_type == 'eeprom':
        print('Reading EEPROM into file {}...'.format(output_file))
        content = swab_bytes(protocol_interface.read_eeprom())
    elif mem_type == 'rom':
        print('Reading ROM into file {}...'.format(output_file))
        content = swab_bytes(protocol_interface.read_rom())
    elif mem_type == 'config':
        print('Reading CONFIG into file {}...'.format(output_file))
        content = protocol_interface.read_config()
        print(content)
        return
    else:
        raise ValueError('Unknown memory type')

    intel_hex = IntelHex()
    intel_hex.frombytes(content)

    with open(output_file, 'w') as file:
        intel_hex.write_hex_file(file)


@command()
def chipinfo() -> None:
    pic_type = OPTIONS['<PIC_TYPE>']
    # Get chip info
    chip_info_filename = find_chip_data()
    chip_info_reader = ChipInfoReader(chip_info_filename)

    if pic_type:
        data = chip_info_reader.get_chip(pic_type).to_dict()
    else:
        data = {chip_name: entry.to_dict() for chip_name, entry in chip_info_reader.chip_entries.items()}

    print(json.dumps(data))


def find_chip_data() -> str:
    chip_data_files = [f for f in [
        os.path.join('/', 'usr', 'share', 'picpro', 'chipdata.cid'),
        os.path.abspath(os.path.join(APP_ROOT_FOLDER, '..', 'usr', 'share', 'picpro', 'chipdata.cid')),
        os.path.abspath(os.path.join(APP_ROOT_FOLDER, '..', 'usr', 'lib', 'picpro', 'chipdata.cid')),  # Legacy search path
        os.path.abspath(os.path.join(APP_ROOT_FOLDER, '..', 'lib', 'picpro', 'chipdata.cid')),  # Legacy search path
        os.path.join(APP_ROOT_FOLDER, 'chipdata.cid'),
    ] if os.path.exists(f)]

    if len(chip_data_files) == 0:
        raise ValueError('chipdata.cid was not found in any search path')

    return chip_data_files[0]


def programmer_common_bootstrap(port: str, pic_type: str, icsp_mode: bool) -> Union[None, tuple]:
    """Given a serial port ID, PIC type, hex file name, and other optional
           data, attempt to program the hex file data to a PIC in the programmer."""
    try:
        s = serial.Serial(port=port, baudrate=19200,
                          bytesize=8, parity='N', stopbits=1,
                          timeout=10, xonxoff=0, rtscts=0)
    except serial.SerialException:
        print('Unable to open serial port "{}".'.format(port))
        print('Be sure port identifier is valid and that you have access to it.')
        return None

    try:
        # Perhaps now, at last, we can program some kind of a PIC.
        # Start up protocol interface
        protocol_interface = ProtocolInterface(s)

        # Verify that communications are functioning
        hex_file_name_encode = b'Hello programmer!'
        response = protocol_interface.echo(hex_file_name_encode)
        if response != hex_file_name_encode:
            print('Invalid response received from PIC programmer. ({!r} != {!r})'.format(response, hex_file_name_encode))
            print('Please check that device is properly connected and working.')
            return None
    except InvalidResponseError as e:
        print('Unable to initialize connection to programmer. {}'.format(e))
        print('Please check that device is properly connected and working.')
        return None

    # Get chip info
    chip_info_filename = find_chip_data()
    try:
        chip_info_reader = ChipInfoReader(chip_info_filename)
    except IOError:
        print('Unable to locate chipinfo.cid file.')
        print('Please verify that file is present in the same directory as this script, '
              'and that the filename is in lowercase characters, and that you have access to read the file.')
        return None

    try:
        chip_info = chip_info_reader.get_chip(pic_type)
    except KeyError:
        print('Unable to find chip type "{}" in data file.'.format(pic_type))
        print('Please check that the spelling is correct and that data file is up to date.')
        return None

    # Initialize programming variables
    protocol_interface.init_programming_vars(chip_info, icsp_mode=icsp_mode)

    # Instruct user to insert chip
    if not icsp_mode:
        print('Waiting for user to insert chip into socket with pin 1 at {}'.format(chip_info.pin1_location_text()))
        protocol_interface.wait_until_chip_in_socket()
        print('Chip detected.')
    else:
        print('Accessing chip connected to ICSP port.')

    return chip_info, protocol_interface


def prepare_flash_data_from_hex_file(chip_info: IChipInfoEntry, hex_file: HexFileReader, pic_id: Optional[str] = None, fuses: Optional[dict] = None) -> tuple:
    # Generate blank ROM and EEPROM of appropriate size.
    core_bits = chip_info.get_core_bits()
    if not core_bits:
        raise ValueError('Failed to detect core bits')
    rom_blank_word = 0xffff << core_bits
    rom_blank_word = (~rom_blank_word & 0xffff)
    rom_blank_bytes = struct.pack('>H', rom_blank_word)
    rom_blank = rom_blank_bytes * chip_info.programming_vars.rom_size

    eeprom_blank_byte = b'\xff'
    eeprom_blank = eeprom_blank_byte * chip_info.programming_vars.eeprom_size

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
                if le_ok and not be_ok:
                    swap_bytes = True
                    break
                if not (le_ok or be_ok):
                    raise ValueError('Invalid ROM word: {}, ROM blank: {}'.format(hex(le_word), hex(rom_blank_word)))
        if swap_bytes is not None:
            break

    if swap_bytes:
        rom_records = [*map(swab_record, rom_records)]
        config_records = [*map(swab_record, config_records)]

    # EEPROM is stored in the hex file with one byte per word, so we
    # need to pick one of the two bytes out of each word to program.
    # If swap_bytes is true, then file is little-endian, and we want
    # the first byte of each EEPROM word.  Else we want the second.
    if swap_bytes:
        pick_byte = 0
    else:
        pick_byte = 1

    def _map_records(eeprom_record: Tuple[int, bytearray]) -> Tuple[int, bytearray]:
        return (
            int(eeprom_word_base + ((eeprom_record[0] - eeprom_word_base) / 2)),
            (bytearray([eeprom_record[1][record_index] for record_index in range(pick_byte, len(eeprom_record[1]), 2)]))
        )

    eeprom_records = [*map(_map_records, eeprom_records)]

    # FINALLY!  We create the byte-level data...
    rom_data = merge_records(rom_records, rom_blank)
    eeprom_data = merge_records(eeprom_records, eeprom_blank, 0x4200)

    # Extract fuse data, pic_id data, etc. from fuse records
    if pic_id is not None:
        id_data = pic_id.encode('UTF-8')
    else:
        id_data_raw = range_filter_records(config_records, 0x4000, 0x4008)
        id_data = merge_records(id_data_raw, (b'\x00' * 8), 0x4000)
        # If this is a 16-bit core, leave id_data as-is.  Else we need to
        # take every other byte according to endian-ness.
        # Config records are already converted to little-endian, so we set
        # range(pick_byte, 8, 2) to range(1, 8, 2)
        if core_bits != 16:
            id_data = bytearray([id_data[x] for x in range(1, 8, 2)])

    # Pull fuse data from config records
    fuse_data_blank = b''.join(map(lambda word: struct.pack('>H', word), chip_info.programming_vars.fuse_blank))
    fuse_config = range_filter_records(
        config_records,
        0x400e,
        0x4010
    )

    fuse_data = merge_records(
        fuse_config,
        fuse_data_blank,
        0x400e
    )

    # Go through each fuse listed in chip info.
    # Determine its current setting in fuse_value, and accumulate a new
    # fuse_value by incorporating values specified in (fuses).
    fuse_values = [int(struct.unpack('>H', fuse_data[x:x + 2])[0]) for x in range(0, len(fuse_data), 2)]
    # for i in xrange(0, len(fuse_blank)):
    # fuse_value[i] = struct.unpack('>H', fuse_data[i*2, i*2+2])
    if fuses:
        fuse_settings = chip_info.decode_fuse_data(fuse_values)
        fuse_settings.update(fuses)
        fuse_values = chip_info.encode_fuse_data(fuse_settings)

    return rom_data, eeprom_data, id_data, fuse_values


def program_pic(
        port: str,
        pic_type: str,
        hex_file_name: str,
        is_program: bool = True,
        fuses: Optional[dict] = None,
        pic_id: Optional[str] = None,
        icsp_mode: bool = False
) -> bool:
    """Given a serial port ID, PIC type, hex file name, and other optional
       data, attempt to program the hex file data to a PIC in the programmer."""

    common_bootstrap_result = programmer_common_bootstrap(port, pic_type, icsp_mode)
    if not common_bootstrap_result:
        return False

    chip_info, protocol_interface = common_bootstrap_result

    # Read hex file.
    try:
        hex_file = HexFileReader(hex_file_name)
    except IOError:
        print('Unable to find hex file "{}".'.format(hex_file_name))
        print('Please verify that the file exists and that you have access to it.')
        return False

    try:
        rom_data, eeprom_data, id_data, fuse_values = prepare_flash_data_from_hex_file(chip_info, hex_file, pic_id, fuses)
    except FuseError:
        print('Invalid fuse setting.  Fuse names and valid settings for this chip are as follows:')
        print(chip_info.fuse_doc())
        return False

    try:
        # If write mode is active, program the ROM, EEPROM, ID and fuses.
        chip_config = protocol_interface.read_config()
        if is_program:
            # Write ROM, EEPROM, ID and fuses
            print('Erasing Chip')
            if not protocol_interface.erase_chip():
                print('Erasure failed.')
                return False

            protocol_interface.cycle_programming_voltages()

            print('Programming ROM')
            if not protocol_interface.program_rom(rom_data):
                print('ROM programming failed.')
                return False

            if chip_info.has_eeprom():
                print('Programming EEPROM')
                if not protocol_interface.program_eeprom(eeprom_data):
                    print('EEPROM programming failed.')
                    return False

            print('Programming ID and fuses')
            if not protocol_interface.program_id_fuses(id_data, fuse_values):
                print('Programming ID and fuses failed.')
                return False

            print('Programming CAL and fuses')
            response = protocol_interface.program_calibration(chip_config.get('calibrate'), fuse_values[0])
            if response == 'C':
                print('Programming CAL failed.')
                return False

        # Verify programmed data.
        # Behold, my godlike powers of verification:
        print('Verifying ROM')
        pic_rom_data = protocol_interface.read_rom()
        verification_result = True

        if chip_info.programming_vars.flag_calibration_value_in_rom:
            # Some chips have cal data put on last two bytes of ROM dump
            rom_data = rom_data[:len(rom_data) - 2] + chip_config.get('calibrate').to_bytes(2, 'big')

        if pic_rom_data == rom_data:
            print('ROM verified.')
        else:
            print('{} {}'.format(pic_rom_data[-1], pic_rom_data[-2]))
            print('{} {}'.format(rom_data[-1], rom_data[-2]))
            print('ROM verification failed.')
            verification_result = False

        if chip_info.has_eeprom():
            print('Verifying EEPROM')
            pic_eeprom_data = protocol_interface.read_eeprom()
            if pic_eeprom_data == eeprom_data:
                print('EEPROM verified.')
            else:
                print('{} {} ({})'.format(pic_eeprom_data, eeprom_data, len(eeprom_data)))
                print('EEPROM verification failed.')
                verification_result = False

        if verification_result and (chip_info.get_core_bits() == 16):
            print('Committing 18Fxxxx fuse data.')
            protocol_interface.program_18fxxxx_fuse()

    except InvalidResponseError as e:
        print('Error: Communication failure.  This may be a bug in this script or a problem with your programmer hardware. ({})'.format(e))
        return False

    return verification_result


def main() -> None:
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))  # Properly handle Control+C
    getattr(command, 'chosen')()  # Execute the function specified by the user.


if __name__ == '__main__':
    main()
