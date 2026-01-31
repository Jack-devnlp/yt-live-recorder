# YouTube Live Recorder

A command-line tool for recording YouTube live streams. Perfect for fans who want to capture their favorite streamers' content for later viewing or clip creation.

## Features

- **Single Stream Recording**: Record any YouTube live stream by URL
- **Multi-Channel Monitoring**: Monitor up to 5 channels and auto-record when they go live
- **Quality Selection**: Choose from best, 1080p, 720p, 480p, or 360p
- **Cookie Support**: Use browser cookies or cookie files to bypass YouTube bot detection
- **Graceful Shutdown**: Press Ctrl+C to stop recording and save the file properly
- **Automatic File Naming**: Files are saved with format `{channel_name}_{YYYYMMDD}_{HHMMSS}.mp4`
- **Robust Error Handling**: Automatic reconnection, disk space checks, and detailed logging

## Installation

### Requirements

- Python >= 3.9
- yt-dlp

### Install from Source

```bash
# Clone the repository
git clone https://github.com/user/yt-live-recorder.git
cd yt-live-recorder

# Create virtual environment and install dependencies
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e .

# Or use uv (recommended)
uv venv
uv pip install -e .
```

## Usage

### Single Stream Recording

```bash
# Basic recording (records until stream ends or you press Ctrl+C)
yt-recorder "https://www.youtube.com/watch?v=xxxxx"

# Specify output directory
yt-recorder "https://www.youtube.com/watch?v=xxxxx" -o ./my_recordings

# Record for a specific duration (e.g., 30 minutes = 1800 seconds)
yt-recorder "https://www.youtube.com/watch?v=xxxxx" -t 1800

# Specify quality
yt-recorder "https://www.youtube.com/watch?v=xxxxx" -q 720p

# Use cookies from browser (to bypass bot detection)
yt-recorder "https://www.youtube.com/watch?v=xxxxx" --cookies-from-browser chrome

# Use cookies file
yt-recorder "https://www.youtube.com/watch?v=xxxxx" --cookies cookies.txt
```

### Multi-Channel Monitoring

Create a configuration file (see `config/example.yaml`):

```yaml
channels:
  - name: "PewDiePie"
    channel_id: "UC-lHJZR3Gqxm24_Vd_AJ5Yw"
  - name: "MrBeast"
    channel_id: "UCX6OQ3DkcsbYNE6H8uQQuVA"

settings:
  output_dir: "./recordings"
  quality: "best"
```

Run the monitor:

```bash
# Start monitoring with default 60-second polling interval
yt-recorder --monitor -c config.yaml

# Custom polling interval (30 seconds)
yt-recorder --monitor -c config.yaml --interval 30
```

## Command-Line Options

```
yt-recorder [URL] [OPTIONS]

Options:
  -o, --output DIR            Output directory (default: ./recordings)
  -t, --time SECONDS          Recording duration limit
  -q, --quality QUAL          Video quality: best, 1080p, 720p, 480p, 360p
  --monitor                   Enable monitoring mode (requires -c)
  -c, --config FILE           Configuration file for monitoring mode
  --interval SECONDS          Polling interval for monitoring (default: 60, min: 10)
  --cookies-from-browser BROWSER  Extract cookies from browser (chrome, firefox, etc.)
  --cookies FILE              Path to cookies file (Netscape format)
  -v, --verbose               Enable verbose output (DEBUG level logging)
  --log-file FILE             Write logs to specified file
  --version                   Show version information
  -h, --help                  Show help message
```

## Output Files

Recordings are saved with the following naming convention:

```
{channel_name}_{YYYYMMDD}_{HHMMSS}.mp4
```

Examples:
- `PewDiePie_20250131_143022.mp4`
- `MrBeast_20250131_160145.mp4`

## Project Structure

```
yt-live-recorder/
├── src/
│   ├── __init__.py
│   ├── cli.py              # Command-line interface
│   ├── config.py           # Configuration parsing
│   ├── logger.py           # Structured logging
│   ├── monitor.py          # Multi-channel monitoring
│   ├── recorder.py         # Core recording logic
│   ├── retry.py            # Retry logic with backoff
│   ├── utils.py            # Utility functions
│   └── youtube_api.py      # YouTube interface wrapper
├── config/
│   └── example.yaml        # Example configuration
├── recordings/             # Default output directory
├── pyproject.toml
└── README.md
```

## Development

### Setup Development Environment

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black src/
ruff check src/
```

## Troubleshooting

### "Sign in to confirm you're not a bot" Error

YouTube may require authentication for some requests. You can use cookies to bypass this:

**Option 1: Use cookies from browser** (easiest)
```bash
# Supported browsers: chrome, firefox, safari, edge, chromium, brave
yt-recorder "https://www.youtube.com/watch?v=xxxxx" --cookies-from-browser chrome
```

**Option 2: Use exported cookies file**
```bash
# Export cookies using a browser extension like "Get cookies.txt LOCALLY"
# Then use the exported file
yt-recorder "https://www.youtube.com/watch?v=xxxxx" --cookies cookies.txt
```

### Recording Quality Issues

If the recording quality is lower than expected:
1. Check if the streamer is broadcasting at that quality
2. Try specifying the quality explicitly: `-q 1080p`
3. Check your internet connection

### Disk Space

The tool checks for available disk space before recording. If you encounter disk space errors:
1. Free up space or specify a different output directory: `-o /path/with/space`
2. Monitor disk space during long recordings

### Network Issues

If recordings fail due to network issues:
1. Check your internet connection
2. The tool will automatically retry on network errors
3. For persistent issues, try using cookies

## Roadmap

- [x] Single stream recording
- [x] Multi-channel monitoring
- [x] Auto-reconnection on network errors
- [x] Structured logging
- [ ] Configuration file hot-reload
- [ ] Docker support

## License

MIT License

## Acknowledgments

This project uses [yt-dlp](https://github.com/yt-dlp/yt-dlp) for YouTube stream handling.
