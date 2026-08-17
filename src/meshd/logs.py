"""Logging setup shared by the daemon and CLI.

Uses the standard library ``logging``; when running under systemd the output
goes to the journal automatically via stderr.
"""

from __future__ import annotations

import logging
import sys

_LOGGER_NAME = "meshd"


def get_logger(name: str = "meshd") -> logging.Logger:
    return logging.getLogger(f"{_LOGGER_NAME}.{name}" if name != _LOGGER_NAME else name)


def setup_logging(verbose: bool = False, foreground: bool = False) -> None:
    logger = logging.getLogger(_LOGGER_NAME)
    level = logging.DEBUG if verbose else logging.INFO
    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stderr if foreground else sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    # Avoid duplicate handlers if setup is called more than once.
    for h in list(logger.handlers):
        logger.removeHandler(h)
    logger.addHandler(handler)
    logger.propagate = False
