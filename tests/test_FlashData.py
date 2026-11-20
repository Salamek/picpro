
from dataclasses import replace
from io import StringIO
from pathlib import Path
from typing import Literal

import pytest
from intelhex import IntelHex

from picpro.ChipDataReader import ChipDataReader
from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.exceptions import FuseError
from picpro.FlashData import FlashData, PaddedBuffer


def test_be_constructed_with(chip_info_entry: ChipInfoEntry, hex_file: IntelHex) -> None:
    FlashData(chip_info_entry, hex_file)


def test_rom_data(flash_data: FlashData) -> None:
    expected = bytes.fromhex('280f3fff3fff3fff00a0080300a11283180c2877082100830ea00e2000090064168330080085019f308c00811283100510851105160516853007009923ff1683009012833020008401800a841f84282430100090207c1683140c1283170b141001b0178b301402301c0328321285138b0063000000641985283701b0207c178b19852837301402301c03284001b101b21005108511051832140518b214851932150501b0300102301c032852120501b0300502301c03285816050ab2300806321d03284801b01d85286a301402301c03286328370ab1300a06311d03284701b01d85286f301402301c03287028370064100c0ab0207c280a30af008e303c008f0008') + b'\x3f\xff' * 895
    assert flash_data.rom_data == expected


def test_eeprom_data(flash_data: FlashData) -> None:
    expected = b'\xff' * 128
    assert flash_data.eeprom_data == expected


def test_id_data(flash_data: FlashData) -> None:
    expected = bytes.fromhex('0000070f')
    assert flash_data.id_data == expected


def test_fuse_data(flash_data: FlashData) -> None:
    expected = [16204]
    assert flash_data.fuse_data == expected


@pytest.fixture
def small_chip(chip_info_entry: ChipInfoEntry) -> ChipInfoEntry:
    return replace(chip_info_entry, rom_size=64, eeprom_size=4, fuse_blank=[0x3fff], fuses={
        'WDT': {'Enabled': [(0, 0x3fff)], 'Disabled': [(0, 0x3ff7)]},
        'MCLRE': {'Enabled': [(0, 0x3fff)], 'Disabled': [(0, 0x3fdf)]},
    })


@pytest.mark.parametrize(('core', 'blank', 'fuses'), [
    ('newf12b', b'\x0f\xff', [0x0fff]),
    ('bit14_b', b'\x3f\xff', [0x3fff]),
    ('bit16_b', b'\xff\xff', [0xffff] * 7),
])
def test_empty_image(small_chip: ChipInfoEntry, core: str, blank: bytes, fuses: list[int]) -> None:
    chip = replace(small_chip, core_type=core, fuse_blank=fuses)
    data = FlashData(chip, IntelHex())
    assert data.rom_data == blank * 32
    assert data.rom_buffer.raw_size == 0
    assert data.rom_buffer.padding_size == 64
    assert data.rom_buffer.size == 64
    assert data.eeprom_data == b'\xff' * 4
    assert data.eeprom_buffer.raw_size == 0
    assert data.eeprom_buffer.padding_size == 4
    assert data.fuse_data == fuses
    assert data.id_data == b'\x00' * (8 if core == 'bit16_b' else 4)


@pytest.mark.parametrize('little_endian', [False, True])
def test_sparse_rom_normalized_and_padded(small_chip: ChipInfoEntry, *, little_endian: bool) -> None:
    image = IntelHex()
    image.frombytes(b'\x83\x12' if little_endian else b'\x12\x83', offset=4)
    before = image.todict()
    data = FlashData(small_chip, image)
    assert data.rom_data == b'\x3f\xff' * 2 + b'\x12\x83' + b'\x3f\xff' * 29
    assert data.rom_buffer.raw_size == 2
    assert data.rom_buffer.padding_size == 62
    assert data.rom_buffer.size == 64
    assert image.todict() == before
    data.process()
    assert data.rom_data == b'\x3f\xff' * 2 + b'\x12\x83' + b'\x3f\xff' * 29


