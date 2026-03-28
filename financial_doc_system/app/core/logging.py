"""
core/logging.py
Loguru-based structured logging configuration.
"""

import sys
from loguru import logger
from app.core.config import settings


def setup_logging() -> None:
    """Configure Loguru with appropriate log level and format."""
    logger.remove()  # Remove default handler

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    logger.add(
        sys.stdout,
        format=log_format,
        level=settings.LOG_LEVEL,
        colorize=True,
    )

    logger.add(
        "logs/app.log",
        format=log_format,
        level=settings.LOG_LEVEL,
        rotation="10 MB",
        retention="30 days",
        compression="zip",
    )

    logger.info(f"Logging initialized at level: {settings.LOG_LEVEL}")
