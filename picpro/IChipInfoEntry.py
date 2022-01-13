from typing import Union
from picpro.ProgrammingVars import ProgrammingVars


class IChipInfoEntry:
    """Chip info entry interface"""

    @property
    def programming_vars(self) -> ProgrammingVars:
        """Returns a ProgrammingVars"""
        raise NotImplementedError

    def get_core_bits(self) -> Union[int, None]:
        """Returns a core bits"""
        raise NotImplementedError

    def decode_fuse_data(self, fuse_values: list) -> dict:
        """Given a list of fuse values, return a dict of symbolic
        (fuse : value) mapping representing the fuses that are set."""
        raise NotImplementedError

    def encode_fuse_data(self, fuse_dict: dict) -> list:
        raise NotImplementedError

    def has_eeprom(self) -> bool:
        raise NotImplementedError

    def pin1_location_text(self) -> str:
        raise NotImplementedError

    def fuse_doc(self) -> str:
        raise NotImplementedError

    def to_dict(self) -> dict:
        raise NotImplementedError