@pytest.mark.parametrize('little_endian', [False, True])
def test_last_rom_word_determines_byte_order(small_chip: ChipInfoEntry, *, little_endian: bool) -> None:
    image = IntelHex()
    image.frombytes(b'\x00' * 62 + (b'\x83\x12' if little_endian else b'\x12\x83'))
    assert FlashData(small_chip, image).rom_data == b'\x00' * 62 + b'\x12\x83'


@pytest.mark.parametrize('address', [0, 62])
def test_invalid_rom_word_rejected(small_chip: ChipInfoEntry, address: int) -> None:
    image = IntelHex()
    image.frombytes(b'\x83\x12' + b'\x00' * 62)
    image.frombytes(b'\xff\xff', offset=address)
    with pytest.raises(ValueError, match='Invalid ROM word'):
        FlashData(small_chip, image)


def test_ambiguous_rom_defaults_to_little_endian(small_chip: ChipInfoEntry) -> None:
    image = IntelHex()
    image.frombytes(b'\x01\x00' * 32)
    assert FlashData(small_chip, image).rom_data == b'\x00\x01' * 32


@pytest.mark.parametrize('offset', [8, 9])
@pytest.mark.parametrize('value', [0, 0x12])
def test_eeprom_overflow_rejected(small_chip: ChipInfoEntry, offset: int, value: int) -> None:
    with pytest.raises(ValueError, match='exceeds chip EEPROM size'):
        FlashData(small_chip, IntelHex({0x4200 + offset: value}))


def test_eeprom_on_chip_without_eeprom_rejected(small_chip: ChipInfoEntry) -> None:
    chip = replace(small_chip, eeprom_size=0)
    with pytest.raises(ValueError, match='exceeds chip EEPROM size'):
        FlashData(chip, IntelHex({0x4200: 0}))


def test_eeprom_boundary_and_explicit_zero(small_chip: ChipInfoEntry) -> None:
    image = IntelHex({0: 0x83, 1: 0x12, 0x4206: 0x12, 0x4207: 0})
    data = FlashData(small_chip, image)
    assert data.eeprom_data == b'\xff\xff\xff\x12'
    assert data.eeprom_buffer.raw_size == 1
    assert data.eeprom_buffer.padding_size == 3
    assert data.eeprom_buffer.size == 4


def test_odd_buffer_size_rejected(small_chip: ChipInfoEntry) -> None:
    with pytest.raises(ValueError, match='even len'):
        FlashData(replace(small_chip, rom_size=63), IntelHex())


def test_zero_eeprom_size(small_chip: ChipInfoEntry) -> None:
    data = FlashData(replace(small_chip, eeprom_size=0), IntelHex())
    assert data.eeprom_data == b''
    assert data.eeprom_buffer == PaddedBuffer(data=b'', raw_size=0, padding_size=0, size=0)


@pytest.mark.parametrize('little_endian', [False, True])
def test_default_and_partial_fuse_padding(small_chip: ChipInfoEntry, *, little_endian: bool) -> None:
    chip = replace(small_chip, fuse_blank=[0x31ff])
    image = IntelHex()
    image.frombytes(b'\x83\x12' if little_endian else b'\x12\x83')
    assert FlashData(chip, image).fuse_data == [0x31ff]
    # Only the byte containing the changed fuse bits is present in HEX.
    image[0x400e if little_endian else 0x400f] = 0xf7
    data = FlashData(chip, image)
    assert data.fuse_data == [0x31f7]
    assert data.fuse_buffer.raw_size == 1
    assert data.fuse_buffer.padding_size == 1


def test_multiple_midrange_fuse_words(small_chip: ChipInfoEntry) -> None:
    chip = replace(small_chip, fuse_blank=[0x3fff, 0x3fff])
    image = IntelHex({0: 0x83, 1: 0x12})
    image.frombytes(b'\xf7\x3f\xfe\x3f', offset=0x400e)
    data = FlashData(chip, image)
    assert data.fuse_data == [0x3ff7, 0x3ffe]
    assert data.fuse_buffer.raw_size == 4


