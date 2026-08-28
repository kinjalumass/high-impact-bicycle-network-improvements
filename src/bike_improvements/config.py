"""Configuration utilities for the bicycle network improvement experiments."""

from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path("configs/experiment.yaml")


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Load an experiment YAML configuration file."""
    config_path = Path(path)

    if not config_path.exists():
        raise FileNotFoundError(
            f"Experiment configuration not found: {config_path}"
        )

    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        raise ValueError("Experiment configuration must contain a YAML mapping.")

    return config


def get_rider_profiles(config: dict[str, Any]) -> dict[str, Any]:
    """Return configured rider profiles."""
    profiles = config.get("rider_profiles")

    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("No rider profiles defined in experiment configuration.")

    return profiles
