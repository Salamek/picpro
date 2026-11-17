#!/usr/bin/python
"""Typer command-line adapter for the PicPro application service."""

import json
import signal
import sys
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Annotated

import typer
from intelhex import IntelHex

import picpro as app_root
from picpro.ChipDataReader import ChipDataReader
from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.exceptions import FuseError, InvalidResponseError
from picpro.PicPro import ChipConfigEvent, MemoryType, NoEEPROMError, PicPro, PicProEvent, Stage, StageEvent, Target, VerificationEvent
from picpro.protocol.ChipConfig import ChipConfig
from picpro.protocol.p18a.Connection import Connection
from picpro.tools import swab_bytes

app = typer.Typer(
    help='Program and inspect PIC chips using kitsrus K150-compatible programmers.',
    context_settings={'help_option_names': ['-h', '--help']},
)

Port = Annotated[str, typer.Option('--port', '-p', help='Serial port connected to the programmer.')]
ChipType = Annotated[str, typer.Option('--pic_type', '-t', help='PIC chip type.')]
InputFile = Annotated[Path, typer.Option('--hex_file', '-i', help='Intel HEX input file.')]
OutputFile = Annotated[Path, typer.Option('--hex_file', '-o', help='Output file.')]
ICSP = Annotated[bool, typer.Option('--icsp', help='Enable ICSP programming.')]


def _version(value: bool) -> None:  # noqa: FBT001 - Typer option callback signature
    if value:
        print(app_root.__version__)
        raise typer.Exit


@app.callback()
def cli(*, version: Annotated[bool, typer.Option('--version', '-v', callback=_version, is_eager=True, help='Display version.')] = False) -> None:
    """Select a command; use COMMAND --help for its arguments and options."""


def _find_chip_data() -> Path | Traversable:
    return PicPro.find_chip_data()


def _print_chip_config(chip_config: ChipConfig, chip_info_entry: ChipInfoEntry) -> None:
    print(f'Chip ID: {chip_config.chip_id} ({hex(chip_config.chip_id)})')
    print(f'ID:      {chip_config.id.hex()}')
    print(f'CAL:     {chip_config.calibrate}')
    print('Fuses:')
    for name, value in chip_info_entry.decode_fuse_data(chip_config.fuses).items():
        print(f'    {name} = {value}')



def _display_event(event: PicProEvent, operation: str, output_file: Path | None = None) -> None:
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
            print(f'Reading {memory} into file {output_file}...')
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


def _service(operation: str, output_file: Path | None = None) -> PicPro:
    return PicPro(
        chip_data=ChipDataReader(_find_chip_data()) if operation != 'programmer_info' else None,
        connection_factory=Connection,
        on_event=lambda event: _display_event(event, operation, output_file),
    )


def _file_error() -> None:
    print('Unable to read input/output files or YAML chip definitions in chip-data.d.')
    print('Please verify the paths and file permissions.')


@app.command()
def program(port: Port, pic_type: ChipType, hex_file: InputFile, *,
            pic_id: Annotated[str | None, typer.Option('--id', help='PIC ID in hexadecimal.')] = None,
            fuse: Annotated[list[str] | None, typer.Option('--fuse', help='NAME:VALUE fuse setting; repeat for multiple fuses.')] = None,
            icsp: ICSP = False) -> None:
    """Program a PIC chip and verify its contents."""
    fuses = {}
    for setting in fuse or []:
        name, separator, value = setting.partition(':')
        if not separator or not name or not value:
            msg = 'Expected NAME:VALUE.'
            raise typer.BadParameter(msg, param_hint='--fuse')
        fuses[name] = value
    try:
        service = _service('program')
        try:
            result = service.program(Target(port, pic_type, icsp), hex_file, pic_id=pic_id, fuses=fuses)
        except FuseError:
            print('Invalid fuse setting. Fuse names and valid settings for this chip are as follows:')
            print(service.get_chip(pic_type).fuse_doc)
            return
        if not result.success:
            raise typer.Exit(1)
    except OSError:
        _file_error()