def test_pic18_buffers(small_chip: ChipInfoEntry) -> None:
    fuses = [0x1234, 0xabcd, 0x5678, 0x4321, 0x8765, 0xfedc, 0x2468]
    chip = replace(small_chip, core_type='bit16_b', fuse_blank=[0xffff] * 7)
    image = IntelHex()
    image.frombytes(b'\x34\x12')
    image.frombytes(b'\x21\x43\x65\x87\xa9\xcb\xed\x0f', offset=0x200000)
    image.frombytes(b''.join(value.to_bytes(2, 'little') for value in fuses), offset=0x300000)
    data = FlashData(chip, image)
    assert data.rom_data[:2] == b'\x12\x34'
    assert data.id_data == bytes.fromhex('43218765cba90fed')
    assert data.fuse_data == fuses
    assert data.id_buffer is not None
    assert data.id_buffer.raw_size == 8


@pytest.mark.parametrize('core', ['newf12b', 'bit14_b'])
def test_user_id_from_configuration(small_chip: ChipInfoEntry, core: str) -> None:
    chip = replace(small_chip, core_type=core)
    start = 64 if core == 'newf12b' else 0x4000
    image = IntelHex()
    image.frombytes(b'\x23\x01')
    image.frombytes(b'\x01\x00\x02\x00\x03\x00\x04\x00', offset=start)
    assert FlashData(chip, image).id_data == b'\x01\x02\x03\x04'


def test_pic12c508a_reads_configuration_word_from_issue_4(yaml_chip_data_path: Path) -> None:
    chip = ChipDataReader(yaml_chip_data_path).get_chip('12c508a')
    image = IntelHex(StringIO(
        ':080000002500C70C0200660098\n'
        ':080400000800080009000100DA\n'
        ':021FFE00EA0FE8\n'
        ':00000001FF\n',
    ))
    data = FlashData(chip, image)
    assert data.rom_buffer.raw_size == 8
    assert data.id_data == bytes.fromhex('08080901')
    assert data.fuse_data == [0x0fea]


def test_explicit_id_overrides_hex(small_chip: ChipInfoEntry) -> None:
    data = FlashData(small_chip, IntelHex(), pic_id='01 23 AB cd')
    assert data.id_data == b'\x01\x23\xab\xcd'


def test_invalid_id_hex(small_chip: ChipInfoEntry) -> None:
    data = FlashData(small_chip, IntelHex(), pic_id='invalid')
    with pytest.raises(ValueError, match='hexadecimal byte pairs'):
        _ = data.id_data


def test_fuse_override_preserves_other_settings(small_chip: ChipInfoEntry) -> None:
    image = IntelHex({0: 0x83, 1: 0x12, 0x400e: 0xdf, 0x400f: 0x3f})
    overrides = {'WDT': 'Disabled'}
    data = FlashData(small_chip, image, fuses=overrides)
    assert data.fuse_data == [0x3fd7]
    assert overrides == {'WDT': 'Disabled'}
    assert small_chip.fuse_blank == [0x3fff]
    assert image[0x400e] == 0xdf


@pytest.mark.parametrize('overrides', [{'UNKNOWN': 'Enabled'}, {'WDT': 'invalid'}])
def test_invalid_fuse_override_rejected(small_chip: ChipInfoEntry, overrides: dict) -> None:
    with pytest.raises(FuseError):
        FlashData(small_chip, IntelHex(), fuses=overrides)


@pytest.mark.parametrize('word', [b'\x12\x34', b'\x00\x00'])
def test_calibration_replaces_last_word_only(small_chip: ChipInfoEntry, word: bytes) -> None:
    data = FlashData(small_chip, IntelHex())
    original = data.rom_data
    data.set_calibration_word(word)
    assert data.rom_data == original[:-2] + word
    assert len(data.rom_data) == 64
    assert data.rom_buffer.data == original
    data.set_calibration_word()
    assert data.rom_data == original


def test_calibration_unsupported(small_chip: ChipInfoEntry) -> None:
    data = FlashData(replace(small_chip, cal_word=False), IntelHex())
    with pytest.raises(ValueError, match='does not have calibration'):
        data.set_calibration_word(b'\x12\x34')


@pytest.mark.parametrize('word', [b'', b'\x12', b'\x12\x34\x56'])
def test_calibration_must_be_one_word(small_chip: ChipInfoEntry, word: bytes) -> None:
    data = FlashData(small_chip, IntelHex())
    with pytest.raises(ValueError, match='2 bytes'):
        data.set_calibration_word(word)


