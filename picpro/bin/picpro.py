#!/usr/bin/python
"""Main entry-point into the 'pic_k150_programmer' CLI application.

The picpro3 provides a simple program-level and command-line-level interface to the PIC programmers made by kitsrus.com. (K150 and compatible)

License: GPL2
Website: https://gitlab.salamek.cz/sadam/pic_k150_programmer.git

Command details:
    program             Program PIC chip.
    verify              Verify PIC flash.
    dump                Dump PIC data as binary.
    erase               Erase PIC.
    chip_info           Prints chip info as JSON in terminal.
    hex_info            Prints information about hexfile.
    programmer_info     Print information about your programmer.
    read_chip_config    Read config from chip.

Usage:
    picpro program -p PORT -i HEX_FILE -t PIC_TYPE [--id=PIC_ID] [--fuse=FUSE_NAME:FUSE_VALUE...] [--icsp]
    picpro verify -p PORT -i HEX_FILE -t PIC_TYPE [--icsp]
    picpro erase -p PORT -t PIC_TYPE [--icsp]
    picpro dump <mem_type> -p PORT -o HEX_FILE -t PIC_TYPE [--icsp] [--binary]
    picpro chip_info [<PIC_TYPE>]
    picpro read_chip_config -p PORT -t PIC_TYPE [--icsp]
    picpro hex_info <HEX_FILE> <PIC_TYPE>
    picpro programmer_info -p PORT
    picpro decode_fuses <fuses> -t PIC_TYPE
    picpro (-h | --help)


Options:
    --icsp                           Enable ISCP programming.
    --fuse=FUSE_NAME:FUSE_VALUE      Set fuse value directly.
    --id=PIC_ID                      Set PIC id to be programmed in pic HEX format.
    -p PORT --port=PORT              Set serial port where programmer is connected.
    -t PIC_TYPE --pic_type=PIC_TYPE  Pic type you are programming/reading.
    -i HEX_FILE --hex_file=HEX_FILE  Hex file to flash or to read.
    -o HEX_FILE --hex_file=HEX_FILE  Hex file to write.
    --binary                         Input/Output file is in binary.
"""

import os.path
import sys
import signal
import json
from functools import wraps
from typing import Optional, Callable
from pathlib import Path

from intelhex import IntelHex
from docopt import docopt
from picpro.ChipInfoReader import ChipInfoReader
from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.FlashData import FlashData
from picpro.HexFileReader import HexFileReader
from picpro.exceptions import FuseError, InvalidResponseError
from picpro.protocol.ChipConfig import ChipConfig
from picpro.protocol.IProgrammingInterface import IProgrammingInterface
from picpro.tools import swab_bytes
from picpro.protocol.p18a.Connection import Connection
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


def _find_chip_data() -> Path:
    path_list = [
        os.path.join('/', 'usr', 'share', 'picpro', 'chipdata.cid'),
        os.path.abspath(os.path.join(APP_ROOT_FOLDER, '..', 'usr', 'share', 'picpro', 'chipdata.cid')),
        os.path.abspath(os.path.join(APP_ROOT_FOLDER, '..', 'usr', 'lib', 'picpro', 'chipdata.cid')),  # Legacy search path
        os.path.abspath(os.path.join(APP_ROOT_FOLDER, '..', 'lib', 'picpro', 'chipdata.cid')),  # Legacy search path
        os.path.join(APP_ROOT_FOLDER, 'chipdata.cid')
    ]

    if os.name == 'nt':
        local_app_data = os.getenv('LOCALAPPDATA')
        if local_app_data:
            # windows path
            path_list.append(os.path.abspath(os.path.join(local_app_data, 'picpro', 'chipdata.cid')))

    chip_data_files = [f for f in path_list if os.path.exists(f)]

    if len(chip_data_files) == 0:
        raise ValueError("File 'chipdata.cid' was not found in any search path.")

    return Path(chip_data_files[0])


