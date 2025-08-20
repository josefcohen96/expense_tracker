-- נכניס 50 עסקאות רנדומליות ל-6 חודשים האחרונים
WITH RECURSIVE months(x) AS (
  SELECT date('now', '-6 months', 'start of month')
  UNION ALL
  SELECT date(x, '+1 month')
  FROM months
  WHERE x < date('now', '-1 month', 'start of month')
)
INSERT INTO transactions (date, amount, category_id, user_id, account_id, notes, tags)
SELECT
  -- תאריך רנדומלי בחודש
  date(x, '+' || abs(random() % 28) || ' days'),
  -- סכום רנדומלי בין 20 ל-500
  round(20 + (abs(random()) % 480), 2),
  -- קטגוריה רנדומלית קיימת
  (SELECT id FROM categories ORDER BY random() LIMIT 1),
  -- משתמש רנדומלי (YOSEF או KARINA)
  (SELECT id FROM users ORDER BY random() LIMIT 1),
  -- חשבון רנדומלי (CASH או CARD)
  (SELECT id FROM accounts ORDER BY random() LIMIT 1),
  -- הערה רנדומלית
  'Generated expense',
  'seed'
FROM months, generate_series(1, 8); -- 8 עסקאות לכל חודש
