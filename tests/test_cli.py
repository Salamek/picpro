import ast
import importlib
import json
import os
import runpy
import subprocess
import sys
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from intelhex import IntelHex

from picpro import __version__
from picpro.ChipDataReader import ChipDataReader
from picpro.ChipInfoReader import ChipInfoReader
from picpro.exceptions import InvalidResponseError
from picpro.FlashData import FlashData
from picpro.protocol.ChipConfig import ChipConfig
from tests.MockedDevice import MockedDevice

_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class CLIResult:
    code: int
    stdout: str
    stderr: str


@dataclass
class CLI:
    monkeypatch: pytest.MonkeyPatch
    capsys: pytest.CaptureFixture[str]
    device: MockedDevice
    serial_factory: MagicMock
    image: Path
    database: Path
    expected: FlashData
    config: ChipConfig
    output: Path

    def run(self, *arguments: str) -> CLIResult:
        # Exercise the public entry point with fresh argv parsing and command
        # registration each time, even when another test imported the CLI.
        package = importlib.import_module('picpro.bin')
        previous_module = sys.modules.pop('picpro.bin.picpro', None)
        previous_attribute = package.__dict__.pop('picpro', None)
        self.capsys.readouterr()
        code = 0
        try:
            with patch.object(sys, 'argv', ['picpro', *arguments]), patch('signal.signal'), patch('picpro.protocol.IConnection.time.sleep'):
                try:
                    runpy.run_module('picpro', run_name='__main__')
                except SystemExit as exc:
                    if isinstance(exc.code, int):
                        code = exc.code
                    elif exc.code is not None:
                        code = 1
                        sys.stderr.write(f'{exc.code}\n')
        finally:
            sys.modules.pop('picpro.bin.picpro', None)
            package.__dict__.pop('picpro', None)
            if previous_module is not None:
                sys.modules['picpro.bin.picpro'] = previous_module
            if previous_attribute is not None:
                package.__dict__['picpro'] = previous_attribute
        output = self.capsys.readouterr()
        return CLIResult(code, output.out, output.err)

    def hardware_args(self, command: str) -> list[str]:
        args = [command]
        if command == 'dump':
            args.extend(['rom', '-o', str(self.output)])
        elif command in ('program', 'verify'):
            args.extend(['-i', str(self.image)])
        args.extend(['-p', '/dev/fake', '-t', '12F675'])
        return args


