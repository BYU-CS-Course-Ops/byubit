from pathlib import Path
from typing import Protocol

Grid = list[list[str]]
Pos = tuple[int, int]


class BitRenderer(Protocol):
    def render(self, code_file: Path, recordings: dict[str, list[dict]]):
        ...
