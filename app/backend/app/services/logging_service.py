from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(log_dir: Path) -> None:
    """Configure application logging (file + console) and attach to uvicorn loggers.

    Idempotent: safe to call multiple times.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "server.log"

    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    formatter = logging.Formatter(fmt)

    file_handler = logging.FileHandler(str(log_path))
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    if not any(
        getattr(h, "baseFilename", None) == str(log_path)
        for h in root_logger.handlers
        if isinstance(h, logging.FileHandler)
    ):
        root_logger.addHandler(file_handler)

    if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
        root_logger.addHandler(stream_handler)

    for uv_logger_name in ("uvicorn.error", "uvicorn.access", "uvicorn"):
        lg = logging.getLogger(uv_logger_name)
        lg.setLevel(logging.INFO)
        if not any(
            getattr(h, "baseFilename", None) == str(log_path)
            for h in lg.handlers
            if isinstance(h, logging.FileHandler)
        ):
            lg.addHandler(file_handler)


