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
    chipdata_migrate    Convert legacy CID chip definitions to YAML.

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
    picpro chipdata_migrate [<CID_FILE>] [--output=OUTPUT_DIR]
    picpro (-h | --help)
    picpro (-v | --version)


Options:
    --output=OUTPUT_DIR              Directory for migrated YAML chip definitions.
    --icsp                           Enable ISCP programming.
    --fuse=FUSE_NAME:FUSE_VALUE      Set fuse value directly.
    --id=PIC_ID                      Set PIC id to be programmed in pic HEX format.
    -p PORT --port=PORT              Set serial port where programmer is connected.
    -t PIC_TYPE --pic_type=PIC_TYPE  Pic type you are programming/reading.
    -i HEX_FILE --hex_file=HEX_FILE  Hex file to flash or to read.
    -o HEX_FILE --hex_file=HEX_FILE  Hex file to write.
    --binary                         Input/Output file is in binary.
    -v --version                     Display version info
"""

import json
import signal
import sys
from collections.abc import Callable
from functools import wraps
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import TypeVar

from docopt import docopt
from intelhex import IntelHex

import picpro as app_root
from picpro.ChipDataReader import ChipDataReader
from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.exceptions import FuseError, InvalidResponseError
from picpro.PicPro import ChipConfigEvent, MemoryType, NoEEPROMError, PicPro, PicProEvent, Stage, StageEvent, Target, VerificationEvent
from picpro.protocol.ChipConfig import ChipConfig
from picpro.protocol.p18a.Connection import Connection
from picpro.tools import swab_bytes

OPTIONS = docopt(__doc__)
CT = TypeVar('CT')

if OPTIONS['--version']:
    print(app_root.__version__)
    sys.exit(0)


def command(name: str | None = None) -> Callable[[Callable[..., CT]], Callable[..., CT]]:
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

    Doing this instead of using Flask-Script.

    Positional arguments:
    func -- the function to decorate
    """

    def function_wrap(func: Callable[..., CT]) -> Callable[..., CT]:

        @wraps(func)
        def wrapped() -> CT:
            return func()

        command_name = name or func.__name__

        # Register chosen function.
        if command_name not in OPTIONS:
            msg = f'Cannot register {command_name}, not mentioned in docstring/docopt.'
            raise KeyError(msg)
        if OPTIONS[command_name]:
            command.chosen = func  # type: ignore[attr-defined]

        return wrapped

    return function_wrap



def _find_chip_data() -> Path | Traversable:
    return PicPro.find_chip_data()


def _print_chip_config(chip_config: ChipConfig, chip_info_entry: ChipInfoEntry) -> None:
    print(f'Chip ID: {chip_config.chip_id} ({hex(chip_config.chip_id)})')
    print(f'ID:      {chip_config.id.hex()}')
    print(f'CAL:     {chip_config.calibrate}')
    print('Fuses:')
    for name, value in chip_info_entry.decode_fuse_data(chip_config.fuses).items():
        print(f'    {name} = {value}')



def _display_event(event: PicProEvent, operation: str) -> None:
    if operation == 'programmer_info':
        return
    if isinstance(event, ChipConfigEvent):
        if operation == 'verify':
            print(f'Chip config: {event.config}')
        else:
            if operation == 'program':
                print('==== Chip info ====')
            _print_chip_config(event.config, event.chip)
    elif isinstance(event, VerificationEvent):
        label = event.memory.value.upper()
        if event.matches:
            print(f'{label} verified.')
        else:
            if event.memory == MemoryType.EEPROM:
                print(f'{event.actual.hex()} {event.expected.hex()} ({len(event.expected)})')
            print(f'{label} verification failed.')
            if event.maybe_locked:
                print('Maybe ROM is locked for reading?')
    elif isinstance(event, StageEvent):
        if operation == 'dump' and event.stage in (Stage.READING_ROM, Stage.READING_EEPROM, Stage.READING_CONFIG):
            memory = {Stage.READING_ROM: 'ROM', Stage.READING_EEPROM: 'EEPROM', Stage.READING_CONFIG: 'CONFIG'}[event.stage]
            print(f"Reading {memory} into file {OPTIONS['--hex_file']}...")
        elif event.stage == Stage.COMPLETED and operation == 'dump':
            return  # File output completes after the service has released the device.
        else:
            messages = {
                Stage.CONNECTING: 'Opening connection to programmer...',
                Stage.INITIALIZING: 'Initializing programming interface...',
                Stage.PRESERVING_CALIBRATION: 'CAL is in ROM data, patching ROM to contain the same CAL data...',
                Stage.ERASING: 'Erasing chip...' if operation == 'erase' else 'Erasing chip.',
                Stage.ERASED: 'Done!',
                Stage.ERASE_SKIPPED: 'This chip is not erasable.',
                Stage.PROGRAMMING_ROM: 'Programming ROM.',
                Stage.PROGRAMMING_EEPROM: 'Programming EEPROM.',
                Stage.PROGRAMMING_FUSES: 'Programming ID and fuses.',
                Stage.VERIFYING_ROM: 'Verifying ROM.',
                Stage.VERIFYING_EEPROM: 'Verifying EEPROM.',
                Stage.COMMITTING_FUSES: 'Committing 18Fxxxx fuse data.',
                Stage.COMPLETED: 'Done!',
            }
            message = messages.get(event.stage)
            if message:
                print(message)


def _service(operation: str) -> PicPro:
    return PicPro(
        chip_data=ChipDataReader(_find_chip_data()) if operation != 'programmer_info' else None,
        connection_factory=Connection,
        on_event=lambda event: _display_event(event, operation),
    )


def _target() -> Target:
    return Target(OPTIONS['--port'], OPTIONS['--pic_type'], OPTIONS['--icsp'])


