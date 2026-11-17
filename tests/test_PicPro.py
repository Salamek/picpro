import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from unittest.mock import MagicMock, create_autospec

import pytest
from intelhex import IntelHex

from picpro.ChipDataReader import ChipDataReader
from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.PicPro import (
    ChipConfigEvent,
    MemoryType,
    NoEEPROMError,
    OperationCancelledError,
    PicPro,
    PicProEvent,
    Stage,
    StageEvent,
    Target,
    VerificationEvent,
)
from picpro.protocol.ChipConfig import ChipConfig
from picpro.protocol.IConnection import IConnection
from picpro.protocol.IFuseTransaction import IFuseTransaction
from picpro.protocol.IProgrammingInterface import IProgrammingInterface


class Repository:
    def __init__(self, chip: ChipInfoEntry) -> None:
        self.chip_entries = {chip.chip_name: chip}

    def get_chip(self, name: str) -> ChipInfoEntry:
        return self.chip_entries[name.lower()]


@dataclass
class ServiceFixture:
    service: PicPro
    repository: Repository
    factory: MagicMock
    connection: MagicMock
    interface: MagicMock
    events: list[PicProEvent]
    target: Target
    image: Path
    chip: ChipInfoEntry


@pytest.fixture
def service_fixture(tmp_path: Path, chip_info_entry: ChipInfoEntry) -> ServiceFixture:
    chip = replace(chip_info_entry)
    image = tmp_path / 'image.hex'
    hex_data = IntelHex()
    hex_data.frombytes(b'\x83\x12')
    hex_data.write_hex_file(str(image))
    repository = Repository(chip)
    connection = create_autospec(IConnection, instance=True)
    connection.__enter__.return_value = connection
    interface = create_autospec(IProgrammingInterface, instance=True)
    interface.__enter__.return_value = interface
    connection.get_programming_interface.return_value = interface
    interface.read_config.return_value = ChipConfig(chip.chip_id, b'12345678', list(chip.fuse_blank) + [0] * 6, 0x3456)
    interface.program_id_fuses.return_value = None
    factory = MagicMock(return_value=connection)
    events: list[PicProEvent] = []
    service = PicPro(chip_data=repository, connection_factory=factory, on_event=events.append)
    expected = service.inspect_hex(chip.chip_name, image)
    expected.set_calibration_word(b'\x34\x56')
    interface.read_rom.return_value = expected.rom_data
    interface.read_eeprom.return_value = expected.eeprom_data
    return ServiceFixture(service, repository, factory, connection, interface, events, Target('/dev/fake', chip.chip_name, icsp=True), image, chip)


def test_importing_service_does_not_run_cli_or_open_ports() -> None:
    code = "import sys; sys.argv = ['gui', '--not-cli-arguments']; import picpro.PicPro; assert 'picpro.bin.picpro' not in sys.modules"
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=10, check=False)  # noqa: S603 - controlled local code
    assert result.returncode == 0, result.stderr
    assert result.stdout == ''
    assert result.stderr == ''


def test_chip_queries_and_inspection_do_not_open_hardware(service_fixture: ServiceFixture) -> None:
    f = service_fixture
    assert f.service.list_chips() == {f.chip.chip_name: f.chip}
    assert f.service.get_chip(f.chip.chip_name.upper()) is f.chip
    data = f.service.inspect_hex(f.chip.chip_name, f.image)
    assert data.rom_data[:2] == b'\x12\x83'
    assert f.service.decode_fuses(f.chip.chip_name, [0x31ff])['WDT'] == 'Enabled'
    f.factory.assert_not_called()


def test_default_repository_reads_bundled_yaml() -> None:
    service = PicPro()
    assert service.get_chip('12F675').chip_name == '12f675'
    assert service.get_chip('12F675').socket_image == 'dip8'


def test_program_returns_verification_and_preserves_calibration(service_fixture: ServiceFixture, capsys: pytest.CaptureFixture[str]) -> None:
    f = service_fixture
    result = f.service.program(f.target, f.image)
    assert result.success
    assert result.rom_matches
    assert result.eeprom_matches
    f.factory.assert_called_once_with('/dev/fake')
    f.connection.get_programming_interface.assert_called_once_with(f.chip, icsp_mode=True)
    programmed = f.interface.program_rom.call_args.args[0]
    assert programmed[:2] == b'\x12\x83'
    assert programmed[-2:] == b'\x34\x56'
    assert f.events[0] == StageEvent(Stage.CONNECTING)
    assert f.events[-1] == StageEvent(Stage.COMPLETED)
    stages = [event.stage for event in f.events if isinstance(event, StageEvent)]
    assert stages.index(Stage.ERASING) < stages.index(Stage.PROGRAMMING_ROM) < stages.index(Stage.VERIFYING_ROM)
    assert any(isinstance(event, ChipConfigEvent) for event in f.events)
    assert any(isinstance(event, VerificationEvent) and event.matches for event in f.events)
    f.interface.__exit__.assert_called_once()
    f.connection.__exit__.assert_called_once()
    assert capsys.readouterr().out == ''


