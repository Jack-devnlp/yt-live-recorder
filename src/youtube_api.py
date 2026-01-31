"""YouTube API wrapper for live stream detection and metadata extraction."""

import logging
import re
import subprocess
import json
from dataclasses import dataclass
from typing import Optional

from .retry import retry_with_backoff, YOUTUBE_RETRY, RetryExhaustedError


logger = logging.getLogger('yt_recorder')


class YouTubeError(Exception):
    """Base exception for YouTube-related errors."""
    pass


class NotLiveError(YouTubeError):
    """Raised when a video is not a live stream."""
    pass


class StreamUnavailableError(YouTubeError):
    """Raised when a stream cannot be accessed."""
    pass


class InvalidURLError(YouTubeError):
    """Raised when a URL format is not recognized."""
    pass


class ChannelNotFoundError(YouTubeError):
    """Raised when a channel doesn't exist."""
    pass


@dataclass
class LiveStatus:
    """Status of a YouTube channel's live stream."""
    is_live: bool
    video_id: Optional[str] = None
    title: Optional[str] = None
    channel_name: Optional[str] = None


def extract_video_id(url: str) -> str:
    """Extract video ID from various YouTube URL formats.

    Supports:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://www.youtube.com/live/VIDEO_ID

    Args:
        url: The YouTube URL.

    Returns:
        The video ID.

    Raises:
        InvalidURLError: If URL format is not recognized.
    """
    patterns = [
        r'(?:https?://)?(?:www\.|m\.)?(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/live/|m\.youtube\.com/watch\?.*v=)([a-zA-Z0-9_-]{11})',
        r'(?:https?://)?(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})',
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    raise InvalidURLError(f"Could not extract video ID from URL: {url}")


def _fetch_video_info(
    url: str,
    cookies_from_browser: Optional[str] = None,
    cookies_file: Optional[str] = None,
) -> dict:
    """Internal function to fetch video info with retry logic."""
    cmd = ['yt-dlp', '--dump-json', '--no-download']

    if cookies_from_browser:
        cmd.extend(['--cookies-from-browser', cookies_from_browser])
    if cookies_file:
        cmd.extend(['--cookies', cookies_file])

    cmd.append(url)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30
    )

    if result.returncode != 0:
        raise YouTubeError(f"yt-dlp failed: {result.stderr}")

    return json.loads(result.stdout)


def get_video_info(
    url: str,
    cookies_from_browser: Optional[str] = None,
    cookies_file: Optional[str] = None,
) -> dict:
    """Get video information using yt-dlp.

    Args:
        url: The YouTube URL.
        cookies_from_browser: Browser to extract cookies from.
        cookies_file: Path to cookies file.

    Returns:
        Dictionary containing video metadata.

    Raises:
        YouTubeError: If video info cannot be retrieved.
    """
    try:
        return retry_with_backoff(
            lambda: _fetch_video_info(url, cookies_from_browser, cookies_file),
            config=YOUTUBE_RETRY,
            on_retry=lambda attempt, error, delay: logger.warning(
                f"Retry {attempt}/3 for video info: {error}. Waiting {delay:.1f}s..."
            )
        )
    except RetryExhaustedError as e:
        raise YouTubeError(f"Failed to fetch video info after retries: {e.last_exception}")
    except subprocess.TimeoutExpired:
        raise YouTubeError("Timeout while fetching video info")
    except json.JSONDecodeError as e:
        raise YouTubeError(f"Failed to parse video info: {e}")
    except FileNotFoundError:
        raise YouTubeError("yt-dlp not found. Please install yt-dlp.")


