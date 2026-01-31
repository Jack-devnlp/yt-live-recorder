"""Configuration parsing for YouTube Live Recorder."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml


@dataclass
class ChannelConfig:
    """Configuration for a single channel to monitor."""
    name: str
    channel_id: str


@dataclass
class Settings:
    """Global settings for the recorder."""
    output_dir: str = "./recordings"
    quality: str = "best"
    format: str = "mp4"
    interval: int = 60


@dataclass
class Config:
    """Full configuration for multi-channel monitoring."""
    channels: List[ChannelConfig] = field(default_factory=list)
    settings: Settings = field(default_factory=Settings)


class ConfigError(Exception):
    """Exception for configuration errors."""
    pass


def load_config(config_path: str) -> Config:
    """Load configuration from a YAML file.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        Parsed Config object.

    Raises:
        ConfigError: If the configuration is invalid or file cannot be read.
    """
    path = Path(config_path)

    if not path.exists():
        raise ConfigError(f"Configuration file not found: {config_path}")

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML format: {e}")
    except Exception as e:
        raise ConfigError(f"Failed to read configuration file: {e}")

    if not isinstance(data, dict):
        raise ConfigError("Configuration must be a YAML dictionary")

    config = Config()

    # Parse channels
    channels_data = data.get('channels', [])
    if not isinstance(channels_data, list):
        raise ConfigError("'channels' must be a list")

    if len(channels_data) > 5:
        raise ConfigError("Maximum 5 channels allowed")

    for i, ch in enumerate(channels_data):
        if not isinstance(ch, dict):
            raise ConfigError(f"Channel {i} must be a dictionary")

        name = ch.get('name')
        channel_id = ch.get('channel_id')

        if not name:
            raise ConfigError(f"Channel {i} missing required field: name")
        if not channel_id:
            raise ConfigError(f"Channel {i} missing required field: channel_id")

        # Validate channel_id format (should start with UC)
        if not channel_id.startswith('UC'):
            raise ConfigError(
                f"Channel '{name}' has invalid channel_id: '{channel_id}'. "
                "Channel ID should start with 'UC'"
            )

        config.channels.append(ChannelConfig(name=name, channel_id=channel_id))

    # Parse settings
    settings_data = data.get('settings', {})
    if not isinstance(settings_data, dict):
        raise ConfigError("'settings' must be a dictionary")

    config.settings.output_dir = settings_data.get('output_dir', './recordings')
    config.settings.quality = settings_data.get('quality', 'best')
    config.settings.format = settings_data.get('format', 'mp4')
    config.settings.interval = settings_data.get('interval', 60)

    # Validate quality setting
    valid_qualities = ['best', '1080p', '720p', '480p', '360p']
    if config.settings.quality not in valid_qualities:
        raise ConfigError(
            f"Invalid quality: '{config.settings.quality}'. "
            f"Must be one of: {', '.join(valid_qualities)}"
        )

    # Validate interval
    if not isinstance(config.settings.interval, int) or config.settings.interval < 10:
        raise ConfigError("interval must be an integer >= 10 seconds")

    return config


def validate_config(config: Config) -> None:
    """Validate a configuration object.

    Args:
        config: The configuration to validate.

    Raises:
        ConfigError: If the configuration is invalid.
    """
    if not config.channels:
        raise ConfigError("At least one channel must be configured")

    if len(config.channels) > 5:
        raise ConfigError("Maximum 5 channels allowed")

    # Check for duplicate channel IDs
    channel_ids = [ch.channel_id for ch in config.channels]
    if len(channel_ids) != len(set(channel_ids)):
        raise ConfigError("Duplicate channel IDs found in configuration")

    # Check for duplicate names
    names = [ch.name for ch in config.channels]
    if len(names) != len(set(names)):
        raise ConfigError("Duplicate channel names found in configuration")

    # Validate output directory is writable
    output_dir = Path(config.settings.output_dir)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        # Test write permission
        test_file = output_dir / ".write_test"
        test_file.touch()
        test_file.unlink()
    except (OSError, PermissionError) as e:
        raise ConfigError(
            f"Output directory is not writable: {config.settings.output_dir} ({e})"
        )
