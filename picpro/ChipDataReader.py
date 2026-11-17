import logging
from pathlib import Path

import yaml

from picpro.ChipInfoEntry import ChipInfoEntry

log = logging.getLogger(__name__)


class ChipDataReader:
    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir

    def get_chip(self, name: str) -> ChipInfoEntry:
        chip_file = self._data_dir / f'{name.lower()}.yml'
        if not chip_file.is_file():
            raise KeyError(name)
        with chip_file.open('r', encoding='UTF-8') as f:
            return self._parse(yaml.safe_load(f))

    @property
    def chip_entries(self) -> dict[str, ChipInfoEntry]:
        entries = {}
        for path in sorted(self._data_dir.glob('*.yml')):
            with path.open('r', encoding='UTF-8') as file:
                entries[path.stem] = self._parse(yaml.safe_load(file))
        return entries

    @staticmethod
    def _parse(data: dict) -> ChipInfoEntry:
        fuse_blank = [v for _, v in sorted(data['fuses_blank'].items())]
        fuses = {
            name: {setting: list(vals.items()) for setting, vals in settings.items()}
            for name, settings in data['fuses'].items()
        }
        return ChipInfoEntry.from_dict({**data, 'fuse_blank': fuse_blank, 'fuses': fuses})
