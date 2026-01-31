"""Core recording logic for YouTube Live Recorder."""

import logging
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from .utils import generate_filename, ensure_directory, format_duration
from .retry import RetryConfig, retry_with_backoff, NETWORK_RETRY


class RecordingError(Exception):
    """Base exception for recording errors."""
    pass


class StreamRecorder:
    """Records YouTube live streams to files with reconnection support."""

    def __init__(
        self,
        output_dir: str = "./recordings",
        quality: str = "best",
        logger: Optional[logging.Logger] = None,
        cookies_from_browser: Optional[str] = None,
        cookies_file: Optional[str] = None,
    ):
        """Initialize the recorder.

        Args:
            output_dir: Directory to save recordings.
            quality: Video quality (best, 1080p, 720p, 480p).
            logger: Optional logger instance.
            cookies_from_browser: Browser to extract cookies from (e.g., 'chrome', 'firefox').
            cookies_file: Path to cookies file.
        """
        self.output_dir = Path(output_dir)
        self.quality = quality
        self.logger = logger or logging.getLogger('yt_recorder')
        self.cookies_from_browser = cookies_from_browser
        self.cookies_file = cookies_file
        self._process: Optional[subprocess.Popen] = None
        self._start_time: Optional[datetime] = None
        self._current_file: Optional[Path] = None
        self._temp_file: Optional[Path] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._channel_name: Optional[str] = None
        self._stream_url: Optional[str] = None
        self._reconnect_count = 0
        self._max_reconnects = 5
        self._recording_parts: list[Path] = []
        self._output_threads: list[threading.Thread] = []

        # Ensure output directory exists
        ensure_directory(self.output_dir)

    def check_disk_space(self, required_mb: int = 1000) -> bool:
        """Check if there's enough disk space.

        Args:
            required_mb: Required free space in MB.

        Returns:
            True if there's enough space, False otherwise.
        """
        try:
            stat = shutil.disk_usage(self.output_dir)
            available_mb = stat.free // (1024 * 1024)
            if available_mb < required_mb:
                self.logger.error(
                    f"Insufficient disk space: {available_mb}MB available, "
                    f"{required_mb}MB required"
                )
                return False
            return True
        except Exception as e:
            self.logger.warning(f"Could not check disk space: {e}")
            return True  # Assume OK if we can't check

    def _log_output(self, pipe, level: int) -> None:
        """Read and log subprocess output to prevent pipe buffer deadlock.

        Args:
            pipe: Subprocess pipe (stdout or stderr).
            level: Logging level for the output.
        """
        try:
            for line in iter(pipe.readline, b''):
                if not line:
                    break
                decoded = line.decode('utf-8', errors='ignore').strip()
                if decoded:
                    self.logger.log(level, f"[yt-dlp] {decoded}")
        except Exception:
            pass  # Pipe closed or other error
        finally:
            pipe.close()

    def _get_format_selector(self) -> str:
        """Get yt-dlp format selector based on quality setting."""
        if self.quality == "best":
            return "best"

        quality_map = {
            "1080p": "best[height<=1080]",
            "720p": "best[height<=720]",
            "480p": "best[height<=480]",
            "360p": "best[height<=360]",
        }
        return quality_map.get(self.quality, "best")

    def start_recording(
        self,
        stream_url: str,
        channel_name: str,
        duration: Optional[int] = None
    ) -> Path:
        """Start recording a stream.

        Args:
            stream_url: The stream URL to record.
            channel_name: Name of the channel (for filename).
            duration: Maximum recording duration in seconds (optional).

        Returns:
            Path to the output file.

        Raises:
            RecordingError: If recording cannot be started.
        """
        with self._lock:
            if self._process is not None:
                raise RecordingError("Already recording")

            # Check disk space before starting
            if not self.check_disk_space(required_mb=500):
                raise RecordingError("Insufficient disk space for recording")

            self._stream_url = stream_url
            self._channel_name = channel_name

            # Generate filenames
            filename = generate_filename(channel_name, "mp4")
            self._current_file = self.output_dir / filename
            self._temp_file = self.output_dir / f".{filename}.tmp"

            # Build yt-dlp command
            format_selector = self._get_format_selector()
            cmd = [
                "yt-dlp",
                "-f", format_selector,
                "--no-part",  # Don't use .part files
                "--no-continue",  # Don't resume partial downloads
                "--newline",  # Output progress on new lines
                "-o", str(self._temp_file),
            ]

            # Add cookies options if provided
            if self.cookies_from_browser:
                cmd.extend(["--cookies-from-browser", self.cookies_from_browser])
            if self.cookies_file:
                cmd.extend(["--cookies", self.cookies_file])

            # Note: We don't use --max-filesize for duration as it's unreliable
            # Duration control is handled in Python layer via record_with_duration

            cmd.append(stream_url)

            try:
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                self._start_time = datetime.now()

                # Start threads to read and log output to prevent pipe buffer deadlock
                self._output_threads = []
                stdout_thread = threading.Thread(
                    target=self._log_output,
                    args=(self._process.stdout, logging.DEBUG),
                    daemon=True,
                    name="stdout-reader"
                )
                stderr_thread = threading.Thread(
                    target=self._log_output,
                    args=(self._process.stderr, logging.WARNING),
                    daemon=True,
                    name="stderr-reader"
                )
                stdout_thread.start()
                stderr_thread.start()
                self._output_threads = [stdout_thread, stderr_thread]

                self.logger.info(f"Started recording: {channel_name}")
                self.logger.info(f"Output: {self._current_file}")

                return self._current_file

            except Exception as e:
                raise RecordingError(f"Failed to start recording: {e}")

    def stop_recording(self) -> Optional[Path]:
        """Stop the current recording gracefully.

        Returns:
            Path to the final saved file, or None if not recording.
        """
        with self._lock:
            if self._process is None:
                return None

            self.logger.info("Stopping recording...")

            # Terminate the process
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.logger.warning("Process did not terminate in time, killing...")
                self._process.kill()
                try:
                    self._process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.logger.error("Process could not be killed")
            except Exception as e:
                self.logger.warning(f"Error stopping process: {e}")

            self._process = None
            self._stop_event.set()

            # Wait for output reader threads to finish
            for thread in self._output_threads:
                thread.join(timeout=2)
            self._output_threads = []

            # Move temp file to final location
            if self._temp_file and self._temp_file.exists():
                try:
                    # Ensure parent directory exists
                    self._current_file.parent.mkdir(parents=True, exist_ok=True)
                    self._temp_file.rename(self._current_file)
                    duration = self.get_recording_duration()
                    self.logger.info(f"Saved: {self._current_file} ({format_duration(duration)})")
                    return self._current_file
                except Exception as e:
                    self.logger.error(f"Failed to rename file: {e}")
                    # Keep the temp file so data isn't lost
                    return self._temp_file

            return None

    def is_recording(self) -> bool:
        """Check if currently recording.

        Returns:
            True if recording is in progress.
        """
        with self._lock:
            if self._process is None:
                return False
            # Check if process is still running
            return self._process.poll() is None

    def get_recording_duration(self) -> int:
        """Get the current recording duration in seconds.

        Returns:
            Duration in seconds.
        """
        if self._start_time is None:
            return 0
        return int((datetime.now() - self._start_time).total_seconds())

    def wait_for_completion(self) -> Optional[Path]:
        """Wait for the recording to complete naturally.

        Returns:
            Path to the final saved file, or None if not recording.
        """
        if self._process is None:
            return None

        try:
            self._process.wait()
        except KeyboardInterrupt:
            return self.stop_recording()

        return self.stop_recording()

    def record_with_duration(
        self,
        stream_url: str,
        channel_name: str,
        duration: int
    ) -> Optional[Path]:
        """Record for a specific duration.

        Args:
            stream_url: The stream URL to record.
            channel_name: Name of the channel.
            duration: Recording duration in seconds.

        Returns:
            Path to the saved file.
        """
        self.start_recording(stream_url, channel_name)

        self.logger.info(f"Recording for {format_duration(duration)}...")
        self.logger.info("Press Ctrl+C to stop early")

        try:
            # Wait for duration or until stopped
            start_time = time.time()
            while self.is_recording():
                elapsed = int(time.time() - start_time)
                if elapsed >= duration:
                    break
                time.sleep(1)

            return self.stop_recording()

        except KeyboardInterrupt:
            return self.stop_recording()

    def record_with_reconnect(
        self,
        stream_url: str,
        channel_name: str,
        get_stream_url: Callable[[], str],
        check_is_live: Callable[[], bool],
        max_reconnects: int = 5
    ) -> list[Path]:
        """Record with automatic reconnection on stream interruption.

        Args:
            stream_url: Initial stream URL.
            channel_name: Name of the channel.
            get_stream_url: Function to get fresh stream URL.
            check_is_live: Function to check if stream is still live.
            max_reconnects: Maximum number of reconnection attempts.

        Returns:
            List of paths to saved recording parts.
        """
        self._max_reconnects = max_reconnects
        self._recording_parts = []
        self._reconnect_count = 0

        self.logger.info(f"Starting recording with reconnection support (max {max_reconnects} reconnects)")

        while self._reconnect_count <= max_reconnects:
            try:
                # Start or resume recording
                if self._reconnect_count == 0:
                    self.start_recording(stream_url, channel_name)
                else:
                    # Get fresh stream URL for reconnection
                    self.logger.info(f"Reconnecting... (attempt {self._reconnect_count}/{max_reconnects})")
                    fresh_url = get_stream_url()
                    self.start_recording(fresh_url, f"{channel_name}_reconnect{self._reconnect_count}")

                # Monitor the recording
                while self.is_recording():
                    time.sleep(1)

                    # Check if stream is still live
                    if not check_is_live():
                        self.logger.info("Stream ended naturally")
                        break

                # Stop current recording segment
                part_file = self.stop_recording()
                if part_file:
                    self._recording_parts.append(part_file)

                # Check if stream is still live (for reconnection)
                if check_is_live() and self._reconnect_count < max_reconnects:
                    self._reconnect_count += 1
                    self.logger.info(f"Stream interrupted, attempting reconnect {self._reconnect_count}/{max_reconnects}")

                    # Wait before reconnecting
                    time.sleep(2)
                    continue
                else:
                    break

            except Exception as e:
                self.logger.error(f"Recording error: {e}")
                self.stop_recording()

                if self._reconnect_count < max_reconnects:
                    self._reconnect_count += 1
                    self.logger.info(f"Waiting before reconnect attempt {self._reconnect_count}/{max_reconnects}")
                    time.sleep(5)
                else:
                    break

        self.logger.info(f"Recording complete. Saved {len(self._recording_parts)} part(s)")
        return self._recording_parts

    def get_recording_parts(self) -> list[Path]:
        """Get list of recording part files.

        Returns:
            List of paths to recording parts.
        """
        return self._recording_parts.copy()
