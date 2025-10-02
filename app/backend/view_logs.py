#!/usr/bin/env python3
"""
Script to view logs in real-time for debugging production issues.
Usage: python view_logs.py [log_type]
Log types: server, auth, debug, errors, all
"""

import sys
import os
from pathlib import Path
import argparse
from datetime import datetime


def get_log_dir():
    """Get the logs directory path."""
    script_dir = Path(__file__).parent
    return script_dir / "logs"


def view_log_file(log_path: Path, lines: int = 50):
    """View the last N lines of a log file."""
    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        return
    
    print(f"\n{'='*80}")
    print(f"Viewing: {log_path.name}")
    print(f"Last {lines} lines:")
    print(f"{'='*80}")
    
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            last_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            
            for line in last_lines:
                print(line.rstrip())
    except Exception as e:
        print(f"Error reading log file: {e}")


def tail_log_file(log_path: Path):
    """Tail a log file in real-time (simplified version)."""
    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        return
    
    print(f"\nTailing: {log_path.name}")
    print("Press Ctrl+C to stop")
    print(f"{'='*80}")
    
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            # Go to end of file
            f.seek(0, 2)
            
            while True:
                line = f.readline()
                if line:
                    print(line.rstrip())
                else:
                    import time
                    time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopped tailing.")
    except Exception as e:
        print(f"Error tailing log file: {e}")


def main():
    parser = argparse.ArgumentParser(description="View application logs")
    parser.add_argument("log_type", nargs="?", default="all", 
                       choices=["server", "auth", "debug", "errors", "all"],
                       help="Type of log to view")
    parser.add_argument("-l", "--lines", type=int, default=50,
                       help="Number of lines to show (default: 50)")
    parser.add_argument("-t", "--tail", action="store_true",
                       help="Tail the log file in real-time")
    
    args = parser.parse_args()
    
    log_dir = get_log_dir()
    
    if not log_dir.exists():
        print(f"Logs directory not found: {log_dir}")
        print("Make sure the application has been run at least once.")
        return
    
    log_files = {
        "server": log_dir / "server.log",
        "auth": log_dir / "auth.log", 
        "debug": log_dir / "debug.log",
        "errors": log_dir / "errors.log"
    }
    
    if args.log_type == "all":
        for log_name, log_path in log_files.items():
            if args.tail:
                print(f"Cannot tail multiple files. Please specify a single log type.")
                return
            view_log_file(log_path, args.lines)
    else:
        log_path = log_files.get(args.log_type)
        if log_path:
            if args.tail:
                tail_log_file(log_path)
            else:
                view_log_file(log_path, args.lines)
        else:
            print(f"Unknown log type: {args.log_type}")


if __name__ == "__main__":
    main()
