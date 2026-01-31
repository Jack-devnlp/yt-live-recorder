"""Command-line interface for YouTube Live Recorder."""

import argparse
import logging
import sys
from pathlib import Path

from .logger import setup_logging
from .youtube_api import (
    extract_video_id,
    check_live_status,
    get_stream_url,
    YouTubeError,
    InvalidURLError,
    NotLiveError,
)
from .recorder import StreamRecorder, RecordingError
from .config import load_config, ConfigError, validate_config
from .monitor import ChannelMonitor


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="yt-recorder",
        description="YouTube Live Recorder - Record YouTube live streams",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Record a live stream
  yt-recorder "https://www.youtube.com/watch?v=xxxxx"

  # Record with custom output directory
  yt-recorder "https://www.youtube.com/watch?v=xxxxx" -o ./my_recordings

  # Record for 30 minutes
  yt-recorder "https://www.youtube.com/watch?v=xxxxx" -t 1800

  # Monitor multiple channels
  yt-recorder --monitor -c config.yaml
        """,
    )

    parser.add_argument(
        "url",
        nargs="?",
        help="YouTube live stream URL to record",
    )

    parser.add_argument(
        "-o",
        "--output",
        default="./recordings",
        help="Output directory for recordings (default: ./recordings)",
    )

    def validate_positive_int(value):
        """Validate that the value is a positive integer."""
        try:
            ivalue = int(value)
            if ivalue <= 0:
                raise argparse.ArgumentTypeError(f"{value} must be a positive integer")
            return ivalue
        except ValueError:
            raise argparse.ArgumentTypeError(f"{value} is not a valid integer")

    def validate_interval(value):
        """Validate polling interval (must be >= 10)."""
        try:
            ivalue = int(value)
            if ivalue < 10:
                raise argparse.ArgumentTypeError("interval must be at least 10 seconds")
            return ivalue
        except ValueError:
            raise argparse.ArgumentTypeError(f"{value} is not a valid integer")

    parser.add_argument(
        "-t",
        "--time",
        type=validate_positive_int,
        metavar="SECONDS",
        help="Recording duration limit in seconds",
    )

    parser.add_argument(
        "-q",
        "--quality",
        default="best",
        choices=["best", "1080p", "720p", "480p", "360p"],
        help="Video quality (default: best)",
    )

    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Enable multi-channel monitoring mode (requires -c)",
    )

    parser.add_argument(
        "-c",
        "--config",
        help="Configuration file path for monitoring mode",
    )

    parser.add_argument(
        "--interval",
        type=validate_interval,
        default=60,
        metavar="SECONDS",
        help="Polling interval for monitoring mode (default: 60, min: 10)",
    )

    parser.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER",
        help="Extract cookies from browser (e.g., chrome, firefox, safari, edge)",
    )

    parser.add_argument(
        "--cookies",
        metavar="FILE",
        help="Path to cookies file (Netscape format)",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output (DEBUG level logging)",
    )

    parser.add_argument(
        "--log-file",
        help="Write logs to specified file",
    )

    return parser


def record_single_stream(args: argparse.Namespace) -> int:
    """Record a single YouTube live stream.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    if not args.url:
        print("Error: URL is required for single stream recording")
        print("Use --help for usage information")
        return 1

    url = args.url

    try:
        # Extract video ID and check if live
        print(f"[INFO] Checking live status...")
        video_id = extract_video_id(url)
        status = check_live_status(
            video_id,
            cookies_from_browser=args.cookies_from_browser,
            cookies_file=args.cookies,
        )

        if not status.is_live:
            print(f"[ERROR] This video is not currently live")
            return 1

        print(f"[INFO] Channel: {status.channel_name or 'Unknown'}")
        print(f"[INFO] Title: {status.title or 'Unknown'}")
        print(f"[INFO] Stream quality: {args.quality}")

        # Get stream URL
        stream_url = get_stream_url(
            video_id,
            args.quality,
            cookies_from_browser=args.cookies_from_browser,
            cookies_file=args.cookies,
        )

        # Start recording
        recorder = StreamRecorder(
            output_dir=args.output,
            quality=args.quality,
            cookies_from_browser=args.cookies_from_browser,
            cookies_file=args.cookies,
        )

        if args.time:
            # Record for specific duration
            output_file = recorder.record_with_duration(
                stream_url=stream_url,
                channel_name=status.channel_name or "unknown",
                duration=args.time,
            )
        else:
            # Record until interrupted
            recorder.start_recording(
                stream_url=stream_url,
                channel_name=status.channel_name or "unknown",
            )
            print("[INFO] Recording... (Press Ctrl+C to stop)")
            output_file = recorder.wait_for_completion()

        if output_file:
            print(f"[INFO] Recording saved to: {output_file}")
            return 0
        else:
            print("[ERROR] Recording failed")
            return 1

    except InvalidURLError as e:
        print(f"[ERROR] Invalid URL: {e}")
        return 1
    except NotLiveError as e:
        print(f"[ERROR] {e}")
        return 1
    except YouTubeError as e:
        print(f"[ERROR] YouTube API error: {e}")
        return 1
    except RecordingError as e:
        print(f"[ERROR] Recording error: {e}")
        return 1
    except KeyboardInterrupt:
        print("\n[INFO] Recording interrupted by user")
        return 0


def monitor_mode(args: argparse.Namespace) -> int:
    """Run in multi-channel monitoring mode.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    if not args.config:
        print("[ERROR] Configuration file required for monitoring mode")
        print("[ERROR] Use -c/--config to specify a config file")
        return 1

    try:
        # Load and validate configuration
        config = load_config(args.config)
        validate_config(config)

        # Override interval if specified on command line
        if args.interval != 60:
            config.settings.interval = args.interval

        # Create and start monitor
        monitor = ChannelMonitor(
            config,
            cookies_from_browser=args.cookies_from_browser,
            cookies_file=args.cookies,
        )
        monitor.start()

        return 0

    except ConfigError as e:
        print(f"[ERROR] Configuration error: {e}")
        return 1
    except KeyboardInterrupt:
        print("\n[INFO] Monitor interrupted by user")
        return 0
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        return 1


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    parser = create_parser()
    args = parser.parse_args()

    # Set up logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(level=log_level, log_file=args.log_file)

    if args.monitor:
        return monitor_mode(args)
    else:
        return record_single_stream(args)


if __name__ == "__main__":
    sys.exit(main())
