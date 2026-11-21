#!/usr/bin/python
"""Typer command-line adapter for the PicPro application service."""

import json
import signal
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from intelhex import HexReaderError, IntelHex
from serial import SerialException, SerialTimeoutException
from yaml import YAMLError

import picpro as app_root
from picpro.ChipDataReader import ChipDataReader
from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.exceptions import FormatError, FuseError, ICSPRequiredError, InvalidFirmwareError, InvalidPicIdError, InvalidResponseError, UnknownChipError
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
        typer.echo(app_root.__version__)
        raise typer.Exit


@app.callback()
def cli(*, version: Annotated[bool, typer.Option('--version', '-v', callback=_version, is_eager=True, help='Display version.')] = False) -> None:
    """Select a command; use COMMAND --help for its arguments and options."""


def _find_chip_data() -> Path | Traversable:
    return PicPro.find_chip_data()


def _print_chip_config(chip_config: ChipConfig, chip_info_entry: ChipInfoEntry) -> None:
    typer.echo(f'Chip ID: {chip_config.chip_id} ({hex(chip_config.chip_id)})')
    typer.echo(f'ID:      {chip_config.id.hex()}')
    typer.echo(f'CAL:     {chip_config.calibrate}')
    typer.echo('Fuses:')
    for name, value in chip_info_entry.decode_fuse_data(chip_config.fuses).items():
        typer.echo(f'    {name} = {value}')



def _display_config_event(event: ChipConfigEvent, operation: str) -> None:
    if event.device_id_mismatch:
        typer.echo(
            f'Warning: Device ID mismatch for {event.chip.chip_name}. '
            f'Expected {event.chip.chip_id:#06x}, read {event.config.chip_id:#06x}.',
            err=True,
        )
    if operation == 'dump':
        return
    if operation == 'verify':
        typer.echo(f'Chip config: {event.config}')
    else:
        if operation == 'program':
            typer.echo('==== Chip info ====')
        _print_chip_config(event.config, event.chip)


def _display_event(event: PicProEvent, operation: str, output_file: Path | None = None) -> None:
    if operation == 'programmer_info':
        return
    if isinstance(event, ChipConfigEvent):
        _display_config_event(event, operation)
    elif isinstance(event, VerificationEvent):
        label = event.memory.value.upper()
        if event.matches:
            typer.echo(f'{label} verified.')
        else:
            if event.memory == MemoryType.EEPROM:
                typer.echo(f'{event.actual.hex()} {event.expected.hex()} ({len(event.expected)})', err=True)
            typer.echo(f'{label} verification failed.', err=True)
            if event.maybe_locked:
                typer.echo('Maybe ROM is locked for reading?', err=True)
    elif isinstance(event, StageEvent):
        if operation == 'dump' and event.stage in (Stage.READING_ROM, Stage.READING_EEPROM, Stage.READING_CONFIG):
            memory = {Stage.READING_ROM: 'ROM', Stage.READING_EEPROM: 'EEPROM', Stage.READING_CONFIG: 'CONFIG'}[event.stage]
            typer.echo(f'Reading {memory} into file {output_file}...')
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
                typer.echo(message)


def _service(operation: str, output_file: Path | None = None) -> PicPro:
    return PicPro(
        chip_data=ChipDataReader(_find_chip_data()) if operation != 'programmer_info' else None,
        connection_factory=Connection,
        on_event=lambda event: _display_event(event, operation, output_file),
    )


def _fail(operation: str, message: str) -> NoReturn:
    typer.echo(f'{operation}: {message}', err=True)
    raise typer.Exit(1)


@contextmanager
def _report_errors(operation: str, *, port: str | None = None, firmware: Path | None = None) -> Iterator[None]:
    try:
        yield
    except (SerialTimeoutException, TimeoutError) as error:
        _fail(operation, f'Operation timed out: {error}' if str(error) else 'Operation timed out.')
    except ConnectionError as error:
        _fail(operation, f'Unable to connect to programmer: {error}')
    except SerialException as error:
        _fail(operation, f'Serial communication failed on "{port}": {error}')
    except InvalidResponseError as error:
        detail = f' {error}' if str(error) else ''
        _fail(operation, f'Invalid response from programmer on "{port}".{detail}')
    except UnknownChipError as error:
        _fail(operation, f'Unable to find chip type "{error.args[0]}" in chip definitions.')
    except NoEEPROMError:
        _fail(operation, 'This chip has no EEPROM.')
    except (HexReaderError, InvalidFirmwareError) as error:
        _fail(operation, f'Invalid firmware "{firmware}": {error}')
    except ICSPRequiredError as error:
        _fail(operation, f'{error} Connect through ICSP and rerun with --icsp.')
    except InvalidPicIdError as error:
        _fail(operation, str(error))
    except FuseError as error:
        _fail(operation, f'Fuse error: {error}')
    except (FormatError, YAMLError) as error:
        _fail(operation, f'Invalid chip definitions: {error}')
    except OSError as error:
        _fail(operation, f'Unable to access file or device: {error}')


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
    with _report_errors('program', port=port, firmware=hex_file):
        service = _service('program')
        if fuses:
            chip = service.get_chip(pic_type)
            try:
                chip.encode_fuse_data(fuses)
            except FuseError as error:
                _fail('program', f'Invalid fuse setting. {error}\nValid settings:\n{chip.fuse_doc.rstrip()}')
        result = service.program(Target(port, pic_type, icsp), hex_file, pic_id=pic_id, fuses=fuses)
        if not result.success:
            raise typer.Exit(1)


