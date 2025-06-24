#!/usr/bin/env python3
"""
Harmoniq Web UI Server
Runs the FastAPI web interface for Harmoniq configuration and monitoring.
"""

import uvicorn
import asyncio
import signal
import logging
from pathlib import Path

from .app import create_app
from ..log_config import logger

# Global shutdown flag
shutdown_event = asyncio.Event()


def handle_shutdown_signal(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Web UI: Shutdown signal ({signal.Signals(signum).name}) received.")
    shutdown_event.set()


# Register signal handlers
signal.signal(signal.SIGINT, handle_shutdown_signal)
signal.signal(signal.SIGTERM, handle_shutdown_signal)


async def run_web_server():
    """Run the FastAPI web server."""
    logger.info("Starting Harmoniq Web UI server on port 7845...")

    # Create FastAPI app
    app = create_app()

    # Configure uvicorn
    config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=7845,
        log_level="info",
        access_log=True,
        reload=False,  # Disable in production
    )

    server = uvicorn.Server(config)

    # Run server until shutdown signal
    try:
        await server.serve()
    except Exception as e:
        logger.error(f"Web UI server error: {e}")
    finally:
        logger.info("Harmoniq Web UI server stopped.")


if __name__ == "__main__":
    logger.info("Harmoniq Web UI starting...")
    try:
        asyncio.run(run_web_server())
    except KeyboardInterrupt:
        logger.info("Web UI shutdown requested by user.")
    except Exception as e:
        logger.exception(f"Web UI fatal error: {e}")
