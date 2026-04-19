from __future__ import annotations

import logging


def configure_logging(level: str = 'INFO') -> None:
    root = logging.getLogger()
    resolved_level = getattr(logging, str(level or 'INFO').upper(), logging.INFO)
    if not root.handlers:
        logging.basicConfig(
            level=resolved_level,
            format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
        )
    root.setLevel(resolved_level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