def _file_error() -> None:
    print('Unable to read input/output files or YAML chip definitions in chip-data.d.')
    print('Please verify the paths and file permissions.')


@command()
def program() -> None:
    fuses = dict(fuse.split(':') for fuse in OPTIONS['--fuse'])
    try:
        service = _service('program')
        try:
            result = service.program(_target(), Path(OPTIONS['--hex_file']), pic_id=OPTIONS['--id'], fuses=fuses)
        except FuseError:
            print('Invalid fuse setting. Fuse names and valid settings for this chip are as follows:')
            print(service.get_chip(OPTIONS['--pic_type']).fuse_doc)
            return
        if not result.success:
            sys.exit(1)
    except OSError:
        _file_error()


@command()
def verify() -> None:
    try:
        result = _service('verify').verify(_target(), Path(OPTIONS['--hex_file']))
        if not result.success:
            sys.exit(1)
    except OSError:
        _file_error()


@command()
def dump() -> None:
    output_file = Path(OPTIONS['--hex_file'])
    try:
        memory = MemoryType(OPTIONS['<mem_type>'])
        try:
            content = _service('dump').read_memory(_target(), memory)
        except NoEEPROMError:
            print('This chip has no EEPROM!')
            return
        if memory == MemoryType.ROM:
            content = swab_bytes(content)
        if OPTIONS['--binary']:
            output_file.write_bytes(content)
        else:
            image = IntelHex()
            image.frombytes(content)
            with output_file.open('w', encoding='ascii') as file:
                image.write_hex_file(file)
        print('Done!')
    except OSError:
        _file_error()


@command()
def erase() -> None:
    try:
        _service('erase').erase(_target())
    except OSError:
        _file_error()


@command()
def chip_info() -> None:
    service = _service('chip_info')
    name = OPTIONS['<PIC_TYPE>']
    data = service.get_chip(name).to_dict() if name else {name: chip.to_dict() for name, chip in service.list_chips().items()}
    print(json.dumps(data))


@command()
def hex_info() -> None:
    pic_type = OPTIONS['<PIC_TYPE>']
    hex_file_path = Path(OPTIONS['<HEX_FILE>'])
    try:
        service = _service('hex_info')
        flash_data = service.inspect_hex(pic_type, hex_file_path)
    except OSError:
        if not hex_file_path.is_file():
            print(f'Unable to find hex file "{hex_file_path}".')
            print('Please verify that the file exists and that you have access to it.')
        else:
            _file_error()
        return
    except KeyError:
        print(f'Unable to find chip type "{pic_type}" in data file.')
        print('Please check that the spelling is correct, and that data file is up-to-date.')
        return
    except FuseError:
        print('Invalid fuse setting. Fuse names and valid settings for this chip are as follows:')
        print(service.get_chip(pic_type).fuse_doc)
        return
    chip_info_entry = flash_data.chip_info
    intel_hex = flash_data.hex_file
    print(f'ROM {flash_data.rom_buffer.raw_size} bytes used, {chip_info_entry.rom_size - flash_data.rom_buffer.raw_size} bytes free on chip.')
    print(f'EEPROM {flash_data.eeprom_buffer.raw_size} bytes used, {chip_info_entry.eeprom_size - flash_data.eeprom_buffer.raw_size} bytes free on chip.')

    indent_char = '  '
    in_list_char = '- '

    if intel_hex.start_addr:
        keys = sorted(intel_hex.start_addr.keys())
        if keys == ['CS', 'IP']:
            entry = intel_hex.start_addr['CS'] * 16 + intel_hex.start_addr['IP']
        elif keys == ['EIP']:
            entry = intel_hex.start_addr['EIP']
        else:
            msg = "Unknown 'IntelHex.start_addr' found."
            raise RuntimeError(msg)
        print(f'{indent_char:s}entry: 0x{entry:08X}')
    segments = intel_hex.segments()
    if segments:
        print(f'{indent_char:s}data:')
        for s in segments:
            print(f'{indent_char:s}{in_list_char:s}{{ first: 0x{s[0]:08X}, last: 0x{s[1] - 1:08X}, length: 0x{s[1] - s[0]:08X} }}')
    print()

    print(f'ROM: {flash_data.rom_data.hex()}')
    print(f'EEPROM: {flash_data.eeprom_data.hex()}')

    return


@command()
def programmer_info() -> None:
    port = OPTIONS['--port']
    try:
        info = _service('programmer_info').programmer_info(port)
        print(f'Firmware version: {info.firmware_version}')
        print(f'Protocol version: {info.protocol}')
    except ConnectionError:
        print(f'Unable to open serial port "{port}".')
        print('Be sure port identifier is valid and that you have access to it.')
    except InvalidResponseError as error:
        print(f'Unable to initialize connection to programmer. {error}')
        print('Please check that device is properly connected and working.')


@command()
def decode_fuses() -> None:
    print(_service('decode_fuses').decode_fuses(OPTIONS['--pic_type'], [int(value) for value in OPTIONS['<fuses>'].split()]))


@command()
def read_chip_config() -> None:
    try:
        _service('read_chip_config').read_config(_target())
    except OSError:
        _file_error()


@command()
def chipdata_migrate() -> None:
    PicPro.migrate_chip_data(
        Path(OPTIONS['<CID_FILE>']) if OPTIONS['<CID_FILE>'] else None,
        Path(OPTIONS['--output']) if OPTIONS['--output'] else None,
    )


def main() -> None:
    signal.signal(signal.SIGINT, lambda _signal, _frame: sys.exit(0))  # Properly handle Control+C
    if hasattr(command, 'chosen'):
        command.chosen()  # Execute the function specified by the user.


if __name__ == '__main__':
    main()
