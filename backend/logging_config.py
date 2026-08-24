from __future__ import annotations

import logging
import sys

from backend.config import LOG_LEVEL


DEFAULT_LOG_FORMAT = (
    "%(asctime)s | "
    "%(levelname)s | "
    "%(name)s | "
    "%(message)s"
)


def configure_logging() -> None:
    """
    Configure application-wide logging.

    The log level comes from the LOG_LEVEL environment
    variable and defaults to INFO.
    """

    level = getattr(
        logging,
        LOG_LEVEL,
        logging.INFO,
    )

    root_logger = logging.getLogger()

    root_logger.setLevel(
        level
    )

    # Avoid adding duplicate handlers when modules reload
    # during local Uvicorn development.
    if root_logger.handlers:
        for handler in root_logger.handlers:
            handler.setLevel(
                level
            )
        return

    handler = logging.StreamHandler(
        sys.stdout
    )

    handler.setLevel(
        level
    )

    handler.setFormatter(
        logging.Formatter(
            DEFAULT_LOG_FORMAT
        )
    )

    root_logger.addHandler(
        handler
    )


def get_logger(
    name: str,
) -> logging.Logger:
    """
    Return a named application logger.
    """

    return logging.getLogger(
        name
    )