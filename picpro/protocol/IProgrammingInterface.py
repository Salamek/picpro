from types import TracebackType
from typing import Optional, Type, List, TYPE_CHECKING

from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.protocol.IConnection import IConnection
from picpro.protocol.ChipConfig import ChipConfig

if TYPE_CHECKING:
    from picpro.protocol.IFuseTransaction import IFuseTransaction


class IProgrammingInterface:

    def __init__(self, connection: IConnection, chip_info: ChipInfoEntry, icsp_mode: bool = False):
        self.connection = connection
        self.chip_info = chip_info
        self._init_programming_vars(icsp_mode)

    def _init_programming_vars(self, icsp_mode: bool = False) -> None:
        raise NotImplementedError

    def set_programming_voltages_command(self, on: bool) -> None:
        raise NotImplementedError

    def cycle_programming_voltages(self) -> None:
        raise NotImplementedError

    def program_rom(self, data: bytes) -> None:
        """Write data to ROM.  data should be a binary string of data, high byte first."""
        raise NotImplementedError

    def program_eeprom(self, data: bytes) -> None:
        """Write data to EEPROM.  Data size must be small enough to fit in EEPROM."""
        raise NotImplementedError

    def program_id_fuses(self, pic_id: bytes, fuses: List[int]) -> Optional['IFuseTransaction']:
        """Program PIC ID and fuses.  For 16-bit processors, fuse values
        are not committed until program_18fxxxx_fuse() is called."""
        raise NotImplementedError

    def program_calibration(self, calibrate: int, fuse: int) -> None:
        """Program calibration"""
        raise NotImplementedError

    def read_rom(self) -> bytes:
        """Returns contents of PIC ROM as a string of big-endian values."""
        raise NotImplementedError

    def read_eeprom(self) -> bytes:
        """Returns data stored in PIC EEPROM."""
        raise NotImplementedError

    def read_config(self) -> ChipConfig:
        """Reads chip ID and programmed ID, fuses, and calibration."""
        raise NotImplementedError

    def erase_chip(self) -> None:
        """Erases all data from chip."""
        raise NotImplementedError

    def rom_is_blank(self, high_byte: bytes) -> bool:
        """Returns True if PIC ROM is blank."""
        raise NotImplementedError

    def eeprom_is_blank(self) -> bool:
        """Returns True if PIC EEPROM is blank."""
        raise NotImplementedError

    def program_debug_vector(self, address: bytes) -> None:
        """Sets the PIC's debugging vector."""
        raise NotImplementedError

    def read_debug_vector(self) -> bytes:
        """Returns the value of the PIC's debugging vector."""
        raise NotImplementedError


    def close(self) -> None:
        raise NotImplementedError

    def __enter__(self) -> 'IProgrammingInterface':
        return self

    def __exit__(self, exc_type: Optional[Type[BaseException]],
                 exc_value: Optional[BaseException],
                 traceback: Optional[TracebackType]) -> None:
        self.close()