@pytest.fixture
def cli(tmp_path: Path, chip_data_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> Iterator[CLI]:
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    database = data_dir / 'chipdata.cid'
    database.write_bytes(chip_data_path.read_bytes())
    monkeypatch.setattr('platformdirs.user_data_dir', lambda _app: str(data_dir))
    image_path = tmp_path / 'firmware.hex'
    image = IntelHex()
    image.frombytes(b'\x83\x12')
    image.frombytes(b'\x01\x00\x02\x00\x03\x00\x04\x00', offset=0x4000)
    image.frombytes(b'\xff\x31', offset=0x400e)
    image.frombytes(b'\x11\x00\x22\x00', offset=0x4200)
    image.write_hex_file(str(image_path))
    chip = ChipInfoReader(database).get_chip('12f675')
    expected = FlashData(chip, image)
    expected.set_calibration_word(b'\x34\x56')
    config = ChipConfig(chip_id=0x0fc0, id=b'12345678', fuses=[0x31ff] + [0] * 6, calibrate=0x3456)
    device = MockedDevice(b'P18A')
    device.work_thread.chip_config = config
    device.work_thread.rom_data = expected.rom_data
    device.work_thread.eeprom_data = expected.eeprom_data
    factory = MagicMock(return_value=device)
    monkeypatch.setattr('serial.Serial', factory)
    worker = threading.Thread(target=device.work_thread.listen_for_commands, daemon=True)
    worker.start()
    try:
        yield CLI(monkeypatch, capsys, device, factory, image_path, database, expected, config, tmp_path / 'dump.bin')
    finally:
        device.close()
        worker.join(timeout=1)
        assert not worker.is_alive(), 'CLI fake programmer worker did not stop'


@pytest.mark.parametrize('arguments', [['--help'], ['--version'], ['nonsense'], ['program']])
def test_public_module_entry_point(arguments: list[str]) -> None:
    result = subprocess.run(  # noqa: S603 - fixed local executable and controlled test arguments
        [sys.executable, '-m', 'picpro', *arguments], cwd=_ROOT,
        env={**os.environ, 'PYTHONPATH': str(_ROOT)}, capture_output=True, text=True, timeout=10, check=False,
    )
    if arguments == ['--version']:
        assert result.returncode == 0
        assert result.stdout.strip() == __version__
        assert result.stderr == ''
    elif arguments == ['--help']:
        assert result.returncode == 0
        assert 'Usage:' in result.stdout
        assert 'picpro program' in result.stdout
        assert result.stderr == ''
    else:
        assert result.returncode != 0
        assert 'Usage:' in result.stderr
        assert 'Traceback' not in result.stderr


@pytest.mark.parametrize('name', [None, '12F675'])
def test_chip_info_json_and_user_database(cli: CLI, name: str | None) -> None:
    args = ['chip_info'] + ([name] if name else [])
    result = cli.run(*args)
    assert result.code == 0
    assert result.stderr == ''
    data = json.loads(result.stdout)
    if name:
        assert data['chip_name'] == '12f675'
        assert data['rom_size'] == 2048
        assert data['eeprom_size'] == 128
    else:
        assert set(data) == {'10f200', '16f737', '12f675'}
    cli.serial_factory.assert_not_called()


def test_decode_fuses_command(cli: CLI) -> None:
    result = cli.run('decode_fuses', '12799', '-t', '12F675')
    assert result.code == 0
    values = ast.literal_eval(result.stdout)
    assert values['WDT'] == 'Enabled'
    assert values['Bandgap'] == 'Highest'
    cli.serial_factory.assert_not_called()


def test_hex_info_reports_logical_usage(cli: CLI) -> None:
    result = cli.run('hex_info', str(cli.image), '12F675')
    assert result.code == 0
    assert 'ROM 2 bytes used, 2046 bytes free' in result.stdout
    assert 'EEPROM 2 bytes used, 126 bytes free' in result.stdout
    assert 'ROM: 1283' in result.stdout
    assert 'EEPROM: 1122' in result.stdout
    cli.serial_factory.assert_not_called()


@pytest.mark.parametrize('failure', ['missing_file', 'unknown_chip'])
def test_hex_info_errors_do_not_open_programmer(cli: CLI, failure: str) -> None:
    image = cli.image.with_name('missing.hex') if failure == 'missing_file' else cli.image
    chip = 'UNKNOWN' if failure == 'unknown_chip' else '12f675'
    result = cli.run('hex_info', str(image), chip)
    expected = 'Unable to find hex file' if failure == 'missing_file' else 'Unable to find chip type "UNKNOWN"'
    assert expected in result.stdout
    cli.serial_factory.assert_not_called()


def test_program_parses_repeated_fuses_id_and_preserves_calibration(cli: CLI) -> None:
    result = cli.run(*cli.hardware_args('program'), '--id=DEADBEEF', '--fuse=WDT:Disabled', '--fuse=MCLRE:Disabled')
    assert result.code == 0
    assert result.stderr == ''
    for message in ['Programming ROM.', 'Programming EEPROM.', 'ROM verified.', 'EEPROM verified.']:
        assert message in result.stdout
    state = cli.device.work_thread
    assert state.rom_data == cli.expected.rom_data
    assert state.eeprom_data == b'\x11\x22' + b'\xff' * 126
    assert state.chip_config is not None
    assert state.chip_config.id == bytes.fromhex('deadbeef') + b'\x00' * 4
    assert state.chip_config.fuses[0] == 0x31d7
    assert not cli.device.is_open
    cli.serial_factory.assert_called_once()
    assert cli.serial_factory.call_args.kwargs['port'] == '/dev/fake'


@pytest.mark.parametrize('fuse', ['UNKNOWN:Enabled', 'WDT:unknown'])
def test_invalid_fuses_print_valid_choices_before_opening_port(cli: CLI, fuse: str) -> None:
    result = cli.run(*cli.hardware_args('program'), f'--fuse={fuse}')
    assert 'Invalid fuse setting.' in result.stdout
    assert "'WDT' : ('Enabled', 'Disabled')" in result.stdout
    cli.serial_factory.assert_not_called()


@pytest.mark.parametrize('icsp', [False, True])
@pytest.mark.parametrize('command', ['program', 'verify', 'dump', 'erase', 'read_chip_config'])
def test_hardware_commands_forward_icsp_option(cli: CLI, command: str, *, icsp: bool) -> None:
    result = cli.run(*cli.hardware_args(command), *(['--icsp'] if icsp else []))
    assert result.code == 0
    received = cli.device.work_thread.programing_vars
    assert received is not None
    assert received.power_sequence == (3 if icsp else 4)
    assert not cli.device.is_open


def test_verify_success(cli: CLI) -> None:
    result = cli.run(*cli.hardware_args('verify'))
    assert result.code == 0
    assert 'ROM verified.' in result.stdout
    assert 'EEPROM verified.' in result.stdout
    assert not cli.device.is_open


@pytest.mark.parametrize('memory', ['rom', 'eeprom'])
def test_verify_mismatch_returns_failure_and_closes_port(cli: CLI, memory: str) -> None:
    if memory == 'rom':
        cli.device.work_thread.rom_data = b'\x00' * 2046 + b'\x34\x56'
    else:
        cli.device.work_thread.eeprom_data = b'\x00' * 128
    result = cli.run(*cli.hardware_args('verify'))
    assert f'{memory.upper()} verification failed.' in result.stdout
    assert result.code == 1
    assert not cli.device.is_open


def test_program_verification_failure_returns_failure_and_closes_port(cli: CLI) -> None:
    cli.device.work_thread.response_overrides[(11, cli.expected.rom_data)] = b'\x00' * 2048
    result = cli.run(*cli.hardware_args('program'))
    assert 'ROM verification failed.' in result.stdout
    assert result.code == 1
    assert not cli.device.is_open


@pytest.mark.parametrize('binary', [False, True])
@pytest.mark.parametrize('memory', ['rom', 'eeprom', 'config'])
def test_dump_public_command_writes_requested_format(cli: CLI, memory: str, *, binary: bool) -> None:
    expected = {
        'rom': b'\x83\x12' + b'\xff\x3f' * 1022 + b'\x56\x34',
        'eeprom': b'\x11\x22' + b'\xff' * 126,
        'config': cli.config.to_bytes(),
    }[memory]
    result = cli.run('dump', memory, '-p', '/dev/fake', '-o', str(cli.output), '-t', '12f675', *(['--binary'] if binary else []))
    assert result.code == 0
    actual = cli.output.read_bytes() if binary else bytes(IntelHex(str(cli.output)).tobinarray())
    assert actual == expected
    assert not cli.device.is_open


def test_dump_chip_without_eeprom_creates_no_file(cli: CLI) -> None:
    result = cli.run('dump', 'eeprom', '-p', '/dev/fake', '-o', str(cli.output), '-t', '10f200')
    assert 'This chip has no EEPROM!' in result.stdout
    assert not cli.output.exists()
    assert not cli.device.is_open


def test_erase_changes_device_memory(cli: CLI) -> None:
    result = cli.run(*cli.hardware_args('erase'))
    assert result.code == 0
    assert 'Erasing chip...' in result.stdout
    assert cli.device.work_thread.rom_data is None
    assert cli.device.work_thread.eeprom_data is None
    assert cli.device.work_thread.chip_config is None
    assert not cli.device.is_open


def test_read_chip_config_output(cli: CLI) -> None:
    result = cli.run(*cli.hardware_args('read_chip_config'))
    assert result.code == 0
    assert 'Chip ID: 4032 (0xfc0)' in result.stdout
    assert 'ID:      3132333435363738' in result.stdout
    assert 'CAL:     13398' in result.stdout
    assert 'WDT = Enabled' in result.stdout
    assert not cli.device.is_open


def test_programmer_info_output(cli: CLI) -> None:
    result = cli.run('programmer_info', '-p', '/dev/fake')
    assert result.code == 0
    assert 'Firmware version: 3' in result.stdout
    assert 'Protocol version: P18A' in result.stdout
    assert not cli.device.is_open


@pytest.mark.parametrize(('error', 'message'), [
    (ConnectionError('Port unavailable'), 'Unable to open serial port "/dev/fake".'),
    (InvalidResponseError('bad reply'), 'Unable to initialize connection to programmer. bad reply'),
])
def test_programmer_info_connection_errors(cli: CLI, error: Exception, message: str) -> None:
    cli.serial_factory.side_effect = error
    result = cli.run('programmer_info', '-p', '/dev/fake')
    assert message in result.stdout
    assert 'Traceback' not in result.stderr


def test_migrate_command_writes_yaml_chip_definitions(cli: CLI, tmp_path: Path) -> None:
    cli.monkeypatch.chdir(tmp_path)
    output = tmp_path / 'picpro' / 'data' / 'chip-data.d'
    output.mkdir(parents=True)
    result = cli.run('chipdata_migrate')
    assert result.code == 0
    chips = ChipDataReader(output).chip_entries
    assert set(chips) == {'10f200', '16f737', '12f675'}
    assert chips['12f675'].rom_size == 2048
    assert chips['12f675'].socket_image == 'dip8'
    assert chips['10f200'].socket_image is None
    assert chips['16f737'].fuse_blank == [0x3fff, 0x3fff]
    cli.serial_factory.assert_not_called()


@pytest.mark.parametrize('verification_fails', [False, True])
def test_pic18_fuses_commit_only_after_successful_verification(cli: CLI, *, verification_fails: bool) -> None:
    packaged_cid = (_ROOT / 'picpro' / 'data' / 'chipdata.cid').read_text(encoding='utf-8')
    block = next(block for block in packaged_cid.split('\n\n') if block.startswith('CHIPname=18F2550\n'))
    with cli.database.open('a', encoding='utf-8') as database:
        database.write('\n\n' + block)
    chip = ChipInfoReader(cli.database).get_chip('18f2550')
    image = IntelHex()
    image.frombytes(b'\x34\x12')
    image.frombytes(b'\x11\x22\x33\x44', offset=0xf00000)
    image.write_hex_file(str(cli.image))
    expected = FlashData(chip, image)
    state = cli.device.work_thread
    state.chip_config = ChipConfig(chip_id=chip.chip_id, id=b'12345678', fuses=chip.fuse_blank, calibrate=0)
    if verification_fails:
        state.response_overrides[(11, expected.rom_data)] = b'\x00' * chip.rom_size

    result = cli.run('program', '-p', '/dev/fake', '-i', str(cli.image), '-t', '18f2550', '--id=0102030405060708')

    assert result.code == (1 if verification_fails else 0)
    assert state.chip_config is not None
    assert state.chip_config.id == bytes.fromhex('0102030405060708')
    assert state.rom_data == expected.rom_data
    assert state.eeprom_data == b'\x11\x22\x33\x44' + b'\xff' * 252
    if verification_fails:
        assert 'ROM verification failed.' in result.stdout
        assert 'Committing 18Fxxxx fuse data.' not in result.stdout
        assert state.chip_config.fuses == [0xffff] * 7
        assert state.pending_fuses == chip.fuse_blank
    else:
        assert 'ROM verified.' in result.stdout
        assert 'Committing 18Fxxxx fuse data.' in result.stdout
        assert state.chip_config.fuses == chip.fuse_blank
        assert state.pending_fuses is None
    assert not cli.device.is_open
