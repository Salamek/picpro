import importlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from intelhex import IntelHex


@pytest.mark.parametrize('binary', [False, True])
@pytest.mark.parametrize('memory', ['eeprom', 'rom'])
def test_dump_byte_order(tmp_path: Path, yaml_chip_data_path: Path, monkeypatch: pytest.MonkeyPatch,
                         memory: str, *, binary: bool) -> None:
    cli = importlib.import_module('picpro.bin.picpro')
    output = tmp_path / ('dump.bin' if binary else 'dump.hex')
    monkeypatch.setattr(cli, '_find_chip_data', lambda: yaml_chip_data_path)
    factory = MagicMock(spec=cli.Connection)
    programmer = factory.return_value.__enter__.return_value.get_programming_interface.return_value.__enter__.return_value
    payload = b'\x11\x22\x00\xff'
    programmer.read_eeprom.return_value = payload
    programmer.read_rom.return_value = payload
    monkeypatch.setattr(cli, 'Connection', factory)

    cli.dump(cli.MemoryType(memory), '/dev/fake', '12f675', output, binary=binary)

    expected = payload if memory == 'eeprom' else b'\x22\x11\xff\x00'
    if binary:
        assert output.read_bytes() == expected
    else:
        result = IntelHex(str(output))
        assert result.addresses() == [0, 1, 2, 3]
        assert bytes(result.tobinarray()) == expected
    factory.assert_called_once_with('/dev/fake')
    if memory == 'eeprom':
        programmer.read_eeprom.assert_called_once_with()
        programmer.read_rom.assert_not_called()
    else:
        programmer.read_rom.assert_called_once_with()
        programmer.read_eeprom.assert_not_called()
