import ast
import importlib
import json
import os
import re
import runpy
import shutil
import subprocess
import sys
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

import pytest
import yaml
from intelhex import IntelHex
from serial import SerialException, SerialTimeoutException

from picpro import __version__
from picpro.ChipDataReader import ChipDataReader
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
        # Exercise the public entry point, including Typer argument parsing,
        # even when another test already imported the CLI.
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
    database = data_dir / 'chip-data.d'
    database.mkdir()
    packaged = _ROOT / 'picpro' / 'data' / 'chip-data.d'
    for name in ['10f200', '16f737', '12f675']:
        shutil.copy2(packaged / f'{name}.yml', database / f'{name}.yml')
    # A legacy file remains available only for explicit migration tests.
    (data_dir / 'chipdata.cid').write_bytes(chip_data_path.read_bytes())
    monkeypatch.setattr('platformdirs.user_data_dir', lambda _app: str(data_dir))
    image_path = tmp_path / 'firmware.hex'
    image = IntelHex()
    image.frombytes(b'\x83\x12')
    image.frombytes(b'\x01\x00\x02\x00\x03\x00\x04\x00', offset=0x4000)
    image.frombytes(b'\xff\x31', offset=0x400e)
    image.frombytes(b'\x11\x00\x22\x00', offset=0x4200)
    image.write_hex_file(str(image_path))
    chip = ChipDataReader(database).get_chip('12f675')
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
        assert 'program' in result.stdout
        assert 'Program a PIC chip' in result.stdout
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
    expected = str(image) if failure == 'missing_file' else 'Unable to find chip type "UNKNOWN"'
    assert result.code == 1
    assert expected in result.stderr
    assert 'Traceback' not in result.stderr
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


@pytest.mark.parametrize('protocol', [b'P014', b'P016', b'P018'])
def test_program_with_legacy_protocol(cli: CLI, protocol: bytes) -> None:
    cli.device.protocol = protocol
    result = cli.run(*cli.hardware_args('program'))
    assert result.code == 0
    assert result.stderr == ''
    assert 'ROM verified.' in result.stdout
    assert cli.device.work_thread.rom_data == cli.expected.rom_data


def test_legacy_unsupported_chip_reports_error_without_initializing(cli: CLI) -> None:
    cli.device.protocol = b'P016'
    result = cli.run('erase', '-p', '/dev/fake', '-t', '10f200', '--icsp')
    assert result.code == 1
    assert 'not supported by P016' in result.stderr
    assert 'Traceback' not in result.stderr
    assert cli.device.work_thread.programing_vars is None


@pytest.mark.parametrize('fuse', ['UNKNOWN:Enabled', 'WDT:unknown'])
def test_invalid_fuses_print_valid_choices_before_opening_port(cli: CLI, fuse: str) -> None:
    result = cli.run(*cli.hardware_args('program'), f'--fuse={fuse}')
    assert result.code == 1
    assert 'Traceback' not in result.stderr
    assert 'Invalid fuse setting.' in result.stderr
    assert "'WDT' : ('Enabled', 'Disabled')" in result.stderr
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
    assert f'{memory.upper()} verification failed.' in result.stderr
    assert result.code == 1
    assert not cli.device.is_open


def test_program_verification_failure_returns_failure_and_closes_port(cli: CLI) -> None:
    cli.device.work_thread.response_overrides[(11, cli.expected.rom_data)] = b'\x00' * 2048
    result = cli.run(*cli.hardware_args('program'))
    assert 'ROM verification failed.' in result.stderr
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
    result = cli.run('dump', 'eeprom', '-p', '/dev/fake', '-o', str(cli.output), '-t', '10f200', '--icsp')
    assert result.code == 1
    assert 'This chip has no EEPROM.' in result.stderr
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
    (ConnectionError('Port unavailable'), 'Unable to connect to programmer'),
    (InvalidResponseError('bad reply'), 'Invalid response from programmer'),
])
@pytest.mark.parametrize('command', ['programmer_info', 'verify'])
def test_connection_errors(cli: CLI, command: str, error: Exception, message: str) -> None:
    cli.serial_factory.side_effect = error
    args = ['programmer_info', '-p', '/dev/fake'] if command == 'programmer_info' else cli.hardware_args(command)
    result = cli.run(*args)
    assert result.code == 1
    assert f'{command}: {message}' in result.stderr
    assert str(error) in result.stderr
    assert 'Traceback' not in result.stderr


