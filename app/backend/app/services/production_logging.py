"""
Production logging configuration for Railway deployment.
This module provides enhanced logging for production environments.
"""

import logging
import os
import sys
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler


def setup_production_logging(log_dir: Path) -> None:
    """
    Setup enhanced logging for production environment.
    Creates separate log files for different components and enables log rotation.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Log file paths
    server_log = log_dir / "server.log"
    auth_log = log_dir / "auth.log"
    debug_log = log_dir / "debug.log"
    error_log = log_dir / "errors.log"
    
    # Formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s %(levelname)s %(name)s [%(filename)s:%(lineno)d] %(funcName)s(): %(message)s'
    )
    simple_formatter = logging.Formatter(
        '%(asctime)s %(levelname)s %(name)s: %(message)s'
    )
    
    # Create rotating file handlers (max 10MB, keep 5 files)
    server_handler = RotatingFileHandler(
        str(server_log), maxBytes=10*1024*1024, backupCount=5
    )
    server_handler.setLevel(logging.INFO)
    server_handler.setFormatter(simple_formatter)
    
    auth_handler = RotatingFileHandler(
        str(auth_log), maxBytes=10*1024*1024, backupCount=5
    )
    auth_handler.setLevel(logging.DEBUG)
    auth_handler.setFormatter(detailed_formatter)
    
    debug_handler = RotatingFileHandler(
        str(debug_log), maxBytes=10*1024*1024, backupCount=5
    )
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(detailed_formatter)
    
    error_handler = RotatingFileHandler(
        str(error_log), maxBytes=10*1024*1024, backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_formatter)
    
    # Console handler for immediate visibility
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.WARNING)  # Only show warnings and errors in console
    console_handler.setFormatter(simple_formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(server_handler)
    root_logger.addHandler(console_handler)
    
    # Configure specific loggers
    auth_logger = logging.getLogger("app.auth")
    auth_logger.setLevel(logging.DEBUG)
    auth_logger.addHandler(auth_handler)
    auth_logger.addHandler(error_handler)
    
    debug_logger = logging.getLogger("app.debug")
    debug_logger.setLevel(logging.DEBUG)
    debug_logger.addHandler(debug_handler)
    
    print_logger = logging.getLogger("app.print")
    print_logger.setLevel(logging.DEBUG)
    print_logger.addHandler(debug_handler)
    
    # Uvicorn loggers
    for uv_logger_name in ("uvicorn.error", "uvicorn.access", "uvicorn"):
        uv_logger = logging.getLogger(uv_logger_name)
        uv_logger.setLevel(logging.INFO)
        uv_logger.addHandler(server_handler)
        uv_logger.addHandler(error_handler)
    
    # Log startup message
    startup_logger = logging.getLogger("app.startup")
    startup_logger.info("Production logging configured successfully")
    startup_logger.info(f"Log files location: {log_dir}")
    startup_logger.info(f"Server log: {server_log}")
    startup_logger.info(f"Auth log: {auth_log}")
    startup_logger.info(f"Debug log: {debug_log}")
    startup_logger.info(f"Error log: {error_log}")


def log_environment_info() -> None:
    """Log important environment information for debugging."""
    env_logger = logging.getLogger("app.environment")
    
    env_info = {
        "PYTHON_VERSION": sys.version,
        "PLATFORM": sys.platform,
        "WORKING_DIRECTORY": os.getcwd(),
        "ENVIRONMENT_VARIABLES": {
            "AUTH_ENABLED": os.environ.get("AUTH_ENABLED"),
            "SESSION_SECRET_KEY": "***" if os.environ.get("SESSION_SECRET_KEY") else None,
            "COOKIE_SECURE": os.environ.get("COOKIE_SECURE"),
            "COOKIE_SAMESITE": os.environ.get("COOKIE_SAMESITE"),
            "SESSION_COOKIE_DOMAIN": os.environ.get("SESSION_COOKIE_DOMAIN"),
        }
    }
    
    env_logger.info("Environment information:")
    for key, value in env_info.items():
        env_logger.info(f"  {key}: {value}")


def log_request_details(request, logger_name: str = "app.requests") -> None:
    """Log detailed request information for debugging."""
    request_logger = logging.getLogger(logger_name)
    
    request_info = {
        "method": request.method,
        "url": str(request.url),
        "path": request.url.path,
        "query_params": dict(request.query_params),
        "headers": dict(request.headers),
        "cookies": dict(request.cookies),
        "client_ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    
    request_logger.debug("Request details:")
    for key, value in request_info.items():
        request_logger.debug(f"  {key}: {value}")


def log_session_details(request, logger_name: str = "app.sessions") -> None:
    """Log session information for debugging."""
    session_logger = logging.getLogger(logger_name)
    
    session_info = {
        "session_id": getattr(request.session, 'session_id', None),
        "session_keys": list(request.session.keys()) if hasattr(request.session, 'keys') else [],
        "session_data": dict(request.session),
        "session_modified": getattr(request.session, 'modified', False),
    }
    
    session_logger.debug("Session details:")
    for key, value in session_info.items():
        session_logger.debug(f"  {key}: {value}")
