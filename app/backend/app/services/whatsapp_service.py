"""
WhatsApp integration service.

Responsibilities:
- Parse incoming WhatsApp text into amount, description, category, date.
- Resolve or create `users`, resolve or create `categories`.
- Find default `accounts` id (first or configured) and insert a negative `transactions` row.
- Send confirmation/error back via WhatsApp Cloud API using httpx.

Environment variables used:
- META_VERIFY_TOKEN: used by webhook (in API layer)
- WHATSAPP_TOKEN: Bearer token for Cloud API
- WHATSAPP_PHONE_ID: Business phone id for sending messages
- DEFAULT_USER_ID: optional fixed user id
- DEFAULT_CATEGORY_NAME: fallback category name if none parsed
- DEFAULT_ACCOUNT_ID: optional fixed account id
"""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional, Tuple, Dict, Any

import httpx


@dataclass
class ParsedMessage:
    amount: float
    description: Optional[str]
    category_name: Optional[str]
    date_str: str  # YYYY-MM-DD


class WhatsAppService:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.whatsapp_token = os.getenv("WHATSAPP_TOKEN", "")
        self.whatsapp_phone_id = os.getenv("WHATSAPP_PHONE_ID", "")
        # Basic Hebrew keyword → category mapping for inference when no hashtag is provided
        # You can expand this mapping as needed.
        self._category_keywords = {
            # groceries / shopping
            "קניות": "קניות",
            "שופרסל": "מזון",
            "סופר": "מזון",
            "מכולת": "מזון",
            # transport / car
            "דלק": "רכב",
            "נסיעה": "תחבורה",
            "חניה": "רכב",
        }

    # --------------- Parsing ---------------
    @staticmethod
    def _normalize_decimal(text: str) -> str:
        return text.replace(",", ".")

    @staticmethod
    def parse_text(message_text: str) -> ParsedMessage:
        """
        Supported free-form formats, examples:
        - "37.5 שופרסל #מצרכים 2025-08-25"
        - "120 דלק #רכב"
        - "56.9 #מזון"
        - "45"
        Rules:
        - amount: first number (supports dot or comma)
        - category: first hashtag token without '#'
        - date: first YYYY-MM-DD occurrence, else today
        - description: remaining text without hashtags/date, trimmed
        """
        text = message_text.strip()
        # amount
        amt_match = re.search(r"(?P<amt>[0-9]+[\.,]?[0-9]*)", WhatsAppService._normalize_decimal(text))
        if not amt_match:
            raise ValueError("לא נמצא סכום בהודעה. נא לשלוח לדוגמה: '37.5 שופרסל #מצרכים 2025-08-25'")
        amount = float(amt_match.group("amt"))

        # date
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
        if date_match:
            date_str = date_match.group(1)
        else:
            date_str = date.today().isoformat()

        # category (hashtag)
        cat_match = re.search(r"#([\wא-ת-]+)", text)
        category_name = cat_match.group(1) if cat_match else None

        # description = remove amount, date, hashtags
        cleaned = re.sub(r"#([\wא-ת-]+)", "", text)
        cleaned = re.sub(r"\d{4}-\d{2}-\d{2}", "", cleaned)
        # remove the first number occurrence only
        cleaned = re.sub(r"(?P<amt>[0-9]+[\.,]?[0-9]*)", "", cleaned, count=1)
        description = cleaned.strip()
        if description == "":
            description = None

        return ParsedMessage(amount=amount, description=description, category_name=category_name, date_str=date_str)

    def _infer_category_from_text(self, text: str) -> Optional[str]:
        lowered = text.lower()
        # Try exact Hebrew tokens by scanning original as well
        for keyword, category in self._category_keywords.items():
            if keyword in text:
                return category
        return None

    # --------------- DB Helpers ---------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _find_or_create_user_by_phone(self, db_conn: sqlite3.Connection, phone_number: str) -> int:
        """
        Strategy:
        - If DEFAULT_USER_ID is set, use it.
        - Else use users.name as the phone number (unique) and upsert.
        """
        default_user_id = os.getenv("DEFAULT_USER_ID")
        if default_user_id:
            return int(default_user_id)

        row = db_conn.execute("SELECT id FROM users WHERE name = ?", (phone_number,)).fetchone()
        if row:
            return int(row["id"])
        cur = db_conn.execute("INSERT INTO users (name) VALUES (?)", (phone_number,))
        db_conn.commit()
        return int(cur.lastrowid)

    def _find_or_create_category(self, db_conn: sqlite3.Connection, category_name: Optional[str]) -> int:
        if not category_name:
            category_name = os.getenv("DEFAULT_CATEGORY_NAME", "מזון")
        row = db_conn.execute("SELECT id FROM categories WHERE name = ?", (category_name,)).fetchone()
        if row:
            return int(row["id"])
        cur = db_conn.execute("INSERT INTO categories (name) VALUES (?)", (category_name,))
        db_conn.commit()
        return int(cur.lastrowid)

    def _get_default_account_id(self, db_conn: sqlite3.Connection) -> Optional[int]:
        env_acc = os.getenv("DEFAULT_ACCOUNT_ID")
        if env_acc:
            return int(env_acc)
        row = db_conn.execute("SELECT id FROM accounts ORDER BY id ASC LIMIT 1").fetchone()
        return int(row["id"]) if row else None

    def create_expense_transaction(
        self,
        phone_number: str,
        message_text: str,
    ) -> Dict[str, Any]:
        """Parse text and insert a new negative transaction. Returns inserted row dict."""
        parsed = self.parse_text(message_text)

        with self._connect() as db_conn:
            user_id = self._find_or_create_user_by_phone(db_conn, phone_number)
            # If no hashtag category provided, try to infer from text
            category_name = parsed.category_name or self._infer_category_from_text(message_text)
            category_id = self._find_or_create_category(db_conn, category_name)
            account_id = self._get_default_account_id(db_conn)

            amount_negative = -abs(parsed.amount)
            cur = db_conn.execute(
                """
                INSERT INTO transactions (date, amount, category_id, user_id, account_id, notes, tags, recurrence_id, period_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                """,
                (
                    parsed.date_str,
                    amount_negative,
                    category_id,
                    user_id,
                    account_id,
                    parsed.description,
                    None,
                ),
            )
            db_conn.commit()
            new_id = int(cur.lastrowid)

            row = db_conn.execute("SELECT * FROM transactions WHERE id = ?", (new_id,)).fetchone()
            return dict(row)

    # --------------- WhatsApp Cloud API ---------------
    async def send_text_message(self, to_phone_e164: str, text: str) -> None:
        if not (self.whatsapp_token and self.whatsapp_phone_id):
            return  # silently ignore in dev if not configured

        url = f"https://graph.facebook.com/v19.0/{self.whatsapp_phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.whatsapp_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone_e164,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                await client.post(url, headers=headers, json=payload)
            except Exception:
                # Avoid raising to not break webhook handler
                pass

    # --------------- Orchestration ---------------
    async def handle_incoming(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extract sender phone and message text from Meta webhook payload and create expense.
        Returns inserted transaction dict on success, None otherwise.
        """
        try:
            entry = payload.get("entry", [])[0]
            change = entry.get("changes", [])[0]
            value = change.get("value", {})
            messages = value.get("messages", [])
            if not messages:
                return None
            msg = messages[0]
            msg_type = msg.get("type")
            if msg_type != "text":
                return None
            text = msg.get("text", {}).get("body", "").strip()
            contacts = value.get("contacts", [])
            wa_id = contacts[0].get("wa_id") if contacts else msg.get("from")
            if not wa_id:
                return None

            # Insert transaction
            inserted = self.create_expense_transaction(wa_id, text)

            # Send confirmation
            amount = inserted.get("amount")
            category_id = inserted.get("category_id")
            date_s = inserted.get("date")
            confirm = f"נקלטה הוצאה של {abs(amount):.2f}- ₪ בתאריך {date_s}. תודה!"
            await self.send_text_message(wa_id, confirm)
            return inserted
        except ValueError as ve:
            # parsing error
            try:
                wa_id = payload.get("entry", [])[0].get("changes", [])[0].get("value", {}).get("contacts", [{}])[0].get("wa_id")
                if wa_id:
                    await self.send_text_message(wa_id, str(ve))
            except Exception:
                pass
            return None
        except Exception:
            try:
                wa_id = payload.get("entry", [])[0].get("changes", [])[0].get("value", {}).get("contacts", [{}])[0].get("wa_id")
                if wa_id:
                    await self.send_text_message(wa_id, "אירעה שגיאה בטיפול בהודעה. נסו שוב מאוחר יותר.")
            except Exception:
                pass
            return None


# Convenience factory used by API layer
def get_whatsapp_service(db_path: str) -> WhatsAppService:
    return WhatsAppService(db_path)


