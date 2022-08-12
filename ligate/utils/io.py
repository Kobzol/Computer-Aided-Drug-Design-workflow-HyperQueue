import os
import shutil
from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Union

GenericPath = Union[Path, str]


def replace_in_place(path: GenericPath, replacements: List[Tuple[str, str]]):
    """
    Replaces multiple occurences (`before`, `after`) in `path`.
    """
    with open(path) as f:
        data = f.read()
    for (src, target) in replacements:
        data = data.replace(src, target)

    with open(path, "w") as f:
        f.write(data)


def delete_file(path: GenericPath):
    """
    Deletes a file at `path`.
    """
    os.unlink(path)


def normalize_path(path: GenericPath) -> Path:
    """
    Makes the path absolute and resolves any links in it.
    """
    return Path(path).resolve()


def ensure_directory(path: GenericPath, clear=False) -> Path:
    """
    Makes sure that the directory at `path` exists and returns an absolute path to it.
    If `clear` is True, the contents of the directory will be removed.
    """
    if os.path.isfile(path) and not os.path.isdir(path):
        path = os.path.dirname(path)
    if clear and os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path, exist_ok=True)
    return normalize_path(path)


def copy_files(files: List[GenericPath], target_dir: GenericPath):
    """
    Copies the provided `files` to the `target_dir`.
    """
    target_dir = ensure_directory(target_dir)

    for path in files:
        shutil.copy(path, target_dir)


def remap_paths_to_dir(paths: List[GenericPath], dir: Path) -> List[Path]:
    """
    Maps the given `paths` so that they are relative to the given `dir`.
    """
    return [dir / path for path in paths]


def append_lines_to(lines: Iterable[str], target: Path, until: Optional[str] = None):
    """
    Reads lines from `lines` and appends them to `target`.
    When a line in `file` equals `until`, the appending will end.
    """
    with open(target, "a") as target:
        for line in lines:
            if until is not None and line == until:
                break
            target.write(f"{line}\n")


def append_to(file: Path, text: str):
    """
    Appends `text` to the provided `file`.
    """
    with open(file, "a") as file:
        file.write(text)


def iterate_file_lines(file: Path, skip=0) -> Iterable[str]:
    """
    Lazily iterates the lines of the given `file`.
    """
    with open(file) as f:
        for (index, line) in enumerate(f):
            line = line.strip()
            if index >= skip:
                yield line


def iterate_directories(path: GenericPath) -> List[Path]:
    """
    Iterates through directories (non-recursively) in the given `path`.
    The directories are sorted by their filepath.
    """
    path = Path(path)
    dirs = [
        path.absolute() / child for child in os.listdir(path) if (path / child).is_dir()
    ]
    return sorted(dirs)


def check_dir_exists(path: GenericPath):
    path = Path(path)
    if not path.is_dir():
        error = f"The path {path} is not an existing directory."
        if path.is_file():
            error += " It is a file."
        elif not path.exists():
            error += " It does not exist."
        raise Exception(error)
