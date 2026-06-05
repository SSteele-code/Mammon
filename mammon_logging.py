"""
Mammon logging configuration.

Call configure() once at startup (e.g. in boot.py or main).
All modules use logging.getLogger(__name__) so output is structured
by package path and controllable without touching source files.

Example:
    import mammon_logging
    mammon_logging.configure(level="INFO", log_file="mammon.log")
"""

import logging
import sys
from pathlib import Path


def configure(
    level: str = "INFO",
    log_file: str = None,
    fmt: str = "%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt: str = "%Y-%m-%d %H:%M:%S",
):
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(fmt, datefmt=datefmt)

    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        root.addHandler(handler)

    if log_file:
        fh = logging.FileHandler(Path(log_file), encoding="utf-8")
        fh.setFormatter(formatter)
        root.addHandler(fh)

    # Quiet noisy third-party libs
    for noisy in ("alpaca", "urllib3", "httpx", "numba"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
