from typing import cast
from unittest.mock import create_autospec

import pytest

from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.protocol.IConnection import IConnection
from picpro.protocol.IProgrammingInterface import IProgrammingInterface


class ProgrammingInterfaceProbe(IProgrammingInterface):
    """Implement lifecycle hooks while retaining the base programming operations."""

    def _init_programming_vars(self, *, icsp_mode: bool = False) -> None:
        self.initialized_connection = self.connection
        self.initialized_chip = self.chip_info
        self.icsp_mode = icsp_mode
        self.close_count = 0

    def close(self) -> None:
        self.close_count += 1


@pytest.fixture
def connection() -> IConnection:
    return cast('IConnection', create_autospec(IConnection, instance=True))


@pytest.fixture
def interface(connection: IConnection, chip_info_entry: ChipInfoEntry) -> ProgrammingInterfaceProbe:
    return ProgrammingInterfaceProbe(connection, chip_info_entry)


def test_initialization_defaults_to_socket_mode(interface: ProgrammingInterfaceProbe, connection: IConnection,
                                               chip_info_entry: ChipInfoEntry) -> None:
    assert interface.connection is connection
    assert interface.chip_info is chip_info_entry
    assert interface.icsp_mode is False


@pytest.mark.parametrize('icsp_mode', [False, True])
def test_initialization_passes_state_to_hook(connection: IConnection, chip_info_entry: ChipInfoEntry, *, icsp_mode: bool) -> None:
    interface = ProgrammingInterfaceProbe(connection, chip_info_entry, icsp_mode=icsp_mode)
    assert interface.initialized_connection is connection
    assert interface.initialized_chip is chip_info_entry
    assert interface.icsp_mode is icsp_mode


def test_initialization_requires_implementation(connection: IConnection, chip_info_entry: ChipInfoEntry) -> None:
    with pytest.raises(NotImplementedError):
        IProgrammingInterface(connection, chip_info_entry)


@pytest.mark.parametrize(('method', 'args', 'kwargs'), [
    ('set_programming_voltages_command', (), {'on': True}),
    ('cycle_programming_voltages', (), {}),
    ('program_rom', (b'\x12\x34',), {}),
    ('program_eeprom', (b'\x12\x34',), {}),
    ('program_id_fuses', (b'1234', [0x3fff]), {}),
    ('program_calibration', (0x1234, 0x3fff), {}),
    ('read_rom', (), {}),
    ('read_eeprom', (), {}),
    ('read_config', (), {}),
    ('erase_chip', (), {}),
    ('rom_is_blank', (b'\x3f',), {}),
    ('eeprom_is_blank', (), {}),
    ('program_debug_vector', (0x123456,), {}),
    ('read_debug_vector', (), {}),
])
def test_operations_require_implementation(interface: ProgrammingInterfaceProbe, method: str, args: tuple, kwargs: dict[str, bool]) -> None:
    with pytest.raises(NotImplementedError):
        getattr(interface, method)(*args, **kwargs)


def test_close_requires_implementation(interface: ProgrammingInterfaceProbe) -> None:
    with pytest.raises(NotImplementedError):
        IProgrammingInterface.close(interface)


def test_context_manager_closes_interface(interface: ProgrammingInterfaceProbe) -> None:
    with interface as active:
        assert active is interface
        assert interface.close_count == 0
    assert interface.close_count == 1


def test_context_manager_closes_on_error_and_preserves_exception(interface: ProgrammingInterfaceProbe) -> None:
    error = RuntimeError('Programming failed')
    with pytest.raises(RuntimeError, match='Programming failed') as exc, interface:
        raise error
    assert exc.value is error
    assert interface.close_count == 1
