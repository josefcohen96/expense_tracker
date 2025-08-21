"""
Challenges API endpoints for managing user challenges and progress tracking.
"""

from typing import List, Optional
import sqlite3
from datetime import datetime, timedelta, date
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from ..schemas import Challenge, ChallengeCreate, UserChallenge, UserChallengeCreate, ChallengeProgress, ChallengeProgressCreate, UserPoints, ChallengeStatus
from ..db import get_db_conn
from ..services.cache_service import cache_service

router = APIRouter(prefix="/api/challenges", tags=["challenges"])

@router.get("", response_model=List[Challenge])
async def get_challenges(
    db_conn: sqlite3.Connection = Depends(get_db_conn)
    ) -> List[Challenge]:
    """Get all available challenges."""
    rows = db_conn.execute("""
        SELECT * FROM challenges 
        WHERE is_active = 1 
        ORDER BY difficulty, points
    """).fetchall()
    return [Challenge(**dict(row)) for row in rows]

@router.get("/user/{user_id}", response_model=List[ChallengeStatus])
async def get_user_challenges(
    user_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn)
    ) -> List[ChallengeStatus]:
    """Get all challenges with user progress."""
    # Get all active challenges
    challenges = db_conn.execute("""
        SELECT * FROM challenges WHERE is_active = 1
    """).fetchall()
    
    result = []
    for challenge_row in challenges:
        challenge = Challenge(**dict(challenge_row))
        
        # Get user's active challenge for this challenge type
        user_challenge_row = db_conn.execute("""
            SELECT * FROM user_challenges 
            WHERE user_id = ? AND challenge_id = ? AND status = 'active'
            ORDER BY start_date DESC LIMIT 1
        """, (user_id, challenge.id)).fetchone()
        
        user_challenge = None
        progress_percentage = 0
        days_remaining = 0
        is_completed = False
        is_failed = False
        
        if user_challenge_row:
            user_challenge = UserChallenge(**dict(user_challenge_row))
            
            # Calculate progress
            if challenge.target_value > 0:
                progress_percentage = min(100, (user_challenge.current_progress / challenge.target_value) * 100)
            else:
                # For "no spending" challenges, progress is based on days completed
                start_date = datetime.strptime(user_challenge.start_date, "%Y-%m-%d").date()
                end_date = datetime.strptime(user_challenge.end_date, "%Y-%m-%d").date()
                today = date.today()
                
                total_days = (end_date - start_date).days
                days_completed = (today - start_date).days
                
                if total_days > 0:
                    progress_percentage = min(100, (days_completed / total_days) * 100)
                
                days_remaining = max(0, (end_date - today).days)
                
                # Check if completed or failed
                if today >= end_date:
                    if user_challenge.current_progress == 0:  # No violations
                        is_completed = True
                    else:
                        is_failed = True
        
        result.append(ChallengeStatus(
            challenge=challenge,
            user_challenge=user_challenge,
            progress_percentage=progress_percentage,
            days_remaining=days_remaining,
            is_completed=is_completed,
            is_failed=is_failed
        ))
    
    return result

@router.post("/start/{challenge_id}")
async def start_challenge(
    challenge_id: int,
    user_id: int = Query(...),
    db_conn: sqlite3.Connection = Depends(get_db_conn)
) -> JSONResponse:
    """Start a new challenge for a user."""
    # Get challenge details
    challenge_row = db_conn.execute("""
        SELECT * FROM challenges WHERE id = ? AND is_active = 1
    """, (challenge_id,)).fetchone()
    
    if not challenge_row:
        raise HTTPException(status_code=404, detail="Challenge not found")
    
    challenge = Challenge(**dict(challenge_row))
    
    # Check if user already has an active challenge of this type
    existing = db_conn.execute("""
        SELECT * FROM user_challenges 
        WHERE user_id = ? AND challenge_id = ? AND status = 'active'
    """, (user_id, challenge_id)).fetchone()
    
    if existing:
        raise HTTPException(status_code=400, detail="User already has an active challenge of this type")
    
    # Calculate start and end dates based on challenge period
    today = date.today()
    start_date = today
    
    if challenge.target_period == 'week':
        end_date = today + timedelta(days=7)
    elif challenge.target_period == 'month':
        # Add one month
        if today.month == 12:
            end_date = date(today.year + 1, 1, today.day)
        else:
            end_date = date(today.year, today.month + 1, today.day)
    elif challenge.target_period == 'year':
        end_date = date(today.year + 1, today.month, today.day)
    else:
        raise HTTPException(status_code=400, detail="Invalid challenge period")
    
    # Create user challenge
    cur = db_conn.execute("""
        INSERT INTO user_challenges (user_id, challenge_id, target_value, start_date, end_date, status)
        VALUES (?, ?, ?, ?, ?, 'active')
    """, (user_id, challenge_id, challenge.target_value, start_date.isoformat(), end_date.isoformat()))
    
    db_conn.commit()
    
    return JSONResponse({
        "message": "Challenge started successfully",
        "challenge_id": challenge_id,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat()
    })

@router.post("/progress/{user_challenge_id}")
async def update_challenge_progress(
    user_challenge_id: int,
    progress: ChallengeProgressCreate,
    db_conn: sqlite3.Connection = Depends(get_db_conn)
) -> JSONResponse:
    """Update challenge progress."""
    # Get user challenge
    user_challenge_row = db_conn.execute("""
        SELECT * FROM user_challenges WHERE id = ?
    """, (user_challenge_id,)).fetchone()
    
    if not user_challenge_row:
        raise HTTPException(status_code=404, detail="User challenge not found")
    
    user_challenge = UserChallenge(**dict(user_challenge_row))
    
    if user_challenge.status != 'active':
        raise HTTPException(status_code=400, detail="Challenge is not active")
    
    # Add progress record
    today = date.today().isoformat()
    cur = db_conn.execute("""
        INSERT INTO challenge_progress (user_challenge_id, progress_date, progress_value, notes)
        VALUES (?, ?, ?, ?)
    """, (user_challenge_id, today, progress.progress_value, progress.notes))
    
    # Update current progress
    db_conn.execute("""
        UPDATE user_challenges 
        SET current_progress = current_progress + ?
        WHERE id = ?
    """, (progress.progress_value, user_challenge_id))
    
    db_conn.commit()
    
    return JSONResponse({"message": "Progress updated successfully"})

@router.get("/points/{user_id}")
async def get_user_points(
    user_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn)
) -> UserPoints:
    """Get user points and level information."""
    row = db_conn.execute("""
        SELECT * FROM user_points WHERE user_id = ?
    """, (user_id,)).fetchone()
    
    if not row:
        # Create default user points record
        db_conn.execute("""
            INSERT INTO user_points (user_id, total_points, current_level, level_progress)
            VALUES (?, 0, 'bronze', 0)
        """, (user_id,))
        db_conn.commit()
        
        row = db_conn.execute("""
            SELECT * FROM user_points WHERE user_id = ?
        """, (user_id,)).fetchone()
    
    return UserPoints(**dict(row))
