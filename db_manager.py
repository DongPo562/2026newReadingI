import sqlite3
import os
import time
import logging
import threading
from config_loader import app_config

class DatabaseManager:
    def __init__(self):
        self.db_path = app_config.db_path
        self.wal_mode = app_config.db_wal_mode
        self.busy_timeout = app_config.db_busy_timeout
        self.retry_count = app_config.db_retry_count
        self._local = threading.local()

    def connect(self):
        try:
            conn = getattr(self._local, "connection", None)
            if conn is not None:
                return conn

            conn = sqlite3.connect(self.db_path, timeout=5.0)
            conn.execute(f"PRAGMA busy_timeout = {self.busy_timeout}")
            if self.wal_mode:
                conn.execute("PRAGMA journal_mode=WAL")
            conn.row_factory = sqlite3.Row
            self._local.connection = conn
            return conn
        except sqlite3.Error as e:
            print(f"Database connection error: {e}")
            raise

    def get_connection(self):
        conn = getattr(self._local, "connection", None)
        if conn is None:
            conn = self.connect()
        return conn

    @property
    def connection(self):
        return self.get_connection()

    @connection.setter
    def connection(self, value):
        self._local.connection = value

    def close(self):
        conn = getattr(self._local, "connection", None)
        if conn:
            conn.close()
            self._local.connection = None

    def init_db(self):
        if not self.connection:
            self.connect()
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS recordings (
            number INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            remember INTEGER DEFAULT 0,
            forget INTEGER DEFAULT 0,
            date DATE NOT NULL
        );
        """
        create_index_sql = "CREATE INDEX IF NOT EXISTS idx_date ON recordings(date);"
        try:
            with self.connection:
                self.connection.execute(create_table_sql)
                self.connection.execute(create_index_sql)
            # 阶段三：执行字段迁移
            self.migrate_add_review_fields()

            # Phase 1: Letter Sequence Migration
            self.migrate_add_letter_sequence()

            # Quiz: review_questions 表迁移
            self.migrate_create_review_questions()
        except sqlite3.Error as e:
            print(f"Database initialization error: {e}")
            raise

    def _execute_with_retry(self, operation_func):
        if not self.connection:
            self.connect()
        for attempt in range(self.retry_count):
            try:
                return operation_func()
            except sqlite3.OperationalError as e:
                if "locked" in str(e) and attempt < self.retry_count - 1:
                    time.sleep(0.1 * (attempt + 1))
                    continue
                else:
                    raise
            except Exception as e:
                raise

    def insert_recording(self, content, date_str):
        def operation():
            cursor = self.connection.cursor()
            cursor.execute(
                "INSERT INTO recordings (content, date) VALUES (?, ?)",
                (content, date_str)
            )
            self.connection.commit()
            return cursor.lastrowid
        return self._execute_with_retry(operation)

    def delete_recording(self, number):
        def operation():
            cursor = self.connection.cursor()
            cursor.execute("DELETE FROM recordings WHERE number = ?", (number,))
            self.connection.commit()
        return self._execute_with_retry(operation)

    def get_recordings_by_date(self, date_str):
        def operation():
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT number, content, date FROM recordings WHERE date = ? ORDER BY number DESC",
                (date_str,)
            )
            return cursor.fetchall()
        return self._execute_with_retry(operation)

    def get_all_dates(self, limit=15):
        def operation():
            cursor = self.connection.cursor()
            cursor.execute(
                f"SELECT DISTINCT date FROM recordings ORDER BY date DESC LIMIT {limit}"
            )
            return [row['date'] for row in cursor.fetchall()]
        return self._execute_with_retry(operation)

    def get_content(self, number):
        def operation():
            cursor = self.connection.cursor()
            cursor.execute("SELECT content FROM recordings WHERE number = ?", (number,))
            row = cursor.fetchone()
            return row['content'] if row else None
        return self._execute_with_retry(operation)

    def get_dates_exceeding_limit(self, limit=15):
        def operation():
            cursor = self.connection.cursor()
            cursor.execute("SELECT DISTINCT date FROM recordings ORDER BY date DESC")
            all_dates = [row['date'] for row in cursor.fetchall()]
            if len(all_dates) > limit:
                return sorted(all_dates[limit:])
            return []
        return self._execute_with_retry(operation)

    def get_recordings_by_date_list(self, date_list):
        if not date_list:
            return []
        def operation():
            cursor = self.connection.cursor()
            placeholders = ','.join(['?'] * len(date_list))
            query = f"SELECT number, date FROM recordings WHERE date IN ({placeholders})"
            cursor.execute(query, date_list)
            return cursor.fetchall()
        return self._execute_with_retry(operation)

    def get_all_recordings_for_consistency_check(self):
        def operation():
            cursor = self.connection.cursor()
            cursor.execute("SELECT number, date FROM recordings")
            return cursor.fetchall()
        return self._execute_with_retry(operation)

    def get_recording_by_number(self, number):
        def operation():
            cursor = self.connection.cursor()
            cursor.execute("SELECT * FROM recordings WHERE number = ?", (number,))
            return cursor.fetchone()
        return self._execute_with_retry(operation)

    # ==================== 新增：内容去重相关方法 ====================
    def get_recording_by_content(self, content):
        """
        根据 content 查询是否已存在记录

        Args:
            content: 要查询的文本内容

        Returns:
            sqlite3.Row 或 None: 如果存在则返回记录，否则返回 None
        """
        def operation():
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT * FROM recordings WHERE content = ?",
                (content,)
            )
            return cursor.fetchone()
        return self._execute_with_retry(operation)

    def update_recording_date(self, number, date_str):
        """
        更新记录的 date 字段（最近一次录音时间）

        Args:
            number: 录音记录的 number
            date_str: 新的日期字符串 (YYYY-MM-DD)
        """
        def operation():
            cursor = self.connection.cursor()
            cursor.execute(
                "UPDATE recordings SET date = ? WHERE number = ?",
                (date_str, number)
            )
            self.connection.commit()
        return self._execute_with_retry(operation)

    # ==================== 阶段三：数据库字段扩展 + 迁移 ====================
    def migrate_add_review_fields(self):
        """迁移：添加 Leitner 盒子系统所需的字段"""
        if not self.connection:
            self.connect()

        from datetime import date
        today = date.today().isoformat()

        migrations = [
            ("box_level", "INTEGER DEFAULT 1"),
            ("next_review_date", "DATE"),
            ("last_review_date", "DATE")
        ]

        for field_name, field_type in migrations:
            try:
                self.connection.execute(f"ALTER TABLE recordings ADD COLUMN {field_name} {field_type}")
                print(f"[Migration] Added column: {field_name}")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    print(f"[Migration] Column already exists: {field_name}")
                else:
                    raise

        # 为现有记录设置初始值
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "UPDATE recordings SET box_level = 1, next_review_date = ? WHERE box_level IS NULL",
                (today,)
            )
            if cursor.rowcount > 0:
                print(f"[Migration] Initialized {cursor.rowcount} existing records")
            self.connection.commit()
        except sqlite3.Error as e:
            print(f"[Migration] Error initializing records: {e}")

    # ==================== 阶段四：复习相关查询方法 ====================
    def get_words_to_review(self):
        """获取待复习的单词列表（next_review_date <= 今天）"""
        def operation():
            from datetime import date
            today = date.today().isoformat()
            cursor = self.connection.cursor()
            cursor.execute(
                """SELECT number, content, box_level, next_review_date, last_review_date, remember, forget
                   FROM recordings
                   WHERE next_review_date <= ?
                   ORDER BY box_level ASC, next_review_date ASC""",
                (today,)
            )
            return cursor.fetchall()
        return self._execute_with_retry(operation)

    def update_word_box(self, number, box_level, next_review_date, remember, forget, last_review_date):
        """更新单词的复习状态"""
        def operation():
            cursor = self.connection.cursor()
            cursor.execute(
                """UPDATE recordings
                   SET box_level = ?, next_review_date = ?, remember = ?, forget = ?, last_review_date = ?
                   WHERE number = ?""",
                (box_level, next_review_date, remember, forget, last_review_date, number)
            )
            self.connection.commit()
        return self._execute_with_retry(operation)

    def get_review_stats(self):
        """获取复习统计信息"""
        def operation():
            from datetime import date
            from text_processor import is_valid_word
            today = date.today().isoformat()
            cursor = self.connection.cursor()

            # 待复习数量（仅合法单词）
            cursor.execute(
                "SELECT content FROM recordings WHERE next_review_date <= ?",
                (today,)
            )
            pending = sum(1 for row in cursor.fetchall() if is_valid_word(row['content']))

            # 今日已完成数量（仅合法单词）
            cursor.execute(
                "SELECT content FROM recordings WHERE last_review_date = ?",
                (today,)
            )
            completed = sum(1 for row in cursor.fetchall() if is_valid_word(row['content']))

            return {'pending': pending, 'completed': completed}
        return self._execute_with_retry(operation)

    # ==================== Phase 1: Letter Sequence Matching ====================
    def migrate_add_letter_sequence(self):
        """Migration: Add letter_sequence column and populate it."""
        if not self.connection:
            self.connect()

        try:
            self.connection.execute("ALTER TABLE recordings ADD COLUMN letter_sequence TEXT")
            print("[Migration] Added column: letter_sequence")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("[Migration] Column already exists: letter_sequence")
            else:
                raise

        # Create index
        try:
            self.connection.execute("CREATE INDEX IF NOT EXISTS idx_letter_sequence ON recordings(letter_sequence);")
        except sqlite3.Error as e:
            print(f"[Migration] Error creating index: {e}")

        # Populate existing records
        try:
            from text_processor import extract_letter_sequence
            cursor = self.connection.cursor()
            cursor.execute("SELECT number, content FROM recordings WHERE letter_sequence IS NULL")
            rows = cursor.fetchall()

            count = 0
            for row in rows:
                seq = extract_letter_sequence(row['content'])
                cursor.execute(
                    "UPDATE recordings SET letter_sequence = ? WHERE number = ?",
                    (seq, row['number'])
                )
                count += 1

            self.connection.commit()
            if count > 0:
                print(f"[Migration] Populated letter_sequence for {count} records")

        except Exception as e:
            print(f"[Migration] Error populating letter_sequence: {e}")

    def get_recording_by_letter_sequence(self, letter_seq):
        """
        Query recording by exact letter sequence match.

        Args:
            letter_seq (str): The letter sequence to search for.

        Returns:
            sqlite3.Row or None
        """
        def operation():
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT * FROM recordings WHERE letter_sequence = ?",
                (letter_seq,)
            )
            return cursor.fetchone()
        return self._execute_with_retry(operation)

    # ==================== Quiz: review_questions 表 ====================
    def migrate_create_review_questions(self):
        """创建 review_questions 表"""
        if not self.connection:
            self.connect()
        create_sql = """
        CREATE TABLE IF NOT EXISTS review_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            save_time TEXT NOT NULL,
            content TEXT NOT NULL,
            sentence_content TEXT,
            ai_status TEXT DEFAULT NULL,
            ai_question TEXT,
            user_answer TEXT,
            is_correct INTEGER,
            ai_feedback TEXT,
            answered_time TEXT
        );
        """
        try:
            with self.connection:
                self.connection.execute(create_sql)
            self._migrate_add_question_columns()
            print("[Migration] review_questions table ready")
        except sqlite3.Error as e:
            print(f"[Migration] Error creating review_questions: {e}")

    def _migrate_add_question_columns(self):
        migrations = [
            ("ai_status", "TEXT DEFAULT NULL"),
        ]
        for field_name, field_type in migrations:
            try:
                self.connection.execute(
                    f"ALTER TABLE review_questions ADD COLUMN {field_name} {field_type}"
                )
                print(f"[Migration] Added review_questions column: {field_name}")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    pass
                else:
                    raise

    def insert_question(self, save_time, content, sentence_content, ai_question=None, ai_status=None):
        """插入一条出题记录"""
        def operation():
            cursor = self.connection.cursor()
            cursor.execute(
                "INSERT INTO review_questions (save_time, content, sentence_content, ai_status, ai_question) VALUES (?, ?, ?, ?, ?)",
                (save_time, content, sentence_content, ai_status, ai_question)
            )
            self.connection.commit()
            return cursor.lastrowid
        return self._execute_with_retry(operation)

    def get_pending_questions(self):
        """获取未答题的记录"""
        def operation():
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT * FROM review_questions WHERE is_correct IS NULL ORDER BY id ASC"
            )
            return cursor.fetchall()
        return self._execute_with_retry(operation)

    def get_question(self, question_id):
        def operation():
            cursor = self.connection.cursor()
            cursor.execute("SELECT * FROM review_questions WHERE id = ?", (question_id,))
            return cursor.fetchone()
        return self._execute_with_retry(operation)

    def update_question_status(self, question_id, ai_status):
        def operation():
            cursor = self.connection.cursor()
            cursor.execute(
                "UPDATE review_questions SET ai_status = ? WHERE id = ?",
                (ai_status, question_id)
            )
            self.connection.commit()
        return self._execute_with_retry(operation)

    def update_question_ai_result(self, question_id, ai_question, ai_status):
        def operation():
            cursor = self.connection.cursor()
            cursor.execute(
                "UPDATE review_questions SET ai_question = ?, ai_status = ? WHERE id = ?",
                (ai_question, ai_status, question_id)
            )
            self.connection.commit()
        return self._execute_with_retry(operation)

    def update_answer(self, question_id, user_answer, is_correct, ai_feedback, answered_time):
        """更新用户答案和批改结果"""
        def operation():
            cursor = self.connection.cursor()
            cursor.execute(
                "UPDATE review_questions SET user_answer = ?, is_correct = ?, ai_feedback = ?, answered_time = ? WHERE id = ?",
                (user_answer, is_correct, ai_feedback, answered_time, question_id)
            )
            self.connection.commit()
        return self._execute_with_retry(operation)