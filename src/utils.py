"""Utility functions for YouTube Live Recorder."""

import re
from datetime import datetime
from pathlib import Path


def sanitize_filename(name: str) -> str:
    """Sanitize a string to be safe for use as a filename.

    Args:
        name: The string to sanitize.

    Returns:
        A sanitized string safe for use as a filename.
    """
    # Replace invalid characters with underscore
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Remove leading/trailing whitespace and dots
    sanitized = sanitized.strip(' .')
    # Limit length
    if len(sanitized) > 100:
        sanitized = sanitized[:100]
    return sanitized or 'unknown'


def generate_filename(channel_name: str, extension: str = 'mp4') -> str:
    """Generate a filename for a recording.

    Format: {channel_name}_{YYYYMMDD}_{HHMMSS}.{extension}

    Args:
        channel_name: The name of the channel.
        extension: The file extension (default: mp4).

    Returns:
        A formatted filename.
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_name = sanitize_filename(channel_name)
    return f"{safe_name}_{timestamp}.{extension}"


def ensure_directory(path: Path) -> Path:
    """Ensure a directory exists, creating it if necessary.

    Args:
        path: The directory path.

    Returns:
        The directory path.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def format_duration(seconds: int) -> str:
    """Format seconds into a human-readable duration string.

    Args:
        seconds: Duration in seconds.

    Returns:
        Formatted string like "1:23:45" or "30:22".
    """
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