@pytest.mark.parametrize('mismatch', ['rom', 'eeprom'])
def test_verification_mismatches_are_results_not_process_exits(service_fixture: ServiceFixture, mismatch: str) -> None:
    f = service_fixture
    if mismatch == 'rom':
        f.interface.read_rom.return_value = b'\x00' * (f.chip.rom_size - 2) + b'\x34\x56'
    else:
        f.interface.read_eeprom.return_value = b'\x00' * f.chip.eeprom_size
    result = f.service.verify(f.target, f.image)
    assert not result.success
    assert result.rom_matches is (mismatch != 'rom')
    assert result.eeprom_matches is (mismatch != 'eeprom')
    assert result.maybe_locked is (mismatch == 'rom')
    assert StageEvent(Stage.COMPLETED) not in f.events
    f.connection.__exit__.assert_called_once()


@pytest.mark.parametrize('verified', [False, True])
def test_pic18_transaction_waits_for_verification(service_fixture: ServiceFixture, yaml_chip_data_path: Path, *, verified: bool) -> None:
    f = service_fixture
    chip = ChipDataReader(yaml_chip_data_path).get_chip('18f2550')
    repository = Repository(chip)
    service = PicPro(chip_data=repository, connection_factory=f.factory, on_event=f.events.append)
    data = service.inspect_hex(chip.chip_name, f.image)
    f.interface.read_rom.return_value = data.rom_data if verified else b'\x00' * chip.rom_size
    f.interface.read_eeprom.return_value = data.eeprom_data
    transaction = create_autospec(IFuseTransaction, instance=True)
    f.interface.program_id_fuses.return_value = transaction
    result = service.program(replace(f.target, chip_name=chip.chip_name), f.image, pic_id='0102030405060708')
    assert result.success is verified
    if verified:
        transaction.program_18fxxxx_fuse.assert_called_once_with(chip.fuse_blank)
    else:
        transaction.program_18fxxxx_fuse.assert_not_called()
    f.connection.__exit__.assert_called_once()


@pytest.mark.parametrize('stage', [Stage.CONNECTING, Stage.INITIALIZING, Stage.PROGRAMMING_ROM, Stage.COMMITTING_FUSES])
def test_cancellation_from_event_stops_before_next_command(service_fixture: ServiceFixture, stage: Stage) -> None:
    f = service_fixture
    cancelled = False

    def observe(event: PicProEvent) -> None:
        nonlocal cancelled
        if event == StageEvent(stage):
            cancelled = True

    if stage == Stage.COMMITTING_FUSES:
        f.interface.program_id_fuses.return_value = create_autospec(IFuseTransaction, instance=True)
    service = PicPro(chip_data=f.repository, connection_factory=f.factory, on_event=observe)
    with pytest.raises(OperationCancelledError):
        service.program(f.target, f.image, should_cancel=lambda: cancelled)
    if stage == Stage.CONNECTING:
        f.factory.assert_not_called()
    else:
        f.connection.__exit__.assert_called_once()
    if stage in (Stage.CONNECTING, Stage.INITIALIZING, Stage.PROGRAMMING_ROM):
        f.interface.program_rom.assert_not_called()
        f.interface.cycle_programming_voltages.assert_not_called()
    if stage == Stage.COMMITTING_FUSES:
        f.interface.program_id_fuses.return_value.program_18fxxxx_fuse.assert_not_called()


def test_pre_cancelled_program_never_reads_image_or_opens_port(service_fixture: ServiceFixture) -> None:
    f = service_fixture
    with pytest.raises(OperationCancelledError):
        f.service.program(f.target, f.image.with_name('missing.hex'), should_cancel=lambda: True)
    f.factory.assert_not_called()


@pytest.mark.parametrize('stage', [Stage.INITIALIZING, Stage.PROGRAMMING_ROM, Stage.COMPLETED])
def test_observer_exceptions_propagate_with_connection_cleanup(service_fixture: ServiceFixture, stage: Stage) -> None:
    f = service_fixture
    error = RuntimeError('Observer failed')

    def observe(event: PicProEvent) -> None:
        if event == StageEvent(stage):
            raise error

    service = PicPro(chip_data=f.repository, connection_factory=f.factory, on_event=observe)
    with pytest.raises(RuntimeError, match='Observer failed') as exc:
        service.program(f.target, f.image)
    assert exc.value is error
    f.connection.__exit__.assert_called_once()


def test_config_events_are_snapshots_not_mutable_workflow_inputs(service_fixture: ServiceFixture) -> None:
    f = service_fixture

    def observe(event: PicProEvent) -> None:
        if isinstance(event, ChipConfigEvent):
            event.config.calibrate = 0
            event.chip.cal_word = False

    service = PicPro(chip_data=f.repository, connection_factory=f.factory, on_event=observe)
    assert service.program(f.target, f.image).success
    assert f.interface.program_rom.call_args.args[0][-2:] == b'\x34\x56'
    assert f.chip.cal_word


