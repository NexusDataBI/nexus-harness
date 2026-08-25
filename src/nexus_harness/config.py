from pathlib import Path
import tomllib


def load_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)
