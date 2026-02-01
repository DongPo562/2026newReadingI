from db_manager import DatabaseManager
from datetime import date

db = DatabaseManager()
db.connect()

today = date.today().isoformat()
cursor = db.connection.cursor()
cursor.execute(
    "UPDATE recordings SET next_review_date = ? WHERE next_review_date IS NULL",
    (today,)
)
print(f"已初始化 {cursor.rowcount} 条记录的 next_review_date")
db.connection.commit()
db.close()