"""Safe file-writing helpers for OpenChat-generated files."""
from pathlib import Path
import os
import tempfile


def is_safe_filename(name: str) -> bool:
    """Accept one plain filename, never a path or a special directory entry."""
    if not isinstance(name, str) or not name or name in {".", ".."}:
        return False
    if "\x00" in name or "/" in name or "\\" in name:
        return False
    if Path(name).is_absolute() or Path(name).name != name:
        return False
    # Reject Windows drive prefixes and control characters on every platform.
    if ":" in name or any(ord(char) < 32 for char in name):
        return False
    return True


def write_text_safely(directory, name: str, content: str, *, overwrite: bool = False):
    """Write UTF-8 text inside directory. Return path, or None if overwrite was declined."""
    if not is_safe_filename(name):
        raise ValueError("Nombre de archivo no permitido.")
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = root / name
    # Never follow a pre-existing symlink to a destination outside the chosen folder.
    if target.is_symlink() and target.resolve().parent != root:
        raise ValueError("El archivo apunta fuera de la carpeta elegida.")
    if target.exists() and not overwrite:
        return None
    if target.exists() and not target.is_file():
        raise ValueError("El destino existe y no es un archivo normal.")
    if overwrite:
        fd, temp_name = tempfile.mkstemp(prefix=".openchat-", dir=str(root))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, target)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise
    else:
        # Exclusive creation avoids overwriting a file created after the initial check.
        with target.open("x", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    if not target.is_file() or target.read_text(encoding="utf-8") != content:
        raise OSError("La comprobación posterior a la escritura no coincide.")
    return target
