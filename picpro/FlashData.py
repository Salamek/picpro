import struct
from typing import Optional, Tuple, List

from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.HexFileReader import HexFileReader
from picpro.tools import range_filter_records, swab_record, merge_records


class FlashData:
    calibration_word: Optional[bytes]
    rom_records: List[Tuple[int, bytes]]
    eeprom_records: List[Tuple[int, bytes]]
    config_records: List[Tuple[int, bytes]]
    id_records: List[Tuple[int, bytes]]

    def __init__(self, chip_info: ChipInfoEntry, hex_file: HexFileReader, pic_id: Optional[str] = None, fuses: Optional[dict] = None):
        self.chip_info = chip_info
        self.hex_file = hex_file
        self.pic_id = pic_id
        self.fuses = fuses

        # Reset
        self.calibration_word = None
        self.rom_records = []
        self.eeprom_records = []
        self.config_records = []
        self.id_records = []

        self.core_bits = chip_info.core_bits
        self.rom_blank_word = self._calculate_rom_blank_word()
        self.rom_blank = struct.pack('>H', self.rom_blank_word) * chip_info.rom_size
        self.eeprom_blank = b'\xff' * chip_info.eeprom_size

        self.process()

    def _calculate_rom_blank_word(self) -> int:
        blank_word = 0xffff << self.core_bits
        return ~blank_word & 0xffff

    def _define_memory_regions(self) -> dict:
        if self.core_bits == 16:
            return {
                'rom': (0x0000, 0x8000),
                'eeprom': (0xf000, 0xf0ff),
                'config': (0x300000, 0x30000e),
                'id': (0x200000, 0x200010)
            }
        return {
            'rom': (0x0000, 0x4000),
            'config': (0x4000, 0x4010),
            'eeprom': (0x4200, 0xffff)
        }

    def _filter_records(self) -> None:
        regions = self._define_memory_regions()
        self.rom_records = range_filter_records(self.hex_file.records, *regions['rom'])
        self.config_records = range_filter_records(self.hex_file.records, *regions['config'])
        self.eeprom_records = range_filter_records(self.hex_file.records, *regions['eeprom'])

        if 'id' in regions:
            self.id_records = range_filter_records(self.hex_file.records, *regions['id'])

    def _is_little_endian(self) -> bool:
        if self.core_bits == 16:
            return True
        for record in self.rom_records:
            if record[0] % 2 != 0:
                raise ValueError('ROM record starts on odd address.')
            for x in range(0, len(record[1]), 2):
                if (x + 2) < len(record[1]):
                    be_word, = struct.unpack('>H', record[1][x:x + 2])
                    le_word, = struct.unpack('<H', record[1][x:x + 2])
                    be_ok = (be_word & self.rom_blank_word) == be_word
                    le_ok = (le_word & self.rom_blank_word) == le_word
                    if be_ok and not le_ok:
                        return False
                    if le_ok and not be_ok:
                        return True
                    if not (le_ok or be_ok):
                        raise ValueError('Invalid ROM word.')
        return False

    def process(self) -> None:
        self._filter_records()
        swap_bytes = self._is_little_endian()
        if swap_bytes:
            self.rom_records = [*map(swab_record, self.rom_records)]
            self.config_records = [*map(swab_record, self.config_records)]
            self.id_records = [*map(swab_record, self.id_records)]

        pick_byte = 0 if swap_bytes else 1
        self.eeprom_records = [
            (int(0x4200 + ((rec[0] - 0x4200) / 2)),
             bytes([rec[1][i] for i in range(pick_byte, len(rec[1]), 2)]))
            for rec in self.eeprom_records
        ]

        # check Fuses
        if self.fuses:
            self.chip_info.encode_fuse_data(self.fuses)

    def set_calibration_word(self, calibration_word: Optional[bytes] = None) -> None:
        if not self.chip_info.cal_word:
            raise ValueError('This chip does not have calibration in ROM data')

        self.calibration_word = calibration_word

    @property
    def rom_data(self) -> bytes:
        data = merge_records(self.rom_records, self.rom_blank)
        if self.calibration_word and self.chip_info.cal_word:
            # Patch calibration word into rom_data
            # @TODO add logging.info here
            return data[:len(data) - 2] + self.calibration_word

        return data

    @property
    def eeprom_data(self) -> bytes:
        return merge_records(self.eeprom_records, self.eeprom_blank, 0x4200)

    @property
    def id_data(self) -> bytes:
        if self.pic_id:
            return bytes.fromhex(self.pic_id)
        if self.core_bits == 16:
            id_data_raw = range_filter_records(self.id_records, 0x100000, 0x100008)
        else:
            id_data_raw = range_filter_records(self.config_records, 0x4000, 0x4008)
        id_data = merge_records(id_data_raw, b'\x00' * 8, 0x100000 if self.core_bits == 16 else 0x4000)
        return id_data if self.core_bits == 16 else bytes([id_data[x] for x in range(1, 8, 2)])

    @property
    def fuse_data(self) -> List[int]:  #@TODO migrate to bytes
        fuse_data_blank = b''.join(map(lambda word: struct.pack('>H', word), self.chip_info.fuse_blank))
        if self.core_bits == 16:
            fuse_config = range_filter_records(self.config_records, 0x300000, 0x30000e)
            fuse_data = merge_records(fuse_config, fuse_data_blank, 0x300000)
        else:
            fuse_config = range_filter_records(self.config_records, 0x400e, 0x4010)
            fuse_data = merge_records(fuse_config, fuse_data_blank, 0x400e)

        fuse_values = [int(struct.unpack('>H', fuse_data[x:x + 2])[0]) for x in range(0, len(fuse_data), 2)]
        if self.fuses:
            fuse_settings = self.chip_info.decode_fuse_data(fuse_values)
            fuse_settings.update(self.fuses)
            fuse_values = self.chip_info.encode_fuse_data(fuse_settings)
        return fuse_values