@app.command()
def verify(port: Port, pic_type: ChipType, hex_file: InputFile, *, icsp: ICSP = False) -> None:
    """Verify PIC flash against an Intel HEX file."""
    with _report_errors('verify', port=port, firmware=hex_file):
        result = _service('verify').verify(Target(port, pic_type, icsp), hex_file)
        if not result.success:
            raise typer.Exit(1)


class DumpRegion(StrEnum):
    ROM = 'rom'
    EEPROM = 'eeprom'
    CONFIG = 'config'
    ALL = 'all'


@app.command()
def dump(mem_type: Annotated[DumpRegion, typer.Argument(help='Memory to read: rom, eeprom, config, or all.')],
         port: Port, pic_type: ChipType, output_file: OutputFile, *, icsp: ICSP = False,
         binary: Annotated[bool, typer.Option('--binary', help='Write raw binary instead of Intel HEX.')] = False) -> None:
    """Dump PIC memory to a file."""
    if mem_type == DumpRegion.ALL and binary:
        msg = 'A whole-chip backup requires Intel HEX.'
        raise typer.BadParameter(msg, param_hint='--binary')
    with _report_errors('dump', port=port):
        service = _service('dump', output_file)
        target = Target(port, pic_type, icsp)
        if mem_type == DumpRegion.ALL:
            image = service.read_backup(target)
        else:
            content = service.read_memory(target, MemoryType(mem_type))
            if mem_type == DumpRegion.ROM:
                content = swab_bytes(content)
            if binary:
                output_file.write_bytes(content)
                typer.echo('Done!')
                return
            image = IntelHex()
            image.frombytes(content)
        with output_file.open('w', encoding='ascii') as file:
            image.write_hex_file(file)
        typer.echo('Done!')


@app.command()
def erase(port: Port, pic_type: ChipType, *, icsp: ICSP = False) -> None:
    """Erase a PIC chip."""
    with _report_errors('erase', port=port):
        _service('erase').erase(Target(port, pic_type, icsp))


@app.command('chip_info')
def chip_info(pic_type: Annotated[str | None, typer.Argument(help='PIC type; omit to list all chips.')] = None) -> None:
    """Print chip definitions as JSON."""
    with _report_errors('chip_info'):
        service = _service('chip_info')
        name = pic_type
        data = service.get_chip(name).to_dict() if name else {name: chip.to_dict() for name, chip in service.list_chips().items()}
        typer.echo(json.dumps(data))


@app.command('hex_info')
def hex_info(hex_file_path: Annotated[Path, typer.Argument(help='Intel HEX input file.')],
             pic_type: Annotated[str, typer.Argument(help='PIC chip type.')]) -> None:
    """Show firmware memory usage and contents."""
    with _report_errors('hex_info', firmware=hex_file_path):
        flash_data = _service('hex_info').inspect_hex(pic_type, hex_file_path)
    chip_info_entry = flash_data.chip_info
    intel_hex = flash_data.hex_file
    typer.echo(f'ROM {flash_data.rom_buffer.raw_size} bytes used, {chip_info_entry.rom_size - flash_data.rom_buffer.raw_size} bytes free on chip.')
    typer.echo(f'EEPROM {flash_data.eeprom_buffer.raw_size} bytes used, {chip_info_entry.eeprom_size - flash_data.eeprom_buffer.raw_size} bytes free on chip.')

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
        typer.echo(f'{indent_char:s}entry: 0x{entry:08X}')
    segments = intel_hex.segments()
    if segments:
        typer.echo(f'{indent_char:s}data:')
        for s in segments:
            typer.echo(f'{indent_char:s}{in_list_char:s}{{ first: 0x{s[0]:08X}, last: 0x{s[1] - 1:08X}, length: 0x{s[1] - s[0]:08X} }}')
    typer.echo()

    typer.echo(f'ROM: {flash_data.rom_data.hex()}')
    typer.echo(f'EEPROM: {flash_data.eeprom_data.hex()}')



@app.command('programmer_info')
def programmer_info(port: Port) -> None:
    """Print the programmer firmware and protocol versions."""
    with _report_errors('programmer_info', port=port):
        info = _service('programmer_info').programmer_info(port)
        typer.echo(f'Firmware version: {info.firmware_version}')
        typer.echo(f'Protocol version: {info.protocol}')


@app.command('decode_fuses')
def decode_fuses(fuses: Annotated[str, typer.Argument(help='Space-separated decimal fuse words (quote multiple words).')], pic_type: ChipType) -> None:
    """Decode fuse words into named settings."""
    try:
        words = [int(value) for value in fuses.split()]
    except ValueError as error:
        msg = 'Fuse words must be decimal integers.'
        raise typer.BadParameter(msg, param_hint='fuses') from error
    with _report_errors('decode_fuses'):
        typer.echo(_service('decode_fuses').decode_fuses(pic_type, words))


@app.command('read_chip_config')
def read_chip_config(port: Port, pic_type: ChipType, *, icsp: ICSP = False) -> None:
    """Read chip identification, calibration, and fuse settings."""
    with _report_errors('read_chip_config', port=port):
        _service('read_chip_config').read_config(Target(port, pic_type, icsp))


@app.command('chipdata_migrate')
def chipdata_migrate(cid_file: Annotated[Path | None, typer.Argument(help='Legacy CID file; omit to search standard locations.')] = None,
                     output: Annotated[Path | None, typer.Option('--output', help='Directory for YAML chip definitions.')] = None) -> None:
    """Convert legacy CID chip definitions to YAML."""
    with _report_errors('chipdata_migrate'):
        PicPro.migrate_chip_data(cid_file, output)


def main() -> None:
    signal.signal(signal.SIGINT, lambda _signal, _frame: sys.exit(0))  # Properly handle Control+C
    app(prog_name='picpro')


if __name__ == '__main__':
    main()
