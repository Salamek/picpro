import logging
from importlib.resources.abc import Traversable
from pathlib import Path

import yaml

from picpro.ChipInfoEntry import ChipInfoEntry
from picpro.exceptions import UnknownChipError

log = logging.getLogger(__name__)


class ChipDataReader:
    def __init__(self, data_dir: Path | Traversable) -> None:
        if not data_dir.is_dir():
            msg = f'Chip data directory does not exist: {data_dir}'
            raise FileNotFoundError(msg)
        self._data_dir = data_dir

    def get_chip(self, name: str) -> ChipInfoEntry:
        chip_file = self._data_dir / f'{name.lower()}.yml'
        if not chip_file.is_file():
            raise UnknownChipError(name)
        with chip_file.open('r', encoding='UTF-8') as f:
            return self._parse(yaml.safe_load(f))

    @property
    def chip_entries(self) -> dict[str, ChipInfoEntry]:
        entries = {}
        for path in sorted(self._data_dir.iterdir(), key=lambda entry: entry.name):
            if not path.is_file() or not path.name.endswith('.yml'):
                continue
            with path.open('r', encoding='UTF-8') as file:
                entries[Path(path.name).stem] = self._parse(yaml.safe_load(file))
        return entries

    @staticmethod
    def _parse(data: dict) -> ChipInfoEntry:
        fuse_blank = [v for _, v in sorted(data['fuses_blank'].items())]
        fuses = {
            name: {setting: list(vals.items()) for setting, vals in settings.items()}
            for name, settings in data['fuses'].items()
        }
        return ChipInfoEntry.from_dict({**data, 'fuse_blank': fuse_blank, 'fuses': fuses})
