"""Multi-channel monitoring for YouTube Live Recorder."""

import logging
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List

from .config import Config, ChannelConfig
from .logger import get_channel_logger
from .recorder import StreamRecorder
from .utils import ensure_directory
from .youtube_api import get_channel_live_status, LiveStatus, YouTubeError, ChannelNotFoundError


logger = logging.getLogger('yt_recorder')


@dataclass
class ChannelState:
    """Current state of a monitored channel."""
    config: ChannelConfig
    is_live: bool = False
    is_recording: bool = False
    current_video_id: Optional[str] = None
    current_title: Optional[str] = None
    recorder: Optional[StreamRecorder] = None
    last_check: Optional[datetime] = None
    last_error: Optional[str] = None
    recording_start_time: Optional[datetime] = None


class ChannelMonitor:
    """Monitors multiple YouTube channels for live streams."""

    def __init__(
        self,
        config: Config,
        cookies_from_browser: Optional[str] = None,
        cookies_file: Optional[str] = None,
    ):
        """Initialize the monitor with configuration.

        Args:
            config: The monitoring configuration.
            cookies_from_browser: Browser to extract cookies from.
            cookies_file: Path to cookies file.
        """
        self.config = config
        self.cookies_from_browser = cookies_from_browser
        self.cookies_file = cookies_file
        self._states: Dict[str, ChannelState] = {}
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._threads: List[threading.Thread] = []

        # Initialize channel states
        for ch in config.channels:
            self._states[ch.channel_id] = ChannelState(config=ch)

        # Ensure output directory exists
        ensure_directory(Path(config.settings.output_dir))

        # Set up signal handlers
        self._setup_signal_handlers()

    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            logger.info("Received interrupt signal, stopping monitor...")
            self.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def _check_channel(self, channel_id: str) -> None:
        """Check the live status of a single channel.

        Args:
            channel_id: The YouTube channel ID to check.
        """
        with self._lock:
            state = self._states[channel_id]

        try:
            status = get_channel_live_status(
                channel_id,
                cookies_from_browser=self.cookies_from_browser,
                cookies_file=self.cookies_file,
            )

            with self._lock:
                state.last_check = datetime.now()
                state.last_error = None
                was_live = state.is_live
                current_video = state.current_video_id

            if status.is_live and not was_live:
                # Channel just went live
                logger.info(f"[{state.config.name}] Now live! Starting recording...")
                self._start_recording(channel_id, status)

            elif not status.is_live and was_live:
                # Channel just went offline
                logger.info(f"[{state.config.name}] Stream ended. Stopping recording...")
                self._stop_recording(channel_id)

            elif status.is_live and was_live:
                # Still live - check if video changed (new stream)
                if status.video_id != current_video:
                    logger.info(f"[{state.config.name}] New stream detected. Restarting recording...")
                    self._stop_recording(channel_id)
                    self._start_recording(channel_id, status)

            with self._lock:
                state.is_live = status.is_live

        except ChannelNotFoundError as e:
            with self._lock:
                state.last_error = str(e)
            logger.error(f"[{state.config.name}] Channel not found: {e}")
        except YouTubeError as e:
            with self._lock:
                state.last_error = str(e)
            logger.error(f"[{state.config.name}] Error checking status: {e}")

    def _start_recording(self, channel_id: str, status: LiveStatus) -> None:
        """Start recording a channel's live stream.

        Args:
            channel_id: The channel ID.
            status: The live status information.
        """
        state = self._states[channel_id]

        try:
            from .youtube_api import get_stream_url

            stream_url = get_stream_url(
                status.video_id,
                self.config.settings.quality,
                cookies_from_browser=self.cookies_from_browser,
                cookies_file=self.cookies_file,
            )

            # Create channel-specific logger
            channel_logger = get_channel_logger(state.config.name, logger)

            recorder = StreamRecorder(
                output_dir=self.config.settings.output_dir,
                quality=self.config.settings.quality,
                logger=channel_logger,
                cookies_from_browser=self.cookies_from_browser,
                cookies_file=self.cookies_file,
            )

            output_file = recorder.start_recording(
                stream_url=stream_url,
                channel_name=state.config.name,
            )

            with self._lock:
                state.recorder = recorder
                state.is_recording = True
                state.current_video_id = status.video_id
                state.current_title = status.title
                state.recording_start_time = datetime.now()

            logger.info(f"[{state.config.name}] Recording to: {output_file}")

        except Exception as e:
            logger.error(f"[{state.config.name}] Failed to start recording: {e}")
            with self._lock:
                state.is_recording = False
                state.last_error = str(e)

    def _stop_recording(self, channel_id: str) -> None:
        """Stop recording a channel.

        Args:
            channel_id: The channel ID.
        """
        with self._lock:
            state = self._states[channel_id]
            recorder = state.recorder
            is_recording = state.is_recording

        if recorder and is_recording:
            try:
                output_file = recorder.stop_recording()
                if output_file:
                    logger.info(f"[{state.config.name}] Saved: {output_file}")
            except Exception as e:
                logger.error(f"[{state.config.name}] Error stopping recording: {e}")

        with self._lock:
            state.recorder = None
            state.is_recording = False
            state.current_video_id = None
            state.current_title = None
            state.recording_start_time = None

    def _monitor_channel(self, channel_id: str) -> None:
        """Monitor a single channel in a loop.

        Args:
            channel_id: The channel ID to monitor.
        """
        state = self._states[channel_id]

        try:
            while not self._stop_event.is_set():
                try:
                    self._check_channel(channel_id)
                except Exception as e:
                    logger.exception(f"[{state.config.name}] Unexpected error in monitor loop: {e}")
                    # Brief pause to avoid rapid failure loops
                    time.sleep(5)

                # Wait for the polling interval
                # Use small increments to allow quick shutdown
                for _ in range(self.config.settings.interval):
                    if self._stop_event.is_set():
                        break
                    time.sleep(1)
        except Exception as e:
            logger.exception(f"[{state.config.name}] Monitor thread crashed: {e}")
            # Don't raise - let other channels continue monitoring

    def start(self) -> None:
        """Start monitoring all configured channels."""
        logger.info(f"Starting monitor with {len(self.config.channels)} channel(s)")
        logger.info(f"Polling interval: {self.config.settings.interval}s")
        logger.info(f"Output directory: {self.config.settings.output_dir}")
        logger.info(f"Monitoring: {', '.join(ch.name for ch in self.config.channels)}")
        logger.info("-" * 60)

        # Create a thread for each channel
        for channel_id in self._states:
            thread = threading.Thread(
                target=self._monitor_channel,
                args=(channel_id,),
                name=f"Monitor-{channel_id}",
            )
            thread.daemon = True
            thread.start()
            self._threads.append(thread)

        # Wait for all threads (or until stopped)
        try:
            while not self._stop_event.is_set():
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        """Stop monitoring and cleanup."""
        logger.info("Stopping monitor...")
        self._stop_event.set()

        # Stop all recordings
        for channel_id in self._states:
            self._stop_recording(channel_id)

        # Wait for threads to finish
        for thread in self._threads:
            thread.join(timeout=5)

        logger.info("Monitor stopped")

    def get_status(self) -> Dict[str, dict]:
        """Get current status of all channels.

        Returns:
            Dictionary mapping channel names to their status.
        """
        status = {}
        for channel_id, state in self._states.items():
            status[state.config.name] = {
                "is_live": state.is_live,
                "is_recording": state.is_recording,
                "current_title": state.current_title,
                "last_check": state.last_check.isoformat() if state.last_check else None,
                "last_error": state.last_error,
            }
        return status