@app.command()
def verify(port: Port, pic_type: ChipType, hex_file: InputFile, *, icsp: ICSP = False) -> None:
    """Verify PIC flash against an Intel HEX file."""
    try:
        result = _service('verify').verify(Target(port, pic_type, icsp), hex_file)
        if not result.success:
            raise typer.Exit(1)
    except OSError:
        _file_error()


@app.command()
def dump(mem_type: Annotated[MemoryType, typer.Argument(help='Memory to read: rom, eeprom, or config.')],
         port: Port, pic_type: ChipType, output_file: OutputFile, *, icsp: ICSP = False,
         binary: Annotated[bool, typer.Option('--binary', help='Write raw binary instead of Intel HEX.')] = False) -> None:
    """Dump PIC memory to a file."""
    try:
        memory = mem_type
        try:
            content = _service('dump', output_file).read_memory(Target(port, pic_type, icsp), memory)
        except NoEEPROMError:
            print('This chip has no EEPROM!')
            return
        if memory == MemoryType.ROM:
            content = swab_bytes(content)
        if binary:
            output_file.write_bytes(content)
        else:
            image = IntelHex()
            image.frombytes(content)
            with output_file.open('w', encoding='ascii') as file:
                image.write_hex_file(file)
        print('Done!')
    except OSError:
        _file_error()


@app.command()
def erase(port: Port, pic_type: ChipType, *, icsp: ICSP = False) -> None:
    """Erase a PIC chip."""
    try:
        _service('erase').erase(Target(port, pic_type, icsp))
    except OSError:
        _file_error()


@app.command('chip_info')
def chip_info(pic_type: Annotated[str | None, typer.Argument(help='PIC type; omit to list all chips.')] = None) -> None:
    """Print chip definitions as JSON."""
    service = _service('chip_info')
    name = pic_type
    data = service.get_chip(name).to_dict() if name else {name: chip.to_dict() for name, chip in service.list_chips().items()}
    print(json.dumps(data))


@app.command('hex_info')
def hex_info(hex_file_path: Annotated[Path, typer.Argument(help='Intel HEX input file.')],
             pic_type: Annotated[str, typer.Argument(help='PIC chip type.')]) -> None:
    """Show firmware memory usage and contents."""
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


@app.command('programmer_info')
def programmer_info(port: Port) -> None:
    """Print the programmer firmware and protocol versions."""
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


@app.command('decode_fuses')
def decode_fuses(fuses: Annotated[str, typer.Argument(help='Space-separated decimal fuse words (quote multiple words).')], pic_type: ChipType) -> None:
    """Decode fuse words into named settings."""
    try:
        words = [int(value) for value in fuses.split()]
    except ValueError as error:
        msg = 'Fuse words must be decimal integers.'
        raise typer.BadParameter(msg, param_hint='fuses') from error
    print(_service('decode_fuses').decode_fuses(pic_type, words))


@app.command('read_chip_config')
def read_chip_config(port: Port, pic_type: ChipType, *, icsp: ICSP = False) -> None:
    """Read chip identification, calibration, and fuse settings."""
    try:
        _service('read_chip_config').read_config(Target(port, pic_type, icsp))
    except OSError:
        _file_error()


@app.command('chipdata_migrate')
def chipdata_migrate(cid_file: Annotated[Path | None, typer.Argument(help='Legacy CID file; omit to search standard locations.')] = None,
                     output: Annotated[Path | None, typer.Option('--output', help='Directory for YAML chip definitions.')] = None) -> None:
    """Convert legacy CID chip definitions to YAML."""
    PicPro.migrate_chip_data(cid_file, output)


def main() -> None:
    signal.signal(signal.SIGINT, lambda _signal, _frame: sys.exit(0))  # Properly handle Control+C
    app(prog_name='picpro')


if __name__ == '__main__':
    main()
