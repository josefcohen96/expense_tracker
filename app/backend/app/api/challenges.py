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
        SELECT id FROM user_challenges 
        WHERE user_id = ? AND challenge_id = ? AND status = 'active'
    """, (user_id, challenge_id)).fetchone()
    
    if existing:
        raise HTTPException(status_code=400, detail="User already has an active challenge of this type")
    
    # Calculate start and end dates
    today = date.today()
    if challenge.target_period == "week":
        end_date = today + timedelta(days=7)
    elif challenge.target_period == "month":
        end_date = today + timedelta(days=30)
    elif challenge.target_period == "year":
        end_date = today + timedelta(days=365)
    else:
        end_date = today + timedelta(days=30)  # Default to month
    
    # Create user challenge
    db_conn.execute("""
        INSERT INTO user_challenges (user_id, challenge_id, target_value, start_date, end_date)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, challenge_id, challenge.target_value, today.isoformat(), end_date.isoformat()))
    
    db_conn.commit()
    
    # Clear cache
    cache_service.invalidate(f"user_challenges_{user_id}")
    
    return JSONResponse({"message": "Challenge started successfully"})



@router.post("/evaluate")
async def evaluate_challenges(
    db_conn: sqlite3.Connection = Depends(get_db_conn)
) -> JSONResponse:
    """Evaluate all active challenges and update progress automatically."""
    today = date.today()
    
    # Get all active user challenges
    active_challenges = db_conn.execute("""
        SELECT uc.*, c.name as challenge_name, c.target_value as challenge_target, 
               c.target_period, c.points, c.category
        FROM user_challenges uc
        JOIN challenges c ON uc.challenge_id = c.id
        WHERE uc.status = 'active'
    """).fetchall()
    
    completed_count = 0
    failed_count = 0
    
    for row in active_challenges:
        user_challenge_id = row["id"]
        user_id = row["user_id"]
        challenge_id = row["challenge_id"]
        end_date = datetime.strptime(row["end_date"], "%Y-%m-%d").date()
        
        # Check if challenge period has ended
        if today >= end_date:
            # Evaluate the challenge based on its type
            if row["category"] == "expertise" and "אוכל" in row["challenge_name"]:
                # Food delivery challenge - check if any food expenses in the period
                food_expenses = db_conn.execute("""
                    SELECT SUM(ABS(amount)) as total
                    FROM transactions t
                    JOIN categories c ON t.category_id = c.id
                    WHERE t.user_id = ? 
                    AND t.date >= ? 
                    AND t.date <= ?
                    AND c.name LIKE '%מזון%'
                    AND t.amount < 0
                    AND t.recurrence_id IS NULL
                """, (user_id, row["start_date"], row["end_date"])).fetchone()
                
                total_food = food_expenses["total"] or 0
                
                if total_food == 0:  # No food expenses - challenge completed
                    db_conn.execute("""
                        UPDATE user_challenges 
                        SET status = 'completed', completed_at = ?, points_earned = ?
                        WHERE id = ?
                    """, (today.isoformat(), row["points"], user_challenge_id))
                    completed_count += 1
                    
                    # Add points to user
                    _add_user_points(db_conn, user_id, row["points"])
                else:
                    db_conn.execute("""
                        UPDATE user_challenges 
                        SET status = 'failed', current_progress = ?
                        WHERE id = ?
                    """, (total_food, user_challenge_id))
                    failed_count += 1
            
            elif "הוצאות" in row["challenge_name"]:
                # Monthly expenses challenge
                monthly_expenses = db_conn.execute("""
                    SELECT SUM(ABS(amount)) as total
                    FROM transactions
                    WHERE user_id = ? 
                    AND date >= ? 
                    AND date <= ?
                    AND amount < 0
                    AND recurrence_id IS NULL
                """, (user_id, row["start_date"], row["end_date"])).fetchone()
                
                total_expenses = monthly_expenses["total"] or 0
                
                if total_expenses < row["challenge_target"]:
                    db_conn.execute("""
                        UPDATE user_challenges 
                        SET status = 'completed', completed_at = ?, points_earned = ?
                        WHERE id = ?
                    """, (today.isoformat(), row["points"], user_challenge_id))
                    completed_count += 1
                    
                    # Add points to user
                    _add_user_points(db_conn, user_id, row["points"])
                else:
                    db_conn.execute("""
                        UPDATE user_challenges 
                        SET status = 'failed', current_progress = ?
                        WHERE id = ?
                    """, (total_expenses, user_challenge_id))
                    failed_count += 1
    
    db_conn.commit()
    
    return JSONResponse({
        "message": f"Evaluation complete: {completed_count} completed, {failed_count} failed"
    })

@router.get("/user/{user_id}/points")
async def get_user_points(
    user_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn)
) -> JSONResponse:
    """Get user's points and level."""
    points_row = db_conn.execute("""
        SELECT * FROM user_points WHERE user_id = ?
    """, (user_id,)).fetchone()
    
    if not points_row:
        # Create user points record if doesn't exist
        db_conn.execute("""
            INSERT INTO user_points (user_id, total_points, current_level, level_progress)
            VALUES (?, 0, 'bronze', 0)
        """, (user_id,))
        db_conn.commit()
        
        return JSONResponse({
            "total_points": 0,
            "current_level": "bronze",
            "level_progress": 0,
            "next_level": "silver",
            "points_to_next": 100
        })
    
    total_points = points_row["total_points"]
    current_level = points_row["current_level"]
    
    # Calculate level progress
    level_thresholds = {
        "bronze": 0,
        "silver": 100,
        "gold": 300,
        "platinum": 600,
        "master": 1000
    }
    
    current_threshold = level_thresholds.get(current_level, 0)
    next_level = "master"
    points_to_next = 0
    
    for level, threshold in level_thresholds.items():
        if threshold > total_points:
            next_level = level
            points_to_next = threshold - total_points
            break
    
    level_progress = 0
    if current_level != "master":
        level_progress = ((total_points - current_threshold) / (level_thresholds[next_level] - current_threshold)) * 100
    
    return JSONResponse({
        "total_points": total_points,
        "current_level": current_level,
        "level_progress": round(level_progress, 1),
        "next_level": next_level,
        "points_to_next": points_to_next
    })



def _add_user_points(db_conn: sqlite3.Connection, user_id: int, points: int) -> None:
    """Add points to user and update level."""
    # Get current points
    points_row = db_conn.execute("""
        SELECT * FROM user_points WHERE user_id = ?
    """, (user_id,)).fetchone()
    
    if not points_row:
        db_conn.execute("""
            INSERT INTO user_points (user_id, total_points, current_level, level_progress)
            VALUES (?, ?, 'bronze', 0)
        """, (user_id, points))
    else:
        new_total = points_row["total_points"] + points
        current_level = points_row["current_level"]
        
        # Check if level should increase
        level_thresholds = {
            "bronze": 100,
            "silver": 300,
            "gold": 600,
            "platinum": 1000
        }
        
        new_level = current_level
        for level, threshold in level_thresholds.items():
            if new_total >= threshold and current_level != level:
                new_level = level
                break
        
        db_conn.execute("""
            UPDATE user_points 
            SET total_points = ?, current_level = ?, last_updated = ?
            WHERE user_id = ?
        """, (new_total, new_level, datetime.now().isoformat(), user_id))