def test_padded_buffer_swap_preserves_sizes() -> None:
    buffer = PaddedBuffer(data=b'\x12\x34\xab\xcd', raw_size=2, padding_size=2, size=4)
    buffer.swab_bytes()
    assert buffer == PaddedBuffer(data=b'\x34\x12\xcd\xab', raw_size=2, padding_size=2, size=4)


@pytest.mark.parametrize(('source', 'expected'), [
    ({0: 0x83}, b'\x3f\x83'), ({1: 0x12}, b'\x12\xff'), ({0: 0}, b'\x3f\x00'),
])
def test_partial_rom_words(small_chip: ChipInfoEntry, source: dict[int, int], expected: bytes) -> None:
    data = FlashData(small_chip, IntelHex(source))
    assert data.rom_data == expected + b'\x3f\xff' * 31
    assert data.rom_buffer.raw_size == 1
    assert data.rom_buffer.padding_size == 63


def test_partial_big_endian_rom_word(small_chip: ChipInfoEntry) -> None:
    data = FlashData(small_chip, IntelHex({0: 0x12, 1: 0x83, 4: 0x12}))
    assert data.rom_data == b'\x12\x83\x3f\xff\x12\xff' + b'\x3f\xff' * 29


def test_pic18_sparse_fuse_defaults(small_chip: ChipInfoEntry) -> None:
    defaults = [0xcf3f, 0x1f3f, 0x8700, 0x00e5, 0xc00f, 0xe00f, 0x400f]
    chip = replace(small_chip, core_type='bit16_b', fuse_blank=defaults)
    data = FlashData(chip, IntelHex({0x300003: 0x0f}))
    assert data.fuse_data == [0xcf3f, 0x0f3f, 0x8700, 0x00e5, 0xc00f, 0xe00f, 0x400f]
    assert data.fuse_buffer.raw_size == 1
    assert data.fuse_buffer.padding_size == 13
    assert chip.fuse_blank == defaults


@pytest.mark.parametrize(('core', 'rom_size'), [('bit14_b', 64), ('bit16_b', 64), ('bit16_b', 0x10000)])
@pytest.mark.parametrize('offset', [0, 1])
@pytest.mark.parametrize('value', [0, 0x12])
def test_rom_overflow_rejected(small_chip: ChipInfoEntry, core: str, rom_size: int, offset: int, value: int) -> None:
    chip = replace(small_chip, core_type=core, rom_size=rom_size)
    with pytest.raises(ValueError, match='exceeds chip ROM size'):
        FlashData(chip, IntelHex({rom_size + offset: value}))


# Regression contributed by cfgnunes in https://github.com/Salamek/picpro/pull/55.
def test_eeprom_little_endian_words_are_unpacked(chip_info_entry: ChipInfoEntry, hex_file: IntelHex) -> None:
    intel_hex = IntelHex(hex_file.todict())
    intel_hex[0x4200] = 0x11
    intel_hex[0x4201] = 0x00
    intel_hex[0x4202] = 0x22
    intel_hex[0x4203] = 0x00

    flash_data = FlashData(chip_info_entry, intel_hex)

    assert flash_data.eeprom_data[:2] == bytes((0x11, 0x22))
    assert flash_data.eeprom_data[2:] == b'\xff' * (len(flash_data.eeprom_data) - 2)
    assert flash_data.eeprom_buffer.raw_size == 2


@pytest.mark.parametrize('core', ['newf12b', 'bit14_b'])
@pytest.mark.parametrize('little_endian', [False, True])
def test_eeprom_words_preserve_byte_sequence(small_chip: ChipInfoEntry, core: str, *, little_endian: bool) -> None:
    chip = replace(small_chip, core_type=core)
    image = IntelHex()
    order: Literal['little', 'big'] = 'little' if little_endian else 'big'
    rom_word = 0x0123 if core == 'newf12b' else 0x1283
    image.frombytes(rom_word.to_bytes(2, order))
    payload = b'\x11\x22\x00\xff'
    image.frombytes(b''.join(value.to_bytes(2, order) for value in payload), offset=0x4200)
    before = image.todict()
    data = FlashData(chip, image)
    assert data.eeprom_data == payload
    assert data.eeprom_buffer == PaddedBuffer(data=payload, raw_size=4, padding_size=0, size=4)
    assert image.todict() == before
    data.process()
    assert data.eeprom_data == payload


