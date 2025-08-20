from ..api import backup

def create_backup_file():
    """יוצר גיבוי חדש ומחזיר את הנתיב"""
    return backup.create_backup()

def list_backup_files():
    """מחזיר רשימת גיבויים קיימים"""
    return backup.list_backups()

def restore_from_file(path):
    """משחזר מסד נתונים מקובץ גיבוי"""
    return backup.restore_from_backup(path)