def _verify_pipeline(
        programming_interface: IProgrammingInterface,
        chip_info_entry: ChipInfoEntry,
        flash_data: FlashData
) -> bool:
    # Verify programmed data.
    # Behold, my godlike powers of verification:
    print('Verifying ROM.')
    pic_rom_data = programming_interface.read_rom()
    verification_result = True

    if pic_rom_data == flash_data.rom_data:
        print('ROM verified.')
    else:
        no_of_zeros = pic_rom_data.count(b'\x00')
        pic_rom_data_len = len(pic_rom_data)
        if chip_info_entry.cal_word:
            is_maybe_locked = pic_rom_data_len - 2 == no_of_zeros
        else:
            is_maybe_locked = pic_rom_data_len == no_of_zeros

        print('ROM verification failed.')
        if is_maybe_locked:
            print('Maybe ROM is locked for reading?')
        verification_result = False

    if chip_info_entry.has_eeprom:
        print('Verifying EEPROM.')
        pic_eeprom_data = programming_interface.read_eeprom()
        if pic_eeprom_data == flash_data.eeprom_data:
            print('EEPROM verified.')
        else:
            print('{} {} ({})'.format(pic_eeprom_data.hex(), flash_data.eeprom_data.hex(), len(flash_data.eeprom_data)))
            print('EEPROM verification failed.')
            verification_result = False

    return verification_result


def _print_chip_config(chip_config: ChipConfig, chip_info_entry: ChipInfoEntry) -> None:
    print('Chip ID: {} ({})'.format(chip_config.chip_id, hex(chip_config.chip_id)))
    print('ID:      {}'.format(chip_config.id.hex()))
    print('CAL:     {}'.format(chip_config.calibrate))
    print('Fuses:')
    for name, value in chip_info_entry.decode_fuse_data(chip_config.fuses).items():
        print('    {} = {}'.format(name, value))

@command()
def program() -> None:
    fuses = {}
    for fuse_cmd in OPTIONS['--fuse']:
        fuse_name, fuse_value = fuse_cmd.split(':')
        fuses[fuse_name] = fuse_value

    hex_file = Path(OPTIONS['--hex_file'])
    try:
        hex_file_reader = HexFileReader(hex_file)
        chip_info_reader = ChipInfoReader(_find_chip_data())
        chip_info_entry = chip_info_reader.get_chip(OPTIONS['--pic_type'])
        try:
            flash_data = FlashData(chip_info_entry, hex_file_reader, fuses=fuses, pic_id=OPTIONS['--id'])
            print('Opening connection to programmer...')
            with Connection(OPTIONS['--port']) as connection:
                print('Initializing programming interface...')
                with connection.get_programming_interface(
                        chip_info_entry,
                        icsp_mode=OPTIONS['--icsp']
                ) as programming_interface:
                    chip_config = programming_interface.read_config()
                    print('==== Chip info ====')
                    _print_chip_config(chip_config, chip_info_entry)
                    if chip_info_entry.cal_word:
                        # Some chips have cal data put on last two bytes of ROM dump
                        print('CAL is in ROM data, patching ROM to contain the same CAL data...')
                        flash_data.set_calibration_word(chip_config.calibrate.to_bytes(2, 'big'))

                    # Write ROM, EEPROM, ID and fuses
                    if chip_info_entry.flash_chip:
                        print('Erasing chip.')
                        programming_interface.erase_chip()
                        print('Done!')
                    else:
                        print('This chip is not erasable.')

                    programming_interface.cycle_programming_voltages()

                    print('Programming ROM.')
                    programming_interface.program_rom(flash_data.rom_data)

                    if chip_info_entry.has_eeprom:
                        print('Programming EEPROM.')
                        programming_interface.program_eeprom(flash_data.eeprom_data)

                    print('Programming ID and fuses.')
                    fuse_transaction = programming_interface.program_id_fuses(flash_data.id_data, flash_data.fuse_data)

                    _verify_pipeline(programming_interface, chip_info_entry, flash_data)
                    if fuse_transaction:
                        print('Committing 18Fxxxx fuse data.')
                        fuse_transaction.program_18fxxxx_fuse(flash_data.fuse_data)
                    print('Done!')
        except FuseError:
            print('Invalid fuse setting. Fuse names and valid settings for this chip are as follows:')
            print(chip_info_entry.fuse_doc)
    except IOError:
        print('Unable to locate chipinfo.cid file.')
        print('Please verify that file is present in the same directory as this script, '
              'and that the filename is in lowercase characters, and that you have access to read the file.')


