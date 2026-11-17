import dataclasses
import struct
from collections.abc import Callable

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
    id: MemoryRegion | None = None


@dataclasses.dataclass
class PaddedBuffer:
    data: bytes
    raw_size: int
    padding_size: int
    size: int

    def swab_bytes(self) -> None:
        self.data = swab_bytes(self.data)

class FlashData:
    calibration_word: bytes | None
    rom_buffer: PaddedBuffer
    eeprom_buffer: PaddedBuffer
    config_buffer: PaddedBuffer
    fuse_buffer: PaddedBuffer
    id_buffer: PaddedBuffer | None

    _memory_mapping: MemoryMapping

    def __init__(self, chip_info: ChipInfoEntry, hex_file: IntelHex, pic_id: str | None = None, fuses: dict | None = None) -> None:
        self.chip_info = chip_info
        self.hex_file = hex_file
        self.pic_id = pic_id
        self.fuses = fuses

        # Reset
        self.calibration_word = None
        self.id_buffer = None

        # Set memory map based on PIC architecture family
        # ROM region is always dynamic based on actual chip ROM size
        if self.chip_info.core_bits == 16:
            # PIC18 EEPROM stores packed bytes at 0xf00000.
            self._memory_mapping = MemoryMapping(
                rom=MemoryRegion(0x0000, self.chip_info.rom_size),  # Was hardcoded to 0x8000
                eeprom=MemoryRegion(0xf00000, 0xf00000 + self.chip_info.eeprom_size),
                config=MemoryRegion(0x300000, 0x30000e),
                id=MemoryRegion(0x200000, 0x200010),
            )
        elif self.chip_info.core_bits == 12:
            # 12-bit Baseline family (10F, 12F508, etc.)
            # Config/calibration typically beyond ROM, around 2*last_word_addr
            # We scan a conservative range that covers all baseline PICs
            self._memory_mapping = MemoryMapping(
                rom=MemoryRegion(0x0000, self.chip_info.rom_size),
                config=MemoryRegion(self.chip_info.rom_size, 0x2000),  # Scan after ROM up to 0x2000
                eeprom=MemoryRegion(0x4200, 0x4200 + self.chip_info.eeprom_size * 2),
            )
        else:  # core_bits == 14
            # 14-bit Midrange family (12F6xx, 16Fxxx)
            # Standard locations: Config at 0x2007 (byte 0x400E), User ID at 0x2000-0x2003, EEPROM at 0x2100+
            self._memory_mapping = MemoryMapping(
                rom=MemoryRegion(0x0000, self.chip_info.rom_size),  # Was hardcoded to 0x4000
                config=MemoryRegion(0x4000, max(0x4010, 0x400e + 2 * len(self.chip_info.fuse_blank))),  # Includes User ID (0x4000-0x4007) and Config (0x400E)
                eeprom=MemoryRegion(0x4200, 0x4200 + self.chip_info.eeprom_size * 2),
            )

        self.process()

    def _tobinarray_really(self, start: int, end: int, pad_callback: Callable[[int, int], int]) -> PaddedBuffer:
        """Return binary array."""
        buf = bytearray()
        raw_size = 0
        for index, address in enumerate(range(start, end)):
            found = self.hex_file._buf.get(address)  # noqa: SLF001
            if found is not None:
                raw_size += 1

            buf.append(found if found is not None else pad_callback(address, index))

        result_len = len(buf)
        if result_len % 2 != 0:
            msg = f'Result should have even len! ({result_len} % 2 != 0)'
            raise ValueError(msg)

        return PaddedBuffer(
            data=bytes(buf),
            raw_size=raw_size,
            padding_size=result_len-raw_size,
            size=result_len,
        )

    def _filter_records(self, *, little_endian: bool) -> None:
        word_format = '<H' if little_endian else '>H'
        rom_blank_word = struct.pack(word_format, self.chip_info.rom_blank_word)
        self._fuse_data_blank = b''.join(struct.pack(word_format, word) for word in self.chip_info.fuse_blank)
        self.rom_buffer = self._tobinarray_really(
            start=self._memory_mapping.rom.start,
            end=self._memory_mapping.rom.end,
            pad_callback=lambda _adr, i: rom_blank_word[i % 2],  # LoL, i % 2 returns 1/0 and rom_blank_word are two bytes with index 0 and 1 ;)
        )

        self.eeprom_buffer = self._tobinarray_really(
            start=self._memory_mapping.eeprom.start,
            end=self._memory_mapping.eeprom.end,
            pad_callback=lambda _adr, _i: 0x0FF,
        )

        self.config_buffer = self._tobinarray_really(
            start=self._memory_mapping.config.start,
            end=self._memory_mapping.config.end,
            pad_callback=lambda _adr, _i: 0x000,
        )

        if self.chip_info.core_bits == 16:
            self.fuse_buffer = self._tobinarray_really(
                start=0x300000,
                end=0x30000e,
                pad_callback=lambda _adr, i: self._fuse_data_blank[i],
            )
        else:
            self.fuse_buffer = self._tobinarray_really(
                start=0x400e,
                end=0x400e + len(self._fuse_data_blank),
                pad_callback=lambda _adr, i: self._fuse_data_blank[i],
            )

        if self._memory_mapping.id:
            self.id_buffer = self._tobinarray_really(
                start=self._memory_mapping.id.start,
                end=self._memory_mapping.id.end,
                pad_callback=lambda _adr, _i: 0x000,
            )

    def _is_little_endian(self) -> bool:
        if self.chip_info.core_bits == 16:
            return True

        # Infer byte order from supplied ROM bytes, never from padding.
        # Keep both candidates until all words have been validated; an early
        # decisive word must not hide invalid data later in the image.
        blank = self.chip_info.rom_blank_word
        be_ok = le_ok = True
        for address in range(self._memory_mapping.rom.start, self._memory_mapping.rom.end - 1, 2):
            first = self.hex_file._buf.get(address)  # noqa: SLF001
            second = self.hex_file._buf.get(address + 1)  # noqa: SLF001
            if first is None and second is None:
                continue
            be_word = ((first if first is not None else blank >> 8) << 8) | (second if second is not None else blank & 0xff)
            le_word = (first if first is not None else blank & 0xff) | ((second if second is not None else blank >> 8) << 8)
            be_ok = be_ok and (be_word & blank) == be_word
            le_ok = le_ok and (le_word & blank) == le_word
            if not (le_ok or be_ok):
                msg = 'Invalid ROM word.'
                raise ValueError(msg)
        # Default to little endian for ambiguous PIC HEX images.
        return le_ok

    def _validate_memory_sizes(self) -> None:
        # Bytes after ROM and before the next mapped region cannot belong to
        # this chip. Baseline chips may put user IDs immediately after ROM.
        region_starts = [self._memory_mapping.config.start, self._memory_mapping.eeprom.start]
        if self._memory_mapping.id is not None:
            region_starts.append(self._memory_mapping.id.start)
        rom_end = self._memory_mapping.rom.end
        rom_area_end = min((start for start in region_starts if start >= rom_end), default=rom_end)
        for address in self.hex_file.addresses():
            if rom_end <= address < rom_area_end:
                msg = f'ROM data at {address:#x} exceeds chip ROM size {rom_end} bytes.'
                raise ValueError(msg)
            if address >= self._memory_mapping.eeprom.end:
                msg = f'EEPROM data at {address:#x} exceeds chip EEPROM size {self.chip_info.eeprom_size} bytes.'
                raise ValueError(msg)

    def _unpack_eeprom_words(self, *, little_endian: bool) -> None:
        """Collapse midrange EEPROM words to one data byte each.

        INHX32 stores 12/14-bit EEPROM as one payload byte per 16-bit word.
        Little-endian files keep that byte first; big-endian files keep it second.
        """
        pick = 0 if little_endian else 1
        words = self.eeprom_buffer.data
        data = bytearray()
        raw_size = 0
        start = self._memory_mapping.eeprom.start
        for index in range(pick, len(words), 2):
            data.append(words[index])
            if self.hex_file._buf.get(start + index) is not None:  # noqa: SLF001
                raw_size += 1

        unpacked = bytes(data)
        self.eeprom_buffer = PaddedBuffer(
            data=unpacked,
            raw_size=raw_size,
            padding_size=len(unpacked) - raw_size,
            size=len(unpacked),
        )

    def process(self) -> None:
        self._validate_memory_sizes()
        is_swap_bytes = self._is_little_endian()
        self._filter_records(little_endian=is_swap_bytes)

        if is_swap_bytes:
            self.rom_buffer.swab_bytes()
            self.config_buffer.swab_bytes()
            self.fuse_buffer.swab_bytes()
            if self.id_buffer:
                self.id_buffer.swab_bytes()

        if self.chip_info.core_bits != 16:
            self._unpack_eeprom_words(little_endian=is_swap_bytes)

        # check Fuses
        if self.fuses:
            self.chip_info.encode_fuse_data(self.fuses)

    def set_calibration_word(self, calibration_word: bytes | None = None) -> None:
        if not self.chip_info.cal_word:
            msg = 'This chip does not have calibration in ROM data'
            raise ValueError(msg)

        if calibration_word is not None and len(calibration_word) != 2:
            msg = 'Calibration word must contain exactly 2 bytes.'
            raise ValueError(msg)
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
    def fuse_data(self) -> list[int]:
        fuse_values = [int(struct.unpack('>H', self.fuse_buffer.data[x:x + 2])[0]) for x in range(0, self.fuse_buffer.size, 2)]
        if self.fuses:
            fuse_settings = self.chip_info.decode_fuse_data(fuse_values)
            fuse_settings.update(self.fuses)
            fuse_values = self.chip_info.encode_fuse_data(fuse_settings)
        return fuse_values