def test_device_exception_unwinds_both_context_managers(service_fixture: ServiceFixture) -> None:
    f = service_fixture
    error = OSError('Disconnected')
    f.interface.program_rom.side_effect = error
    with pytest.raises(OSError, match='Disconnected'):
        f.service.program(f.target, f.image)
    f.interface.__exit__.assert_called_once()
    f.connection.__exit__.assert_called_once()


@pytest.mark.parametrize(('memory', 'method', 'expected'), [
    (MemoryType.ROM, 'read_rom', b'\x12\x34'),
    (MemoryType.EEPROM, 'read_eeprom', b'\x11\x22'),
])
def test_read_memory_returns_device_bytes_without_export_formatting(service_fixture: ServiceFixture, memory: MemoryType, method: str, expected: bytes) -> None:
    f = service_fixture
    getattr(f.interface, method).return_value = expected
    assert f.service.read_memory(f.target, memory) == expected
    assert f.events[-1] == StageEvent(Stage.COMPLETED)
    f.connection.__exit__.assert_called_once()


def test_read_config_and_config_memory(service_fixture: ServiceFixture) -> None:
    f = service_fixture
    expected = f.interface.read_config.return_value
    assert f.service.read_config(f.target) is expected
    assert f.service.read_memory(f.target, MemoryType.CONFIG) == expected.to_bytes()


def test_no_eeprom_raises_domain_error_and_releases_device(service_fixture: ServiceFixture) -> None:
    f = service_fixture
    f.chip.eeprom_size = 0
    with pytest.raises(NoEEPROMError):
        f.service.read_memory(f.target, MemoryType.EEPROM)
    f.interface.read_eeprom.assert_not_called()
    f.connection.__exit__.assert_called_once()


def test_erase_and_programmer_info(service_fixture: ServiceFixture) -> None:
    f = service_fixture
    f.service.erase(f.target)
    f.interface.erase_chip.assert_called_once_with()
    f.connection.programmer_version.return_value = 3
    f.connection.programmer_protocol.return_value = b'P18A'
    info = f.service.programmer_info('/dev/fake')
    assert info.firmware_version == 3
    assert info.protocol == 'P18A'


@pytest.mark.parametrize('setting', ['no_eeprom', 'no_calibration', 'not_erasable'])
def test_program_respects_chip_capabilities(service_fixture: ServiceFixture, setting: str) -> None:
    f = service_fixture
    if setting == 'no_eeprom':
        f.chip.eeprom_size = 0
    elif setting == 'no_calibration':
        f.chip.cal_word = False
        f.interface.read_rom.return_value = f.service.inspect_hex(f.chip.chip_name, f.image).rom_data
    else:
        f.chip.flash_chip = False
    assert f.service.program(f.target, f.image).success
    if setting == 'no_eeprom':
        f.interface.program_eeprom.assert_not_called()
        f.interface.read_eeprom.assert_not_called()
    elif setting == 'no_calibration':
        assert StageEvent(Stage.PRESERVING_CALIBRATION) not in f.events
    else:
        f.interface.erase_chip.assert_not_called()
        assert StageEvent(Stage.ERASE_SKIPPED) in f.events


def test_events_are_optional(service_fixture: ServiceFixture, capsys: pytest.CaptureFixture[str]) -> None:
    f = service_fixture
    service = PicPro(chip_data=f.repository, connection_factory=f.factory)
    assert service.program(f.target, f.image).success
    assert capsys.readouterr().out == ''


def test_interface_initialization_error_releases_connection(service_fixture: ServiceFixture) -> None:
    f = service_fixture
    error = OSError('Initialization failed')
    f.connection.get_programming_interface.side_effect = error
    with pytest.raises(OSError, match='Initialization failed'):
        f.service.program(f.target, f.image)
    f.connection.__exit__.assert_called_once()


def test_program_snapshots_fuse_options_before_notifying_observers(service_fixture: ServiceFixture) -> None:
    f = service_fixture
    options = {'WDT': 'Disabled'}

    def observe(event: PicProEvent) -> None:
        if isinstance(event, ChipConfigEvent):
            options['WDT'] = 'Enabled'

    service = PicPro(chip_data=f.repository, connection_factory=f.factory, on_event=observe)
    assert service.program(f.target, f.image, fuses=options).success
    assert f.interface.program_id_fuses.call_args.args[1] == [0x31f7]


def test_programmer_info_supports_pre_cancellation(service_fixture: ServiceFixture) -> None:
    f = service_fixture
    with pytest.raises(OperationCancelledError):
        f.service.programmer_info('/dev/fake', should_cancel=lambda: True)
    f.factory.assert_not_called()
