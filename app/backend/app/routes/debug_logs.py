from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from pathlib import Path
import os
import logging

router = APIRouter(tags=["debug"])

@router.get("/debug/logs", response_class=PlainTextResponse)
async def view_logs_endpoint(request: Request, lines: int = 100):
    """Debug endpoint to view logs in production."""
    
    # Only allow in development or if user is authenticated
    is_production = os.environ.get("RAILWAY_ENVIRONMENT") is not None
    if is_production:
        # Check if user is authenticated
        if not hasattr(request, 'session') or not request.session.get('user'):
            raise HTTPException(status_code=401, detail="Authentication required")
    
    log_dir = Path(__file__).parent.parent / "logs"
    
    if not log_dir.exists():
        return "Logs directory not found"
    
    log_file = log_dir / "server.log"
    
    if not log_file.exists():
        return "Server log file not found"
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            last_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            
            result = []
            result.append(f"=== Last {len(last_lines)} lines from server.log ===\n")
            result.extend(last_lines)
            
            return "".join(result)
    except Exception as e:
        return f"Error reading log file: {e}"

@router.get("/debug/logs/auth", response_class=PlainTextResponse)
async def view_auth_logs_endpoint(request: Request, lines: int = 100):
    """Debug endpoint to view auth logs."""
    
    # Only allow in development or if user is authenticated
    is_production = os.environ.get("RAILWAY_ENVIRONMENT") is not None
    if is_production:
        if not hasattr(request, 'session') or not request.session.get('user'):
            raise HTTPException(status_code=401, detail="Authentication required")
    
    log_dir = Path(__file__).parent.parent / "logs"
    log_file = log_dir / "auth.log"
    
    if not log_file.exists():
        return "Auth log file not found"
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            last_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            
            result = []
            result.append(f"=== Last {len(last_lines)} lines from auth.log ===\n")
            result.extend(last_lines)
            
            return "".join(result)
    except Exception as e:
        return f"Error reading log file: {e}"

@router.get("/debug/logs/errors", response_class=PlainTextResponse)
async def view_error_logs_endpoint(request: Request, lines: int = 100):
    """Debug endpoint to view error logs."""
    
    # Only allow in development or if user is authenticated
    is_production = os.environ.get("RAILWAY_ENVIRONMENT") is not None
    if is_production:
        if not hasattr(request, 'session') or not request.session.get('user'):
            raise HTTPException(status_code=401, detail="Authentication required")
    
    log_dir = Path(__file__).parent.parent / "logs"
    log_file = log_dir / "errors.log"
    
    if not log_file.exists():
        return "Error log file not found"
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            last_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            
            result = []
            result.append(f"=== Last {len(last_lines)} lines from errors.log ===\n")
            result.extend(last_lines)
            
            return "".join(result)
    except Exception as e:
        return f"Error reading log file: {e}"