def check_live_status(
    video_id: str,
    cookies_from_browser: Optional[str] = None,
    cookies_file: Optional[str] = None,
) -> LiveStatus:
    """Check if a video is currently live.

    Args:
        video_id: The YouTube video ID.
        cookies_from_browser: Browser to extract cookies from.
        cookies_file: Path to cookies file.

    Returns:
        LiveStatus with is_live flag and metadata.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"

    try:
        info = get_video_info(url, cookies_from_browser, cookies_file)

        # Check if it's a live stream
        is_live = info.get('is_live', False)
        live_status = info.get('live_status', 'not_live')

        # Also check for was_live to handle ended streams
        was_live = info.get('was_live', False)

        return LiveStatus(
            is_live=is_live or live_status == 'is_live',
            video_id=video_id,
            title=info.get('title'),
            channel_name=info.get('channel')
        )
    except YouTubeError:
        return LiveStatus(is_live=False)


def get_channel_live_status(
    channel_id: str,
    cookies_from_browser: Optional[str] = None,
    cookies_file: Optional[str] = None,
) -> LiveStatus:
    """Check if a channel is currently live streaming.

    Args:
        channel_id: YouTube channel ID (starts with UC).
        cookies_from_browser: Browser to extract cookies from.
        cookies_file: Path to cookies file.

    Returns:
        LiveStatus with is_live flag and video details if live.

    Raises:
        ChannelNotFoundError: If the channel doesn't exist.
        YouTubeError: If there are network or other errors.
    """
    # Validate channel_id format
    if not channel_id or not isinstance(channel_id, str):
        raise YouTubeError(f"Invalid channel_id: must be a non-empty string")

    # Use yt-dlp to check channel's live tab
    url = f"https://www.youtube.com/channel/{channel_id}/live"

    try:
        info = get_video_info(url, cookies_from_browser, cookies_file)
    except YouTubeError as e:
        error_msg = str(e).lower()
        # Check if it's a channel not found error
        if any(msg in error_msg for msg in ['not found', 'unavailable', 'does not exist', 'removed']):
            raise ChannelNotFoundError(f"Channel not found: {channel_id}") from e
        raise

    # More strict live status checking
    is_live = info.get('is_live', False)
    live_status = info.get('live_status', 'not_live')
    was_live = info.get('was_live', False)

    # Only consider actually live if is_live is True AND live_status is 'is_live'
    # AND it was not a past live stream
    actually_live = is_live and live_status == 'is_live' and not was_live

    # Additional check: if we got redirected to a VOD, it's not live
    if actually_live and info.get('id'):
        # Verify this is actually a current live stream by checking availability
        pass  # yt-dlp already handles the /live redirect logic

    return LiveStatus(
        is_live=actually_live,
        video_id=info.get('id') if actually_live else None,
        title=info.get('title') if actually_live else None,
        channel_name=info.get('channel')
    )


def _fetch_stream_url(
    url: str,
    format_selector: str,
    cookies_from_browser: Optional[str] = None,
    cookies_file: Optional[str] = None,
) -> str:
    """Internal function to fetch stream URL with retry logic."""
    cmd = ['yt-dlp', '-f', format_selector, '-g']

    if cookies_from_browser:
        cmd.extend(['--cookies-from-browser', cookies_from_browser])
    if cookies_file:
        cmd.extend(['--cookies', cookies_file])

    cmd.append(url)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30
    )

    if result.returncode != 0:
        raise StreamUnavailableError(f"Failed to get stream URL: {result.stderr}")

    stream_url = result.stdout.strip()
    if not stream_url:
        raise StreamUnavailableError("No stream URL returned")

    return stream_url


def get_stream_url(
    video_id: str,
    quality: str = "best",
    cookies_from_browser: Optional[str] = None,
    cookies_file: Optional[str] = None,
) -> str:
    """Get direct stream URL for a live video using yt-dlp.

    Args:
        video_id: YouTube video ID.
        quality: Desired quality (best, 1080p, 720p, etc.).
        cookies_from_browser: Browser to extract cookies from.
        cookies_file: Path to cookies file.

    Returns:
        Direct stream URL.

    Raises:
        NotLiveError: If video is not a live stream.
        StreamUnavailableError: If stream cannot be accessed.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"

    # First check if it's live
    status = check_live_status(video_id, cookies_from_browser, cookies_file)
    if not status.is_live:
        raise NotLiveError(f"Video {video_id} is not a live stream")

    # Get the stream URL
    format_selector = "best"
    if quality != "best":
        # Map quality to format selector
        quality_map = {
            "1080p": "best[height<=1080]",
            "720p": "best[height<=720]",
            "480p": "best[height<=480]",
            "360p": "best[height<=360]",
        }
        format_selector = quality_map.get(quality, "best")

    try:
        return retry_with_backoff(
            lambda: _fetch_stream_url(url, format_selector, cookies_from_browser, cookies_file),
            config=YOUTUBE_RETRY,
            on_retry=lambda attempt, error, delay: logger.warning(
                f"Retry {attempt}/3 for stream URL: {error}. Waiting {delay:.1f}s..."
            )
        )
    except RetryExhaustedError as e:
        raise StreamUnavailableError(f"Failed to get stream URL after retries: {e.last_exception}")
    except subprocess.TimeoutExpired:
        raise StreamUnavailableError("Timeout while getting stream URL")
    except FileNotFoundError:
        raise StreamUnavailableError("yt-dlp not found. Please install yt-dlp.")
