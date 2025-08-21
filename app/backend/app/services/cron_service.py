import asyncio
import sqlite3
from datetime import datetime, date
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CronService:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.scheduler = AsyncIOScheduler()
        
    def start(self):
        """Start the CRON scheduler."""
        # Schedule challenge evaluation to run on the 1st of every month at 2:00 AM
        self.scheduler.add_job(
            self.evaluate_all_challenges,
            CronTrigger(day=1, hour=2, minute=0),
            id='challenge_evaluation',
            name='Monthly Challenge Evaluation',
            replace_existing=True
        )
        
        # Also run daily at midnight for active challenges
        self.scheduler.add_job(
            self.update_active_challenge_progress,
            CronTrigger(hour=0, minute=0),
            id='daily_progress_update',
            name='Daily Challenge Progress Update',
            replace_existing=True
        )
        
        self.scheduler.start()
        logger.info("CRON scheduler started successfully")
        
    def stop(self):
        """Stop the CRON scheduler."""
        self.scheduler.shutdown()
        logger.info("CRON scheduler stopped")
        
    async def evaluate_all_challenges(self):
        """Evaluate all active challenges that have ended."""
        logger.info("Starting monthly challenge evaluation...")
        
        try:
            with sqlite3.connect(self.db_path) as db_conn:
                db_conn.row_factory = sqlite3.Row
                today = date.today()
                
                # Get all active challenges that have ended
                active_challenges = db_conn.execute("""
                    SELECT uc.*, c.name as challenge_name, c.category, c.target_value, c.points
                    FROM user_challenges uc
                    JOIN challenges c ON uc.challenge_id = c.id
                    WHERE uc.status = 'active'
                    AND date(uc.end_date) <= date('now')
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
                                self._add_user_points(db_conn, user_id, row["points"])
                                logger.info(f"Challenge {row['challenge_name']} completed for user {user_id}")
                            else:
                                db_conn.execute("""
                                    UPDATE user_challenges 
                                    SET status = 'failed', current_progress = ?
                                    WHERE id = ?
                                """, (total_food, user_challenge_id))
                                failed_count += 1
                                logger.info(f"Challenge {row['challenge_name']} failed for user {user_id} (spent {total_food} on food)")
                        
                        elif "הוצאות" in row["challenge_name"]:
                            # Monthly expenses challenge
                            monthly_expenses = db_conn.execute("""
                                SELECT SUM(ABS(amount)) as total
                                FROM transactions
                                WHERE user_id = ? 
                                AND date >= ? 
                                AND date <= ?
                                AND amount < 0
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
                                self._add_user_points(db_conn, user_id, row["points"])
                                logger.info(f"Challenge {row['challenge_name']} completed for user {user_id} (spent {total_expenses} < {row['challenge_target']})")
                            else:
                                db_conn.execute("""
                                    UPDATE user_challenges 
                                    SET status = 'failed', current_progress = ?
                                    WHERE id = ?
                                """, (total_expenses, user_challenge_id))
                                failed_count += 1
                                logger.info(f"Challenge {row['challenge_name']} failed for user {user_id} (spent {total_expenses} >= {row['challenge_target']})")
                
                db_conn.commit()
                logger.info(f"Monthly evaluation complete: {completed_count} completed, {failed_count} failed")
                
        except Exception as e:
            logger.error(f"Error in monthly challenge evaluation: {e}")
            
    async def update_active_challenge_progress(self):
        """Update progress for all active challenges daily."""
        logger.info("Starting daily challenge progress update...")
        
        try:
            with sqlite3.connect(self.db_path) as db_conn:
                db_conn.row_factory = sqlite3.Row
                today = date.today()
                
                # Get all active challenges
                active_challenges = db_conn.execute("""
                    SELECT uc.*, c.name as challenge_name, c.category, c.target_value
                    FROM user_challenges uc
                    JOIN challenges c ON uc.challenge_id = c.id
                    WHERE uc.status = 'active'
                    AND date(uc.end_date) >= date('now')
                """).fetchall()
                
                updated_count = 0
                
                for challenge in active_challenges:
                    user_id = challenge["user_id"]
                    start_date = challenge["start_date"]
                    end_date = challenge["end_date"]
                    
                    # Calculate current progress based on challenge type
                    if "אוכל" in challenge["challenge_name"] or "נקי" in challenge["challenge_name"]:
                        # Food delivery challenges - track violations
                        food_expenses = db_conn.execute("""
                            SELECT SUM(ABS(amount)) as total
                            FROM transactions t
                            JOIN categories c ON t.category_id = c.id
                            WHERE t.user_id = ? 
                            AND t.date >= ? 
                            AND t.date <= ?
                            AND c.name LIKE '%מזון%'
                            AND t.amount < 0
                        """, (user_id, start_date, end_date)).fetchone()
                        
                        current_progress = food_expenses["total"] or 0
                        
                    elif "הוצאות" in challenge["challenge_name"]:
                        # Monthly expense challenges - track total expenses
                        monthly_expenses = db_conn.execute("""
                            SELECT SUM(ABS(amount)) as total
                            FROM transactions
                            WHERE user_id = ? 
                            AND date >= ? 
                            AND date <= ?
                            AND amount < 0
                        """, (user_id, start_date, end_date)).fetchone()
                        
                        current_progress = monthly_expenses["total"] or 0
                    
                    else:
                        continue
                    
                    # Update the challenge progress
                    db_conn.execute("""
                        UPDATE user_challenges 
                        SET current_progress = ?
                        WHERE id = ?
                    """, (current_progress, challenge["id"]))
                    
                    updated_count += 1
                
                db_conn.commit()
                logger.info(f"Daily progress update complete: {updated_count} challenges updated")
                
        except Exception as e:
            logger.error(f"Error in daily challenge progress update: {e}")
    
    def _add_user_points(self, db_conn: sqlite3.Connection, user_id: int, points: int) -> None:
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
                    logger.info(f"User {user_id} leveled up from {current_level} to {new_level}!")
                    break
            
            db_conn.execute("""
                UPDATE user_points 
                SET total_points = ?, current_level = ?, last_updated = ?
                WHERE user_id = ?
            """, (new_total, new_level, datetime.now().isoformat(), user_id))
