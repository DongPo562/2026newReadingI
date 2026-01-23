import sqlite3
import os
import time
import logging
from config_loader import app_config

class DatabaseManager:
    def __init__(self):
        self.db_path = app_config.db_path
        self.wal_mode = app_config.db_wal_mode
        self.busy_timeout = app_config.db_busy_timeout
        self.retry_count = app_config.db_retry_count
        self.connection = None

    def connect(self):
        """Establish a database connection with configured settings."""
        try:
            # check_same_thread=False allows using the connection across multiple threads
            # This is useful for the UI process which has background threads
            self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
            
            # Set busy timeout to avoid 'database is locked' errors
            self.connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout}")
            
            # Enable WAL mode if configured
            if self.wal_mode:
                self.connection.execute("PRAGMA journal_mode=WAL")
            
            # Return rows as dictionary-like objects
            self.connection.row_factory = sqlite3.Row
            
        except sqlite3.Error as e:
            print(f"Database connection error: {e}")
            raise

    def get_connection(self):
        """Get the underlying sqlite3 connection object."""
        if not self.connection:
            self.connect()
        return self.connection

    def close(self):
        """Close the database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None

    def init_db(self):
        """Initialize the database schema."""
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
        except sqlite3.Error as e:
            print(f"Database initialization error: {e}")
            raise

    def _execute_with_retry(self, operation_func):
        """Execute a database operation with retries."""
        if not self.connection:
            self.connect()

        for attempt in range(self.retry_count):
            try:
                return operation_func()
            except sqlite3.OperationalError as e:
                if "locked" in str(e) and attempt < self.retry_count - 1:
                    time.sleep(0.1 * (attempt + 1))  # Exponential backoff
                    continue
                else:
                    raise
            except Exception as e:
                raise

    def insert_recording(self, content, date_str):
        """Insert a new recording and return the generated number."""
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
        """Delete a recording by its number."""
        def operation():
            cursor = self.connection.cursor()
            cursor.execute("DELETE FROM recordings WHERE number = ?", (number,))
            self.connection.commit()
            
        return self._execute_with_retry(operation)

    def get_recordings_by_date(self, date_str):
        """Get all recordings for a specific date, ordered by number DESC."""
        def operation():
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT number, content, date FROM recordings WHERE date = ? ORDER BY number DESC",
                (date_str,)
            )
            return cursor.fetchall()
            
        return self._execute_with_retry(operation)

    def get_all_dates(self, limit=15):
        """Get distinct dates from recordings, ordered by date DESC."""
        def operation():
            cursor = self.connection.cursor()
            cursor.execute(
                f"SELECT DISTINCT date FROM recordings ORDER BY date DESC LIMIT {limit}"
            )
            return [row['date'] for row in cursor.fetchall()]
            
        return self._execute_with_retry(operation)

    def get_content(self, number):
        """Get the content text for a specific recording."""
        def operation():
            cursor = self.connection.cursor()
            cursor.execute("SELECT content FROM recordings WHERE number = ?", (number,))
            row = cursor.fetchone()
            return row['content'] if row else None
            
        return self._execute_with_retry(operation)

    def get_dates_exceeding_limit(self, limit=15):
        """Get list of dates that should be cleaned up (older than the newest limit dates)."""
        def operation():
            cursor = self.connection.cursor()
            # Get all dates ordered by date DESC
            cursor.execute("SELECT DISTINCT date FROM recordings ORDER BY date DESC")
            all_dates = [row['date'] for row in cursor.fetchall()]
            
            if len(all_dates) > limit:
                # Return dates that are outside the kept range
                # We keep the first 'limit' dates (newest), so we return the rest
                return sorted(all_dates[limit:]) # Return older dates sorted asc
            return []
            
        return self._execute_with_retry(operation)

    def get_recordings_by_date_list(self, date_list):
        """Get all recordings for a list of dates."""
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
        """Get all recording numbers and dates for consistency check."""
        def operation():
            cursor = self.connection.cursor()
            cursor.execute("SELECT number, date FROM recordings")
            return cursor.fetchall()
            
        return self._execute_with_retry(operation)

    def get_recording_by_number(self, number):
        """Get a single recording by number."""
        def operation():
            cursor = self.connection.cursor()
            cursor.execute("SELECT * FROM recordings WHERE number = ?", (number,))
            return cursor.fetchone()
            
        return self._execute_with_retry(operation)