@pytest.mark.parametrize(('error', 'message'), [
    (InvalidResponseError('short ROM read'), 'Invalid response from programmer'),
    (SerialException('device disconnected'), 'Serial communication failed'),
    (SerialTimeoutException('write timeout'), 'Operation timed out'),
])
def test_read_failure_during_verification_closes_port(cli: CLI, error: Exception, message: str) -> None:
    with patch('picpro.protocol.p18a.ProgrammingInterface.ProgrammingInterface.read_rom', side_effect=error):
        result = cli.run(*cli.hardware_args('verify'))
    assert result.code == 1
    assert f'verify: {message}' in result.stderr
    assert str(error) in result.stderr
    assert 'Traceback' not in result.stderr
    assert not cli.device.is_open


@pytest.mark.parametrize('content', ['invalid record', ':02000000FFFF00\n:00000001FF\n'])
def test_bad_firmware_is_reported_before_opening_port(cli: CLI, content: str) -> None:
    cli.image.write_text(content, encoding='ascii')
    result = cli.run(*cli.hardware_args('verify'))
    assert result.code == 1
    assert f'Invalid firmware "{cli.image}"' in result.stderr
    assert 'Traceback' not in result.stderr
    cli.serial_factory.assert_not_called()


@pytest.mark.parametrize('pic_id', ['ZZ', '12', '0011223344'])
def test_invalid_pic_id_is_reported_before_opening_port(cli: CLI, pic_id: str) -> None:
    result = cli.run(*cli.hardware_args('program'), '--id', pic_id)
    assert result.code == 1
    assert 'PIC ID must' in result.stderr
    assert 'Traceback' not in result.stderr
    cli.serial_factory.assert_not_called()


def test_internal_key_error_propagates(cli: CLI) -> None:
    with patch('picpro.PicPro.PicPro.verify', side_effect=KeyError('internal state')), pytest.raises(KeyError, match='internal state'):
        cli.run(*cli.hardware_args('verify'))


def test_migrate_command_writes_yaml_chip_definitions(cli: CLI, tmp_path: Path) -> None:
    cli.monkeypatch.chdir(tmp_path)
    output = tmp_path / 'converted'
    result = cli.run('chipdata_migrate', str(cli.database.parent / 'chipdata.cid'), '--output', str(output))
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
    shutil.copy2(_ROOT / 'picpro' / 'data' / 'chip-data.d' / '18f2550.yml', cli.database / '18f2550.yml')
    chip = ChipDataReader(cli.database).get_chip('18f2550')
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
        assert 'ROM verification failed.' in result.stderr
        assert 'Committing 18Fxxxx fuse data.' not in result.stdout
        assert state.chip_config.fuses == [0xffff] * 7
        assert state.pending_fuses == chip.fuse_blank
    else:
        assert 'ROM verified.' in result.stdout
        assert 'Committing 18Fxxxx fuse data.' in result.stdout
        assert state.chip_config.fuses == chip.fuse_blank
        assert state.pending_fuses is None
    assert not cli.device.is_open


