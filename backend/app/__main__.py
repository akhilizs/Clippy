"""Start the backend: `python -m app`. Prints the address and access code to type into the iPhone app."""

from __future__ import annotations

import logging
import socket

import uvicorn

from .config import get_settings
from .main import create_app
from .pipeline.ffmpeg import FFmpegError, require_ffmpeg


def lan_ip() -> str:
    """This computer's address on the home network (no traffic is actually sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s", datefmt="%H:%M:%S")
    try:
        require_ffmpeg()
    except FFmpegError as e:
        raise SystemExit(str(e))
    settings = get_settings()
    app = create_app(settings)
    ai = settings.claude_model if settings.ai_enabled else "OFF (no ANTHROPIC_API_KEY, using loudest moments)"
    bar = "=" * 62
    print(f"\n{bar}\n  Clippy backend is running\n\n"
          f"  In the iPhone app, open Settings and enter:\n"
          f"    Server address:  http://{lan_ip()}:{settings.port}\n"
          f"    Access code:     {settings.access_token}\n\n"
          f"  AI clip picker:    {ai}\n"
          f"  Files are saved in {settings.data_dir}\n"
          f"  Keep this window open while you use the app. Ctrl+C stops it.\n{bar}\n", flush=True)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="warning")


if __name__ == "__main__":
    main()
