# הוראות דיבאג לבעיית "אין הוצאות ב-3 חודשים האחרונים"

## מה הוספנו

הוספנו מערכת לוגינג מקיפה לבדיקת הבעיה עם הצגת ההוצאות ב-3 חודשים האחרונים.

### לוגים בשרת (Backend)

1. **לוגים בקובץ `app/backend/app/api/statistics.py`**:
   - לוגים מפורטים על כל שלב בעיבוד הנתונים
   - בדיקת הקאש (hit/miss)
   - הדפסת הנתונים שמתקבלים מהבסיס נתונים
   - בדיקת התאריכים והחישובים

2. **לוגים בקובץ `app/backend/app/services/cache_service.py`**:
   - לוגים על כל פעולת קאש (GET, SET, INVALIDATE)
   - מידע על סוג הנתונים ואורכם

3. **Endpoint חדש לבדיקה**: `/api/statistics/debug`
   - מחזיר מידע מפורט על הנתונים בבסיס הנתונים
   - בדיקת התאריכים
   - בדיקת הקאש

### לוגים בפרונט (Frontend)

1. **לוגים בקובץ `app/frontend/templates/pages/statistics.html`**:
   - הדפסות ל-console של הדפדפן
   - בדיקת הנתונים שמתקבלים מהשרת
   - בדיקה אם המערך ריק

## איך להשתמש

### 1. הפעלת השרת
```bash
cd app/backend
python -m uvicorn app.main:app --reload
```

### 2. בדיקת הלוגים
הלוגים נשמרים בקובץ: `app/logs/server.log`

### 3. בדיקת הנתונים
פתח את הדפדפן ובדוק:
- **עמוד הסטטיסטיקות**: `http://localhost:8000/statistics`
- **Endpoint דיבאג**: `http://localhost:8000/api/statistics/debug`

### 4. בדיקת Console בדפדפן
פתח את Developer Tools (F12) ובדוק את ה-Console למידע על הנתונים בפרונט.

## מה לחפש

### בלוגים של השרת:
1. **האם יש הוצאות ב-3 חודשים האחרונים?**
   - חפש: `"Last 3 months data"`
   - בדוק את `negative_count` (מספר ההוצאות)

2. **האם הקאש עובד?**
   - חפש: `"Cache HIT"` או `"Cache MISS"`
   - חפש: `"Top expenses query returned X results"`

3. **האם התאריכים נכונים?**
   - חפש: `"Current date"` ו-`"Three months ago"`

### ב-Console של הדפדפן:
1. **האם הנתונים מגיעים מהשרת?**
   - חפש: `"Top expenses data from server"`
   - בדוק את `"Top expenses length"`

2. **האם המערך ריק?**
   - חפש: `"WARNING: No top expenses found"`

## שליחת הלוגים

כדי לשלוח את הלוגים לבדיקה:
1. העתק את התוכן של `app/logs/server.log`
2. העתק את הפלט מה-Console של הדפדפן
3. שלח את שניהם יחד עם התוצאה של `/api/statistics/debug`

## אפשרויות נוספות לבדיקה

### ניקוי הקאש
אם אתה חושד שהקאש גורם לבעיה:
```bash
curl -X POST http://localhost:8000/api/statistics/clear-cache
```

### בדיקת סטטיסטיקות הקאש
```bash
curl http://localhost:8000/api/statistics/cache-stats
```
