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
