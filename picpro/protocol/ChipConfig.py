import dataclasses
from typing import List


@dataclasses.dataclass
class ChipConfig:
    chip_id: int
    id: bytes
    fuses: List[int]
    calibrate: int