@pytest.mark.parametrize('core', ['newf12b', 'bit14_b'])
@pytest.mark.parametrize('little_endian', [False, True])
def test_sparse_eeprom_counts_only_payload_bytes(small_chip: ChipInfoEntry, core: str, *, little_endian: bool) -> None:
    chip = replace(small_chip, core_type=core)
    image = IntelHex()
    order: Literal['little', 'big'] = 'little' if little_endian else 'big'
    rom_word = 0x0123 if core == 'newf12b' else 0x1283
    image.frombytes(rom_word.to_bytes(2, order))
    payload_offset = 0 if little_endian else 1
    image[0x4200 + (1 - payload_offset)] = 0  # Filler without a payload is not used EEPROM.
    image[0x4200 + 6 + payload_offset] = 0
    data = FlashData(chip, image)
    assert data.eeprom_buffer == PaddedBuffer(data=b'\xff\xff\xff\x00', raw_size=1, padding_size=3, size=4)


@pytest.mark.parametrize('size', [128, 256])
@pytest.mark.parametrize('core', ['newf12b', 'bit14_b'])
def test_last_midrange_eeprom_byte_is_not_truncated(small_chip: ChipInfoEntry, size: int, core: str) -> None:
    chip = replace(small_chip, core_type=core, eeprom_size=size)
    image = IntelHex({0x4200 + 2 * (size - 1): 0x55})
    data = FlashData(chip, image)
    assert data.eeprom_data == b'\xff' * (size - 1) + b'\x55'
    assert data.eeprom_buffer.raw_size == 1
    assert data.eeprom_buffer.padding_size == size - 1
    assert data.eeprom_buffer.size == size


def test_pic18_eeprom_is_packed_bytes_at_f00000(small_chip: ChipInfoEntry) -> None:
    chip = replace(small_chip, core_type='bit16_b', rom_size=0x10000, fuse_blank=[0xffff] * 7)
    image = IntelHex()
    image.frombytes(b'\x34\x12', offset=0xf000)  # This is ROM, not EEPROM.
    image.frombytes(b'\x11\x22\x00\xff', offset=0xf00000)
    data = FlashData(chip, image)
    assert data.eeprom_buffer == PaddedBuffer(data=b'\x11\x22\x00\xff', raw_size=4, padding_size=0, size=4)
    assert data.rom_data[0xf000:0xf002] == b'\x12\x34'


def test_pic18_eeprom_capacity_larger_than_256(small_chip: ChipInfoEntry) -> None:
    chip = replace(small_chip, core_type='bit16_b', eeprom_size=1024, fuse_blank=[0xffff] * 7)
    data = FlashData(chip, IntelHex({0xf003ff: 0x55}))
    assert data.eeprom_data == b'\xff' * 1023 + b'\x55'
    assert data.eeprom_buffer.raw_size == 1
    assert data.eeprom_buffer.padding_size == 1023
    assert data.eeprom_buffer.size == 1024


@pytest.mark.parametrize('offset', [4, 5])
@pytest.mark.parametrize('value', [0, 0x12])
def test_pic18_eeprom_overflow_rejected(small_chip: ChipInfoEntry, offset: int, value: int) -> None:
    chip = replace(small_chip, core_type='bit16_b', fuse_blank=[0xffff] * 7)
    with pytest.raises(ValueError, match='exceeds chip EEPROM size'):
        FlashData(chip, IntelHex({0xf00000 + offset: value}))


def test_pic18_without_eeprom_rejects_eeprom_data(small_chip: ChipInfoEntry) -> None:
    chip = replace(small_chip, core_type='bit16_b', eeprom_size=0, fuse_blank=[0xffff] * 7)
    with pytest.raises(ValueError, match='exceeds chip EEPROM size'):
        FlashData(chip, IntelHex({0xf00000: 0}))
