"""Shared strict JSON loading and same-directory atomic writes for local records."""

import json
import os
from pathlib import Path
import tempfile


class JsonStorageError(ValueError):
    """Never includes file contents, paths or underlying exception bodies."""


def write_json_record(record, path, max_bytes):
    payload = record.model_dump_json(indent=2).encode("utf-8")
    if len(payload) > max_bytes:
        raise JsonStorageError("记录超过文件大小限制。")
    path = Path(path)
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.stem}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError:
        raise JsonStorageError("记录写入失败；未完成原子替换。") from None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    return path


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key.")
        result[key] = value
    return result


def read_json_record(path, model, max_bytes):
    try:
        with Path(path).open("rb") as stream:
            payload = stream.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise ValueError("Record too large.")
        data = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_keys)
        # Each model requires an explicit supported schema_version.
        return model.model_validate(data)
    except (OSError, ValueError, RecursionError):
        raise JsonStorageError("记录损坏、Schema 不符、版本不兼容或文件不可读。") from None
