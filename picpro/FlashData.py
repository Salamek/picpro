import dataclasses
import struct
from typing import Optional, List, Callable
from intelhex import IntelHex
from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.tools import swab_bytes


@dataclasses.dataclass
class MemoryRegion:
    start: int
    end: int

@dataclasses.dataclass
class MemoryMapping:
    rom: MemoryRegion
    eeprom: MemoryRegion
    config: MemoryRegion
    id: Optional[MemoryRegion] = None


@dataclasses.dataclass
class PaddedBuffer:
    data: bytes
    raw_size: int
    padding_size: int
    size: int

    def swab_bytes(self) -> None:
        self.data = swab_bytes(self.data)

class FlashData:
    calibration_word: Optional[bytes]
    rom_buffer: PaddedBuffer
    eeprom_buffer: PaddedBuffer
    config_buffer: PaddedBuffer
    fuse_buffer: PaddedBuffer
    id_buffer: Optional[PaddedBuffer]

    _memory_mapping: MemoryMapping

    def __init__(self, chip_info: ChipInfoEntry, hex_file: IntelHex, pic_id: Optional[str] = None, fuses: Optional[dict] = None):
        self.chip_info = chip_info
        self.hex_file = hex_file
        self.pic_id = pic_id
        self.fuses = fuses

        # Reset
        self.calibration_word = None
        self.id_buffer = None

        self._rom_blank_word = self._calculate_rom_blank_word()
        self._fuse_data_blank = b''.join(map(lambda word: struct.pack('>H', word), self.chip_info.fuse_blank))

        # Set memory map based on PIC architecture family
        # ROM region is always dynamic based on actual chip ROM size
        rom_size_bytes = self.chip_info.rom_size * 2

        if self.chip_info.core_bits == 16:
            # 16-bit Baseline family
            self._memory_mapping = MemoryMapping(
                rom=MemoryRegion(0x0000, rom_size_bytes),  # Was hardcoded to 0x8000
                eeprom=MemoryRegion(0xf000, 0xf100),
                config=MemoryRegion(0x300000, 0x30000e),
                id=MemoryRegion(0x200000, 0x200010)
            )
        elif self.chip_info.core_bits == 12:
            # 12-bit Baseline family (10F, 12F508, etc.)
            # Config/calibration typically beyond ROM, around 2*last_word_addr
            # We scan a conservative range that covers all baseline PICs
            self._memory_mapping = MemoryMapping(
                rom=MemoryRegion(0x0000, rom_size_bytes),
                config=MemoryRegion(rom_size_bytes, 0x2000),  # Scan after ROM up to 0x2000
                eeprom=MemoryRegion(0x2100 * 2, 0x2100 * 2 + max(self.chip_info.eeprom_size, 256)),  # 0x4200+
            )
        else:  # core_bits == 14
            # 14-bit Midrange family (12F6xx, 16Fxxx)
            # Standard locations: Config at 0x2007 (byte 0x400E), User ID at 0x2000-0x2003, EEPROM at 0x2100+
            self._memory_mapping = MemoryMapping(
                rom=MemoryRegion(0x0000, rom_size_bytes),  # Was hardcoded to 0x4000
                config=MemoryRegion(0x4000, 0x4010),  # Includes User ID (0x4000-0x4007) and Config (0x400E)
                eeprom=MemoryRegion(0x4200, 0x4200 + max(self.chip_info.eeprom_size, 256)),  # Was hardcoded to 0xffff
            )

        self.process()

    def _tobinarray_really(self, start: int, end: int, pad_callback: Callable[[int, int], int], max_size: Optional[int] = None) -> PaddedBuffer:
        """Return binary array."""
        buf = bytearray()
        raw_size = 0
        for index, address in enumerate(range(start, end)):
            found = self.hex_file._buf.get(address)
            if found is not None:
                raw_size += 1

            if max_size is not None and found and index > max_size:
                raise ValueError('Range contains data over expected max_size')

            if max_size is None or index < max_size:
                buf.append(found if found is not None else pad_callback(address, index))

        result_len = len(buf)
        if result_len % 2 != 0:
            raise ValueError('Result should have even len! ({} % 2 != 0)'.format(result_len))

        return PaddedBuffer(
            data=bytes(buf),
            raw_size=raw_size,
            padding_size=result_len-raw_size,
            size=result_len
        )


    def _calculate_rom_blank_word(self) -> int:
        blank_word = 0xffff << self.chip_info.core_bits
        return ~blank_word & 0xffff

    def _filter_records(self) -> None:
        rom_blank_word = struct.pack('<H', self._rom_blank_word)
        self.rom_buffer = self._tobinarray_really(
            start=self._memory_mapping.rom.start,
            end=self._memory_mapping.rom.end,
            max_size=(self.chip_info.rom_size * 2), # Makes _tobinarray_really to rise ValueError if there are data in given range over expected size of chip
            pad_callback=lambda adr, i: rom_blank_word[i % 2]  # LoL, i % 2 returns 1/0 and rom_blank_word are two bytes with index 0 and 1 ;)
        )

        self.eeprom_buffer = self._tobinarray_really(
            start=self._memory_mapping.eeprom.start,
            end=self._memory_mapping.eeprom.end,
            max_size=self.chip_info.eeprom_size,
            pad_callback=lambda adr, i: 0x0FF
        )

        self.config_buffer = self._tobinarray_really(
            start=self._memory_mapping.config.start,
            end=self._memory_mapping.config.end,
            pad_callback=lambda adr, i: 0x000
        )

        if self.chip_info.core_bits == 16:
            self.fuse_buffer = self._tobinarray_really(
                start=0x300000,
                end=0x30000e,
                pad_callback=lambda adr, i: self._fuse_data_blank[i]
            )
        else:
            self.fuse_buffer = self._tobinarray_really(
                start=0x400e,
                end=0x4010,
                pad_callback=lambda adr, i: self._fuse_data_blank[i]
            )

        if self._memory_mapping.id:
            self.id_buffer = self._tobinarray_really(
                start=self._memory_mapping.id.start,
                end=self._memory_mapping.id.end,
                pad_callback=lambda adr, i: 0x000
            )

    def _is_little_endian(self) -> bool:
        if self.chip_info.core_bits == 16:
            return True

        for x in range(0, self.rom_buffer.size, 2):
            if (x + 2) < self.rom_buffer.size:
                be_word, = struct.unpack('>H', self.rom_buffer.data[x:x + 2])
                le_word, = struct.unpack('<H', self.rom_buffer.data[x:x + 2])
                be_ok = (be_word & self._rom_blank_word) == be_word
                le_ok = (le_word & self._rom_blank_word) == le_word
                if be_ok and not le_ok:
                    return False
                if le_ok and not be_ok:
                    return True
                if not (le_ok or be_ok):
                    raise ValueError('Invalid ROM word.')
        return False

    def process(self) -> None:
        self._filter_records()
        is_swap_bytes = self._is_little_endian()

        if is_swap_bytes:
            self.rom_buffer.swab_bytes()
            self.config_buffer.swab_bytes()
            self.eeprom_buffer.swab_bytes()
            self.fuse_buffer.swab_bytes()
            if self.id_buffer:
                self.id_buffer.swab_bytes()


        # pick_byte = 0 if is_swap_bytes else 1
        # self.eeprom_records = [
        #     (int(0x4200 + ((rec[0] - 0x4200) / 2)),
        #     bytes([rec[1][i] for i in range(pick_byte, len(rec[1]), 2)]))
        #     for rec in self.eeprom_records
        # ]


        # check Fuses
        if self.fuses:
            self.chip_info.encode_fuse_data(self.fuses)

    def set_calibration_word(self, calibration_word: Optional[bytes] = None) -> None:
        if not self.chip_info.cal_word:
            raise ValueError('This chip does not have calibration in ROM data')

        self.calibration_word = calibration_word

    @property
    def rom_data(self) -> bytes:
        if self.calibration_word and self.chip_info.cal_word:
            return self.rom_buffer.data[:self.rom_buffer.size - 2] + self.calibration_word
        return self.rom_buffer.data

    @property
    def eeprom_data(self) -> bytes:
        return self.eeprom_buffer.data

    @property
    def id_data(self) -> bytes:
        if self.pic_id:
            return bytes.fromhex(self.pic_id)

        id_data = self.id_buffer.data[:8] if self.id_buffer else self.config_buffer.data[:8]
        return id_data if self.chip_info.core_bits == 16 else bytes([id_data[x] for x in range(1, 8, 2)])

    @property
    def fuse_data(self) -> List[int]:
        fuse_values = [int(struct.unpack('>H', self.fuse_buffer.data[x:x + 2])[0]) for x in range(0, self.fuse_buffer.size, 2)]
        if self.fuses:
            fuse_settings = self.chip_info.decode_fuse_data(fuse_values)
            fuse_settings.update(self.fuses)
            fuse_values = self.chip_info.encode_fuse_data(fuse_settings)
        return fuse_values
