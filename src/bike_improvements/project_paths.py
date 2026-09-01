"""Resolve local data paths for the bicycle-network experiments."""

from __future__ import annotations

import os
from pathlib import Path


def _required_path(variable: str) -> Path:
    value = os.environ.get(variable)

    if not value:
        raise RuntimeError(
            f"{variable} is not set. "
            "Configure the local project data paths before running this script."
        )

    return Path(value)


def data_root() -> Path:
    return _required_path("BIKE_DATA_ROOT")


def final_root() -> Path:
    return _required_path("BIKE_FINAL_ROOT")


def course_root() -> Path:
    return _required_path("BIKE_COURSE_ROOT")


def data_relative_path(path: str | Path) -> str:
    """Return a portable path relative to BIKE_DATA_ROOT.

    Relative paths that are already outside the configured data root are
    preserved as relative paths. Absolute paths outside BIKE_DATA_ROOT are
    rejected rather than written into result manifests.
    """
    candidate = Path(path)

    if not candidate.is_absolute():
        resolved = candidate.resolve()
        root = data_root().resolve()

        try:
            return resolved.relative_to(root).as_posix()
        except ValueError:
            return candidate.as_posix()

    root = data_root().resolve()
    resolved = candidate.resolve()

    try:
        return resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(
            f"Path is outside BIKE_DATA_ROOT and cannot be "
            f"stored portably: {resolved}"
        ) from exc
