from __future__ import annotations

import logging
import sys
from pathlib import Path
from datetime import datetime


class PrintToLogHandler:
    """Custom handler that redirects print statements to logging."""
    
    def __init__(self, logger_name: str = "app.print"):
        self.logger = logging.getLogger(logger_name)
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        
    def write(self, message: str) -> None:
        if message.strip():  # Only log non-empty messages
            # Remove newlines and format as log message
            clean_message = message.strip()
            self.logger.info(f"[PRINT] {clean_message}")
        # Also write to original stdout for immediate console visibility
        self.original_stdout.write(message)
        
    def flush(self) -> None:
        self.original_stdout.flush()
        
    def __enter__(self):
        sys.stdout = self
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout = self.original_stdout


def configure_logging(log_dir: Path) -> None:
    """Configure application logging (file + console) and attach to uvicorn loggers.

    Idempotent: safe to call multiple times.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Create separate log files for different purposes
    server_log_path = log_dir / "server.log"
    auth_log_path = log_dir / "auth.log"
    debug_log_path = log_dir / "debug.log"
    
    # Main formatter
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    formatter = logging.Formatter(fmt)
    
    # Detailed formatter for debug logs
    debug_fmt = "%(asctime)s %(levelname)s %(name)s [%(filename)s:%(lineno)d]: %(message)s"
    debug_formatter = logging.Formatter(debug_fmt)

    # File handlers
    server_handler = logging.FileHandler(str(server_log_path))
    server_handler.setLevel(logging.DEBUG)
    server_handler.setFormatter(formatter)

    auth_handler = logging.FileHandler(str(auth_log_path))
    auth_handler.setLevel(logging.DEBUG)
    auth_handler.setFormatter(formatter)

    debug_handler = logging.FileHandler(str(debug_log_path))
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(debug_formatter)

    # Console handler
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Add handlers if not already present
    if not any(
        getattr(h, "baseFilename", None) == str(server_log_path)
        for h in root_logger.handlers
        if isinstance(h, logging.FileHandler)
    ):
        root_logger.addHandler(server_handler)

    if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
        root_logger.addHandler(stream_handler)

    # Configure specific loggers
    auth_logger = logging.getLogger("app.auth")
    auth_logger.setLevel(logging.DEBUG)
    if not any(
        getattr(h, "baseFilename", None) == str(auth_log_path)
        for h in auth_logger.handlers
        if isinstance(h, logging.FileHandler)
    ):
        auth_logger.addHandler(auth_handler)

    # Debug logger for print statements and detailed debugging
    debug_logger = logging.getLogger("app.debug")
    debug_logger.setLevel(logging.DEBUG)
    if not any(
        getattr(h, "baseFilename", None) == str(debug_log_path)
        for h in debug_logger.handlers
        if isinstance(h, logging.FileHandler)
    ):
        debug_logger.addHandler(debug_handler)

    # Print logger for capturing print statements
    print_logger = logging.getLogger("app.print")
    print_logger.setLevel(logging.DEBUG)
    if not any(
        getattr(h, "baseFilename", None) == str(debug_log_path)
        for h in print_logger.handlers
        if isinstance(h, logging.FileHandler)
    ):
        print_logger.addHandler(debug_handler)

    # Uvicorn loggers
    for uv_logger_name in ("uvicorn.error", "uvicorn.access", "uvicorn"):
        lg = logging.getLogger(uv_logger_name)
        lg.setLevel(logging.DEBUG)
        if not any(
            getattr(h, "baseFilename", None) == str(server_log_path)
            for h in lg.handlers
            if isinstance(h, logging.FileHandler)
        ):
            lg.addHandler(server_handler)


def redirect_prints_to_logs() -> PrintToLogHandler:
    """Redirect print statements to logging system."""
    return PrintToLogHandler()