@command()
def verify() -> None:
    hex_file = Path(OPTIONS['--hex_file'])
    try:
        hex_file_reader = HexFileReader(hex_file)
        chip_info_reader = ChipInfoReader(_find_chip_data())
        chip_info_entry = chip_info_reader.get_chip(OPTIONS['--pic_type'])
        flash_data = FlashData(chip_info_entry, hex_file_reader)
        print('Opening connection to programmer...')
        with Connection(OPTIONS['--port']) as connection:
            print('Initializing programming interface...')
            with connection.get_programming_interface(chip_info_entry, icsp_mode=OPTIONS['--icsp']) as programming_interface:
                chip_config = programming_interface.read_config()
                print('Chip config: {}'.format(chip_config))
                if chip_info_entry.cal_word:
                    # Some chips have cal data put on last two bytes of ROM dump
                    print('CAL is in ROM data, patching ROM to contain the same CAL data...')
                    flash_data.set_calibration_word(chip_config.calibrate.to_bytes(2, 'big'))

                _verify_pipeline(programming_interface, chip_info_entry, flash_data)
                print('Done!')
    except IOError:
        print('Unable to locate chipinfo.cid file.')
        print('Please verify that file is present in the same directory as this script, '
              'and that the filename is in lowercase characters, and that you have access to read the file.')


@command()
def dump() -> None:
    mem_type = OPTIONS['<mem_type>']
    output_file = OPTIONS['--hex_file']
    try:
        chip_info_reader = ChipInfoReader(_find_chip_data())
        chip_info_entry = chip_info_reader.get_chip(OPTIONS['--pic_type'])
        print('Opening connection to programmer...')
        with Connection(OPTIONS['--port']) as connection:
            print('Initializing programming interface...')
            with connection.get_programming_interface(chip_info_entry) as programming_interface:
                if mem_type == 'eeprom':
                    if not chip_info_entry.has_eeprom:
                        print('This chip has no EEPROM!')
                        return
                    print('Reading EEPROM into file {}...'.format(output_file))
                    content = swab_bytes(programming_interface.read_eeprom())
                elif mem_type == 'rom':
                    print('Reading ROM into file {}...'.format(output_file))
                    content = swab_bytes(programming_interface.read_rom())
                elif mem_type == 'config':
                    print('Reading CONFIG into file {}...'.format(output_file))
                    content = programming_interface.read_config().to_bytes()
                else:
                    raise ValueError('Unknown memory type.')

                if OPTIONS['--binary']:
                    # Binary dump requested
                    with open(output_file, 'wb') as binary_file:
                        binary_file.write(content)
                else:
                    intel_hex = IntelHex()
                    intel_hex.frombytes(content)

                    with open(output_file, 'w', encoding='ascii') as file:
                        intel_hex.write_hex_file(file)
                print('Done!')
    except IOError:
        print('Unable to locate chipinfo.cid file.')
        print('Please verify that file is present in the same directory as this script, '
              'and that the filename is in lowercase characters, and that you have access to read the file.')


@command()
def erase() -> None:
    try:
        chip_info_reader = ChipInfoReader(_find_chip_data())
        chip_info_entry = chip_info_reader.get_chip(OPTIONS['--pic_type'])
        print('Opening connection to programmer...')
        with Connection(OPTIONS['--port']) as connection:
            print('Initializing programming interface...')
            with connection.get_programming_interface(chip_info_entry) as programming_interface:
                print('Erasing chip...')
                programming_interface.erase_chip()
                print('Done!')
    except IOError:
        print('Unable to locate chipinfo.cid file.')
        print('Please verify that file is present in the same directory as this script, '
              'and that the filename is in lowercase characters, and that you have access to read the file.')


@command()
def chip_info() -> None:
    pic_type = OPTIONS['<PIC_TYPE>']
    # Get chip info
    chip_info_filename = _find_chip_data()
    chip_info_reader = ChipInfoReader(chip_info_filename)

    if pic_type:
        data = chip_info_reader.get_chip(pic_type).to_dict()
    else:
        data = {chip_name: entry.to_dict() for chip_name, entry in chip_info_reader.chip_entries.items()}

    print(json.dumps(data))