def test_normal_commands_use_yaml_without_parsing_legacy_cid(cli: CLI) -> None:
    # A broken legacy file must not affect normal commands after migration.
    (cli.database.parent / 'chipdata.cid').write_text('not a chip database', encoding='utf-8')
    chip_file = cli.database / '12f675.yml'
    data = yaml.safe_load(chip_file.read_text(encoding='utf-8'))
    data['program_delay'] = 42
    chip_file.write_text(yaml.safe_dump(data), encoding='utf-8')
    result = cli.run('chip_info', '12F675')
    assert result.code == 0
    assert json.loads(result.stdout)['program_delay'] == 42
    assert result.stderr == ''


def test_default_migration_uses_user_legacy_file_and_user_yaml_directory(cli: CLI) -> None:
    result = cli.run('chipdata_migrate')
    assert result.code == 0
    chips = ChipDataReader(cli.database).chip_entries
    assert set(chips) == {'10f200', '16f737', '12f675'}
    assert chips['12f675'].rom_size == 2048
    assert chips['12f675'].socket_image == 'dip8'


def test_packaged_yaml_cli_works_without_any_bundled_cid(tmp_path: Path) -> None:
    archive_path = tmp_path / 'picpro-yaml.zip'
    with ZipFile(archive_path, 'w') as archive:
        for path in (_ROOT / 'picpro').rglob('*'):
            if path.is_file() and path.suffix in ('.py', '.yml'):
                archive.write(path, path.relative_to(_ROOT))
    result = subprocess.run(
        [sys.executable, '-m', 'picpro', 'chip_info', '12F675'], cwd=tmp_path,
        env={**os.environ, 'PYTHONPATH': str(archive_path), 'XDG_DATA_HOME': str(tmp_path / 'user-data')},
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data['chip_name'] == '12f675'
    assert data['rom_size'] == 2048
    assert data['socket_image'] == 'dip8'


@pytest.mark.parametrize('command', [
    'program', 'verify', 'dump', 'erase', 'chip_info', 'hex_info',
    'programmer_info', 'decode_fuses', 'read_chip_config', 'chipdata_migrate',
])
def test_command_help_does_not_open_hardware(cli: CLI, command: str) -> None:
    result = cli.run(command, '--help')
    assert result.code == 0
    # Rich can style individual words in the usage line, including in GitHub Actions.
    help_text = re.sub(r'\x1b\[[0-9;]*m', '', result.stdout)
    assert f'Usage: picpro {command}' in help_text
    assert '--help' in help_text
    assert result.stderr == ''
    cli.serial_factory.assert_not_called()


@pytest.mark.parametrize('arguments', [
    [], ['program'], ['dump', 'unknown', '-p', '/dev/fake', '-t', '12f675', '-o', 'unused.hex'],
    ['program', '-p', '/dev/fake', '-t', '12f675', '-i', 'unused.hex', '--fuse=WDT'],
    ['program', '-p', '/dev/fake', '-t', '12f675', '-i', 'unused.hex', '--fuse=:Enabled'],
    ['program', '-p', '/dev/fake', '-t', '12f675', '-i', 'unused.hex', '--fuse=WDT:'],
    ['decode_fuses', 'not-a-number', '-t', '12f675'], ['chip_info', '--unknown'],
])
def test_invalid_arguments_report_usage_without_opening_hardware(cli: CLI, arguments: list[str]) -> None:
    result = cli.run(*arguments)
    assert result.code == 2
    assert 'Usage:' in result.stderr
    assert 'Traceback' not in result.stderr
    cli.serial_factory.assert_not_called()


def test_long_option_aliases_preserve_program_and_dump_behavior(cli: CLI) -> None:
    result = cli.run('program', '--port=/dev/fake', '--pic_type=12f675', '--hex_file', str(cli.image))
    assert result.code == 0
    assert 'ROM verified.' in result.stdout
    assert cli.device.work_thread.rom_data == cli.expected.rom_data


def test_long_dump_output_alias(cli: CLI) -> None:
    result = cli.run('dump', 'rom', '--port', '/dev/fake', '--pic_type', '12f675', '--hex_file', str(cli.output), '--binary')
    assert result.code == 0
    assert cli.output.read_bytes() == b'\x83\x12' + b'\xff\x3f' * 1022 + b'\x56\x34'
    assert f'Reading ROM into file {cli.output}...' in result.stdout


def test_typer_app_can_be_invoked_repeatedly(cli: CLI) -> None:
    from typer.testing import CliRunner  # noqa: PLC0415 - test the public Typer app directly

    module = importlib.import_module('picpro.bin.picpro')
    runner = CliRunner()
    for chip in ['12f675', '10f200']:
        result = runner.invoke(module.app, ['chip_info', chip])
        assert result.exit_code == 0
        assert json.loads(result.stdout)['chip_name'] == chip
    result = runner.invoke(module.app, ['-v'])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__
    cli.serial_factory.assert_not_called()


def test_importing_cli_does_not_parse_arguments_or_install_signal_handlers() -> None:
    code = (
        "import sys; from unittest.mock import patch; sys.argv = ['gui', '--unknown']; "
        "\nwith patch('signal.signal') as signal, patch('serial.Serial') as serial:"
        "\n import picpro.bin.picpro; signal.assert_not_called(); serial.assert_not_called()"
    )
    result = subprocess.run(  # noqa: S603 - fixed local executable and controlled test code
        [sys.executable, '-c', code], cwd=_ROOT,
        env={**os.environ, 'PYTHONPATH': str(_ROOT)}, capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ''
    assert result.stderr == ''


@pytest.mark.parametrize(('device_id', 'warn'), [(0x0fc0, False), (0x0fcb, False), (0x0fd0, False), (0x0f8b, True)])
def test_read_config_warns_for_device_id_mismatch(cli: CLI, device_id: int, *, warn: bool) -> None:
    cli.config.chip_id = device_id
    result = cli.run(*cli.hardware_args('read_chip_config'))
    assert result.code == 0
    if warn:
        assert 'Device ID mismatch for 12f675. Expected 0x0fc0, read 0x0f8b.' in result.stderr
    else:
        assert result.stderr == ''


def test_icsp_only_chip_requires_flag_before_opening_port(cli: CLI) -> None:
    chip_file = cli.database / '12f675.yml'
    definition = yaml.safe_load(chip_file.read_text(encoding='utf-8'))
    definition['icsp_only'] = True
    chip_file.write_text(yaml.safe_dump(definition), encoding='utf-8')
    args = cli.hardware_args('erase')

    result = cli.run(*args)
    assert result.code == 1
    assert '12f675 requires ICSP mode.' in result.stderr
    assert '--icsp' in result.stderr
    assert 'Traceback' not in result.stderr
    cli.serial_factory.assert_not_called()

    result = cli.run(*args, '--icsp')
    assert result.code == 0
    assert result.stderr == ''
    cli.serial_factory.assert_called_once()


def test_dump_all_writes_an_addressed_backup(cli: CLI) -> None:
    result = cli.run('dump', 'all', '-p', '/dev/fake', '-o', str(cli.output), '-t', '12f675')
    assert result.code == 0
    image = IntelHex(str(cli.output))
    assert [image[address] for address in (0, 1)] == [0x83, 0x12]
    assert [image[address] for address in (0x4000, 0x4001, 0x400e, 0x400f)] == [ord('1'), 0, 0xff, 0x31]
    assert [image[address] for address in (0x4200, 0x4201, 0x4202, 0x4203)] == [0x11, 0, 0x22, 0]
    cli.serial_factory.assert_called_once()


def test_dump_all_rejects_binary_before_opening_port(cli: CLI) -> None:
    result = cli.run('dump', 'all', '-p', '/dev/fake', '-o', str(cli.output), '-t', '12f675', '--binary')
    assert result.code == 2
    assert 'requires Intel HEX' in result.stderr
    cli.serial_factory.assert_not_called()
    assert not cli.output.exists()
