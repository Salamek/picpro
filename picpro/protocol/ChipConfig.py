import struct
import dataclasses
from typing import List


@dataclasses.dataclass
class ChipConfig:
    chip_id: int
    id: bytes
    fuses: List[int]
    calibrate: int

    @classmethod
    def from_bytes(cls, data: bytes) -> 'ChipConfig':
        config = struct.unpack('<HccccccccHHHHHHHH', data)
        return cls(
            chip_id=config[0],
            id=b''.join(config[1:9]),
            fuses=list(config[9:16]),
            calibrate=config[16]
        )

    def to_bytes(self) -> bytes:
        return struct.pack(
            '<HccccccccHHHHHHHH',
            self.chip_id,
            self.id[0].to_bytes(1, byteorder='big'),
            self.id[1].to_bytes(1, byteorder='big'),
            self.id[2].to_bytes(1, byteorder='big'),
            self.id[3].to_bytes(1, byteorder='big'),
            self.id[4].to_bytes(1, byteorder='big'),
            self.id[5].to_bytes(1, byteorder='big'),
            self.id[6].to_bytes(1, byteorder='big'),
            self.id[7].to_bytes(1, byteorder='big'),
            self.fuses[0],
            self.fuses[1],
            self.fuses[2],
            self.fuses[3],
            self.fuses[4],
            self.fuses[5],
            self.fuses[6],
            self.calibrate
        )