@command()
def hex_info() -> None:
    pic_type = OPTIONS['<PIC_TYPE>']
    hex_file_name = Path(OPTIONS['<HEX_FILE>'])

    # Read hex file.
    try:
        hex_file = HexFileReader(hex_file_name)
    except IOError:
        print('Unable to find hex file "{}".'.format(hex_file_name))
        print('Please verify that the file exists and that you have access to it.')
        return None

    # Get chip info
    try:
        chip_info_reader = ChipInfoReader(_find_chip_data())
    except IOError:
        print('Unable to locate chipinfo.cid file.')
        print('Please verify that file is present in the same directory as this script, '
              'and that the filename is in lowercase characters, and that you have access to read the file.')
        return None

    try:
        chip_info_entry = chip_info_reader.get_chip(pic_type)
    except KeyError:
        print('Unable to find chip type "{}" in data file.'.format(pic_type))
        print('Please check that the spelling is correct, and that data file is up-to-date.')
        return None

    try:
        flash_data = FlashData(chip_info_entry, hex_file)
    except FuseError:
        print('Invalid fuse setting. Fuse names and valid settings for this chip are as follows:')
        print(chip_info_entry.fuse_doc)
        return None

    word_count_rom = len(flash_data.rom_data) // 2
    word_count_eeprom = len(flash_data.eeprom_data) // 2
    print('ROM {} words used, {} words free on chip.'.format(word_count_rom, chip_info_entry.rom_size - word_count_rom))
    print('EEPROM {} words used, {} words free on chip.'.format(word_count_eeprom, chip_info_entry.eeprom_size - word_count_eeprom))

    indent_char = '  '
    in_list_char = '- '
    intel_hex = IntelHex(hex_file_name)
    if intel_hex.start_addr:
        keys = sorted(intel_hex.start_addr.keys())
        if keys == ['CS', 'IP']:
            entry = intel_hex.start_addr['CS'] * 16 + intel_hex.start_addr['IP']
        elif keys == ['EIP']:
            entry = intel_hex.start_addr['EIP']
        else:
            raise RuntimeError("Unknown 'IntelHex.start_addr' found.")
        print("{:s}entry: 0x{:08X}".format(indent_char, entry))
    segments = intel_hex.segments()
    if segments:
        print("{:s}data:".format(indent_char))
        for s in segments:
            print("{:s}{:s}{{ first: 0x{:08X}, last: 0x{:08X}, length: 0x{:08X} }}".format(indent_char, in_list_char, s[0], s[1] - 1, s[1] - s[0]))
    print("")

    #if self.chip_info.programming_vars.rom_size < word_count:  # type: ignore
    #    raise InvalidValueError('Data too large for PIC ROM {} > {}.'.format(word_count, chip_info.programming_vars.rom_size))
    return None

@command()
def programmer_info() -> None:
    port = OPTIONS['--port']
    try:
        with Connection(port) as connection:
            print('Firmware version: {}'.format(connection.programmer_version().decode('UTF-8')))
            print('Protocol version: {}'.format(connection.programmer_protocol().decode('UTF-8')))
    except ConnectionError:
        print('Unable to open serial port "{}".'.format(port))
        print('Be sure port identifier is valid and that you have access to it.')
    except InvalidResponseError as e:
        print('Unable to initialize connection to programmer. {}'.format(e))
        print('Please check that device is properly connected and working.')

@command()
def decode_fuses() -> None:
    pic_type = OPTIONS['--pic_type']
    fuses = [int (f) for f in OPTIONS['<fuses>'].split()]
    # Get chip info
    chip_info_filename = _find_chip_data()
    chip_info_reader = ChipInfoReader(chip_info_filename)

    chip_info_entry = chip_info_reader.get_chip(pic_type)
    print(chip_info_entry.decode_fuse_data(fuses))


@command()
def read_chip_config() -> None:
    try:
        chip_info_reader = ChipInfoReader(_find_chip_data())
        chip_info_entry = chip_info_reader.get_chip(OPTIONS['--pic_type'])
        print('Opening connection to programmer...')
        with Connection(OPTIONS['--port']) as connection:
            print('Initializing programming interface...')
            with connection.get_programming_interface(
                    chip_info_entry,
                    icsp_mode=OPTIONS['--icsp']
            ) as programming_interface:
                chip_config = programming_interface.read_config()
                _print_chip_config(chip_config, chip_info_entry)

                print('Done!')
    except IOError:
        print('Unable to locate chipinfo.cid file.')
        print('Please verify that file is present in the same directory as this script, '
              'and that the filename is in lowercase characters, and that you have access to read the file.')

def main() -> None:
    signal.signal(signal.SIGINT, lambda _signal, _frame: sys.exit(0))  # Properly handle Control+C
    getattr(command, 'chosen')()  # Execute the function specified by the user.


if __name__ == '__main__':
    main()
