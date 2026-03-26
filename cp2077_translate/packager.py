"""Assemble the final translation mod package as a distributable zip."""

import zipfile
from pathlib import Path

from .config import Config


def create_zip(config: Config, packed_dir: Path) -> Path:
    """Create a distributable zip containing the repacked .archive file(s).

    The zip layout mirrors the game's archive directory so users can extract
    directly into the game folder:

        archive/pc/mod/<mod_name>.archive
    """
    config.output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = config.output_dir / f"{config.mod_name}.zip"

    archives = list(packed_dir.glob("*.archive"))
    if not archives:
        raise FileNotFoundError(f"No .archive files found in {packed_dir}")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, archive in enumerate(archives):
            suffix = f"_{i}" if i > 0 else ""
            arcname = Path("archive") / "pc" / "mod" / f"{config.mod_name}{suffix}.archive"
            zf.write(archive, arcname)

    print(f"  Package created: {zip_path}")
    return zip_path
