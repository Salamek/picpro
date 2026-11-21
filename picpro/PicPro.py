"""Synchronous application workflows shared by command-line and graphical clients."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Protocol

import platformdirs
import yaml
from intelhex import IntelHex
from yaml import ScalarNode

from picpro.ChipDataReader import ChipDataReader
from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.ChipInfoReader import ChipInfoReader
from picpro.exceptions import ICSPRequiredError, UnsupportedChipError
from picpro.FlashData import FlashData
from picpro.protocol.auto import open_connection
from picpro.protocol.ChipConfig import ChipConfig
from picpro.protocol.IConnection import IConnection
from picpro.protocol.IProgrammingInterface import IProgrammingInterface


@dataclass(frozen=True)
class Target:
    port: str
    chip_name: str
    icsp: bool = False


class MemoryType(StrEnum):
    ROM = 'rom'
    EEPROM = 'eeprom'
    CONFIG = 'config'


class Stage(StrEnum):
    CONNECTING = 'connecting'
    INITIALIZING = 'initializing'
    READING_CONFIG = 'reading_config'
    PRESERVING_CALIBRATION = 'preserving_calibration'
    ERASING = 'erasing'
    ERASED = 'erased'
    ERASE_SKIPPED = 'erase_skipped'
    PROGRAMMING_ROM = 'programming_rom'
    PROGRAMMING_EEPROM = 'programming_eeprom'
    PROGRAMMING_FUSES = 'programming_fuses'
    VERIFYING_ROM = 'verifying_rom'
    VERIFYING_EEPROM = 'verifying_eeprom'
    COMMITTING_FUSES = 'committing_fuses'
    READING_ROM = 'reading_rom'
    READING_EEPROM = 'reading_eeprom'
    COMPLETED = 'completed'


@dataclass(frozen=True)
class StageEvent:
    stage: Stage


@dataclass(frozen=True)
class ChipConfigEvent:
    chip: ChipInfoEntry
    config: ChipConfig

    @property
    def device_id_mismatch(self) -> bool:
        # The chip database excludes the five low revision bits.
        # A definition with 0xffff has no device ID to compare.
        expected = self.chip.chip_id
        return expected != 0xffff and (self.config.chip_id & 0xffe0) != expected


@dataclass(frozen=True)
class VerificationEvent:
    memory: MemoryType
    expected: bytes
    actual: bytes
    maybe_locked: bool = False

    @property
    def matches(self) -> bool:
        return self.actual == self.expected


@dataclass(frozen=True)
class VerificationResult:
    rom_matches: bool
    eeprom_matches: bool | None
    maybe_locked: bool = False

    @property
    def success(self) -> bool:
        return self.rom_matches and self.eeprom_matches is not False


@dataclass(frozen=True)
class ProgrammerInfo:
    firmware_version: int
    protocol: str


class OperationCancelledError(Exception):
    """Cooperative cancellation at a device-command boundary."""


class NoEEPROMError(ValueError):
    """The selected target has no EEPROM."""


class ChipRepository(Protocol):
    def get_chip(self, name: str) -> ChipInfoEntry: ...

    @property
    def chip_entries(self) -> dict[str, ChipInfoEntry]: ...


PicProEvent = StageEvent | ChipConfigEvent | VerificationEvent
EventHandler = Callable[[PicProEvent], None]
CancellationCheck = Callable[[], bool]

_LEGACY_LIMITS = {b'P014': (10, 5), b'P016': (10, 5), b'P018': (11, 7)}


class PicPro:
    """One blocking operation per call; callers own worker threads and presentation.

    Event handlers run synchronously on the calling thread. Handler exceptions
    propagate and unwind open connections. Cancellation is checked between
    device commands; transfers and erase commands currently finish atomically.
    """

    def __init__(self, *, chip_data: ChipRepository | None = None, connection_factory: Callable[[str], IConnection] | None = None,
                 on_event: EventHandler | None = None) -> None:
        self._chip_data = chip_data
        self._connection_factory = connection_factory if connection_factory is not None else open_connection
        self._on_event = on_event

    @staticmethod
    def find_chip_data() -> Path | Traversable:
        locations: list[Path | Traversable] = [
            Path(platformdirs.user_data_dir('picpro')) / 'chip-data.d',
            Path('/usr/share/picpro/chip-data.d'),
            Path(__file__).parent / 'chip-data.d',
            files('picpro') / 'data' / 'chip-data.d',
        ]
        for directory in locations:
            if directory.is_dir():
                return directory
        msg = "YAML chip data directory 'chip-data.d' was not found in any search path."
        raise FileNotFoundError(msg)

    @staticmethod
    def find_legacy_chip_data() -> Path | Traversable:
        locations: list[Path | Traversable] = [
            Path(platformdirs.user_data_dir('picpro')) / 'chipdata.cid',
            Path('/usr/share/picpro/chipdata.cid'),
            Path(__file__).parent / 'chipdata.cid',
            files('picpro') / 'data' / 'chipdata.cid',
        ]
        for path in locations:
            if path.is_file():
                return path
        msg = "File 'chipdata.cid' was not found in any search path."
        raise FileNotFoundError(msg)

    @property
    def chip_data(self) -> ChipRepository:
        if self._chip_data is None:
            self._chip_data = ChipDataReader(self.find_chip_data())
        return self._chip_data

    def list_chips(self) -> dict[str, ChipInfoEntry]:
        return self.chip_data.chip_entries

    def get_chip(self, name: str) -> ChipInfoEntry:
        return self.chip_data.get_chip(name)

    def inspect_hex(self, chip_name: str, hex_file: Path, *, pic_id: str | None = None, fuses: dict[str, str] | None = None) -> FlashData:
        image = IntelHex(str(hex_file))
        return FlashData(deepcopy(self.get_chip(chip_name)), image, pic_id=pic_id, fuses=dict(fuses) if fuses is not None else None)

    def decode_fuses(self, chip_name: str, fuses: list[int]) -> dict:
        return self.get_chip(chip_name).decode_fuse_data(fuses)

    def _emit(self, event: PicProEvent) -> None:
        if self._on_event is not None:
            self._on_event(event)

    @staticmethod
    def _check_cancel(should_cancel: CancellationCheck | None) -> None:
        if should_cancel is not None and should_cancel():
            raise OperationCancelledError

    def _stage(self, stage: Stage, should_cancel: CancellationCheck | None) -> None:
        self._check_cancel(should_cancel)
        self._emit(StageEvent(stage))
        self._check_cancel(should_cancel)

    @contextmanager
    def _interface(self, target: Target, chip: ChipInfoEntry, should_cancel: CancellationCheck | None) -> Iterator[IProgrammingInterface]:
        if chip.icsp_only and not target.icsp:
            msg = f'{chip.chip_name} requires ICSP mode.'
            raise ICSPRequiredError(msg)
        self._stage(Stage.CONNECTING, should_cancel)
        with self._connection_factory(target.port) as connection:
            self._stage(Stage.INITIALIZING, should_cancel)
            protocol = connection.expected_programmer_protocol
            if protocol in _LEGACY_LIMITS:
                variables = chip.programming_variables
                max_core, max_erase = _LEGACY_LIMITS[protocol]
                if chip.core_type == 'newf12b' or not 1 <= variables.core_type <= max_core or not 0 <= variables.erase_mode <= max_erase:
                    msg = f'{chip.chip_name} has programming parameters not supported by {protocol.decode()}.'
                    raise UnsupportedChipError(msg)
            with connection.get_programming_interface(chip, icsp_mode=target.icsp) as interface:
                yield interface

    def _config(self, interface: IProgrammingInterface, chip: ChipInfoEntry, should_cancel: CancellationCheck | None) -> ChipConfig:
        self._stage(Stage.READING_CONFIG, should_cancel)
        config = interface.read_config()
        self._emit(ChipConfigEvent(deepcopy(chip), deepcopy(config)))
        return config

    def _preserve_calibration(self, data: FlashData, config: ChipConfig, should_cancel: CancellationCheck | None) -> None:
        if data.chip_info.cal_word:
            self._stage(Stage.PRESERVING_CALIBRATION, should_cancel)
            data.set_calibration_word(config.calibrate.to_bytes(2, 'big'))

    def _verify(self, interface: IProgrammingInterface, data: FlashData, should_cancel: CancellationCheck | None) -> VerificationResult:
        self._stage(Stage.VERIFYING_ROM, should_cancel)
        actual_rom = interface.read_rom()
        rom_matches = actual_rom == data.rom_data
        zeros = actual_rom.count(b'\x00')
        expected_zeros = len(actual_rom) - 2 if data.chip_info.cal_word else len(actual_rom)
        maybe_locked = not rom_matches and zeros == expected_zeros
        self._emit(VerificationEvent(MemoryType.ROM, data.rom_data, actual_rom, maybe_locked))
        eeprom_matches = None
        if data.chip_info.has_eeprom:
            self._stage(Stage.VERIFYING_EEPROM, should_cancel)
            actual_eeprom = interface.read_eeprom()
            eeprom_matches = actual_eeprom == data.eeprom_data
            self._emit(VerificationEvent(MemoryType.EEPROM, data.eeprom_data, actual_eeprom))
        return VerificationResult(rom_matches, eeprom_matches, maybe_locked)

    def program(self, target: Target, hex_file: Path, *, pic_id: str | None = None, fuses: dict[str, str] | None = None,
                should_cancel: CancellationCheck | None = None) -> VerificationResult:
        self._check_cancel(should_cancel)
        data = self.inspect_hex(target.chip_name, hex_file, pic_id=pic_id, fuses=fuses)
        id_data = data.id_data
        with self._interface(target, data.chip_info, should_cancel) as interface:
            config = self._config(interface, data.chip_info, should_cancel)
            self._preserve_calibration(data, config, should_cancel)
            if data.chip_info.flash_chip:
                self._stage(Stage.ERASING, should_cancel)
                interface.erase_chip()
                self._stage(Stage.ERASED, should_cancel)
            else:
                self._stage(Stage.ERASE_SKIPPED, should_cancel)
            self._stage(Stage.PROGRAMMING_ROM, should_cancel)
            interface.cycle_programming_voltages()
            interface.program_rom(data.rom_data)
            if data.chip_info.has_eeprom:
                self._stage(Stage.PROGRAMMING_EEPROM, should_cancel)
                interface.program_eeprom(data.eeprom_data)
            self._stage(Stage.PROGRAMMING_FUSES, should_cancel)
            transaction = interface.program_id_fuses(id_data, data.fuse_data)
            result = self._verify(interface, data, should_cancel)
            if not result.success:
                return result
            if transaction is not None:
                self._stage(Stage.COMMITTING_FUSES, should_cancel)
                transaction.program_18fxxxx_fuse(data.fuse_data)
        self._stage(Stage.COMPLETED, should_cancel)
        return result

    def verify(self, target: Target, hex_file: Path, *, should_cancel: CancellationCheck | None = None) -> VerificationResult:
        self._check_cancel(should_cancel)
        data = self.inspect_hex(target.chip_name, hex_file)
        with self._interface(target, data.chip_info, should_cancel) as interface:
            config = self._config(interface, data.chip_info, should_cancel)
            self._preserve_calibration(data, config, should_cancel)
            result = self._verify(interface, data, should_cancel)
        if result.success:
            self._stage(Stage.COMPLETED, should_cancel)
        return result

    def erase(self, target: Target, *, should_cancel: CancellationCheck | None = None) -> None:
        chip = self.get_chip(target.chip_name)
        with self._interface(target, chip, should_cancel) as interface:
            self._stage(Stage.ERASING, should_cancel)
            interface.erase_chip()
        self._stage(Stage.COMPLETED, should_cancel)

    def read_config(self, target: Target, *, should_cancel: CancellationCheck | None = None) -> ChipConfig:
        chip = self.get_chip(target.chip_name)
        with self._interface(target, chip, should_cancel) as interface:
            config = self._config(interface, chip, should_cancel)
        self._stage(Stage.COMPLETED, should_cancel)
        return config

    def read_memory(self, target: Target, memory: MemoryType, *, should_cancel: CancellationCheck | None = None) -> bytes:
        memory = MemoryType(memory)
        chip = self.get_chip(target.chip_name)
        with self._interface(target, chip, should_cancel) as interface:
            if memory == MemoryType.EEPROM:
                if not chip.has_eeprom:
                    raise NoEEPROMError
                self._stage(Stage.READING_EEPROM, should_cancel)
                data = interface.read_eeprom()
            elif memory == MemoryType.ROM:
                self._stage(Stage.READING_ROM, should_cancel)
                data = interface.read_rom()
            else:
                self._stage(Stage.READING_CONFIG, should_cancel)
                data = interface.read_config().to_bytes()
        self._stage(Stage.COMPLETED, should_cancel)
        return data

    def read_backup(self, target: Target, *, should_cancel: CancellationCheck | None = None) -> IntelHex:
        """Read programmable regions in one session and return an Intel HEX image."""
        chip = self.get_chip(target.chip_name)
        with self._interface(target, chip, should_cancel) as interface:
            config = self._config(interface, chip, should_cancel)
            self._stage(Stage.READING_ROM, should_cancel)
            rom = interface.read_rom()
            eeprom = b''
            if chip.has_eeprom:
                self._stage(Stage.READING_EEPROM, should_cancel)
                eeprom = interface.read_eeprom()
        image = FlashData.backup_image(chip, rom, eeprom, config)
        self._stage(Stage.COMPLETED, should_cancel)
        return image

    def programmer_info(self, port: str, *, should_cancel: CancellationCheck | None = None) -> ProgrammerInfo:
        self._stage(Stage.CONNECTING, should_cancel)
        with self._connection_factory(port) as connection:
            self._check_cancel(should_cancel)
            info = ProgrammerInfo(connection.programmer_version(), connection.programmer_protocol().decode('UTF-8'))
        self._stage(Stage.COMPLETED, should_cancel)
        return info

    @staticmethod
    def migrate_chip_data(source: Path | Traversable | None = None, output_dir: Path | None = None) -> Path:
        chip_info_reader = ChipInfoReader(source if source is not None else PicPro.find_legacy_chip_data())
        output_dir = output_dir if output_dir is not None else Path(platformdirs.user_data_dir('picpro')) / 'chip-data.d'
        output_dir.mkdir(parents=True, exist_ok=True)

        def hex_string_representer(dumper: yaml.Dumper, data: str) -> ScalarNode:
            if isinstance(data, str) and data.startswith('0x'):
                return dumper.represent_scalar('tag:yaml.org,2002:int', hex(int(data, 16)))
            return dumper.represent_scalar('tag:yaml.org,2002:str', data)

        class HexStringDumper(yaml.Dumper):  # pylint: disable=too-many-ancestors
            pass

        HexStringDumper.add_representer(str, hex_string_representer)

        socket_image_to_dip = {
            '8pin': 'dip8',
            '14pin': 'dip14',
            '18pin': 'dip18',
            '28Npin': 'dip28',
            '40pin': 'dip40',
        }

        for chip_name, chip_entry in chip_info_reader.chip_entries.items():
            chip_name_lower = chip_name.lower()
            file_path = output_dir.joinpath(f'{chip_name_lower}.yml')
            with file_path.open('w', encoding='utf-8') as f:
                data = chip_entry.to_dict()
                data['chip_id'] = hex(chip_entry.chip_id)
                data['core_type'] = chip_entry.core_type.lower()
                data['chip_name'] = chip_name_lower
                data['socket_image'] = socket_image_to_dip[chip_entry.socket_image] if not chip_entry.icsp_only and chip_entry.socket_image else None

                fuse_blank = {}
                for index, fuse in enumerate(chip_entry.fuse_blank):
                    fuse_blank[index] = hex(fuse)

                data['fuses_blank'] = fuse_blank
                del data['fuse_blank']
                del data['fuses']
                fuses: dict[str, dict[str, dict[int, int]]] = {}

                for fuse_name, fuse_options in chip_entry.fuses.items():
                    for option_name, options in fuse_options.items():
                        fuses.setdefault(fuse_name, {})
                        option_values = dict(options)
                        fuses[fuse_name].setdefault(option_name, option_values)

                data['fuses'] = fuses

                yaml.dump(data, f, Dumper=HexStringDumper, sort_keys=False)
        return output_dir
