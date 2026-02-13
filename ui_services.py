"""
ui_services.py - UI服务线程
包含: CommandServer, ConsistencyChecker, FileCleaner
"""
import os
import time
import socket
import shutil
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtMultimedia import QMediaPlayer
from config_loader import app_config

class CommandServer(QThread):
    file_saved_signal = pyqtSignal(str)
    stop_playback_signal = pyqtSignal()
    play_request_signal = pyqtSignal(int, int)  # number, count
    silent_record_signal = pyqtSignal()  # 静默录音模式信号

    def run(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(('127.0.0.1', 65432))
            server.listen(5)
            while True:
                try:
                    conn, addr = server.accept()
                    with conn:
                        data = conn.recv(1024)
                        if data:
                            message = data.decode('utf-8')
                            if message == "STOP_PLAYBACK":
                                self.stop_playback_signal.emit()
                            elif message.startswith("PLAY:"):
                                try:
                                    parts = message.split(":")
                                    number = int(parts[1])
                                    count = int(parts[2]) if len(parts) > 2 else 1
                                    self.play_request_signal.emit(number, count)
                                except ValueError:
                                    print(f"Invalid PLAY command: {message}")
                            elif message == "SILENT_RECORD_START":
                                # 静默录音模式：自动补录触发，通知 ListPanel 进入静默模式
                                print("[CommandServer] Received SILENT_RECORD_START")
                                self.silent_record_signal.emit()
                            else:
                                self.file_saved_signal.emit(message)
                except Exception as e:
                    print(f"Socket Accept Error: {e}")
        except Exception as e:
            print(f"Socket Bind Error: {e}")

class ConsistencyChecker(QThread):
    finished = pyqtSignal()

    def __init__(self, db_manager):
        super().__init__()
        self.db_manager = db_manager

    def run(self):
        print("Consistency check started")
        try:
            records = self.db_manager.get_all_recordings_for_consistency_check()
            db_numbers = {r['number'] for r in records}
            audio_dir = app_config.save_dir
            if not os.path.exists(audio_dir):
                os.makedirs(audio_dir)
            files = os.listdir(audio_dir)
            file_numbers = set()
            file_map = {}
            for f in files:
                if not f.endswith('.wav'): continue
                if '@' in f: continue
                try:
                    name_part = os.path.splitext(f)[0]
                    if name_part.isdigit():
                        num = int(name_part)
                        file_numbers.add(num)
                        file_map[num] = f
                except ValueError:
                    pass
            orphans_db = db_numbers - file_numbers
            removed_records = 0
            for num in orphans_db:
                print(f"Consistency check: removing orphan record number={num}")
                try:
                    self.db_manager.delete_recording(num)
                    removed_records += 1
                except Exception as e:
                    print(f"Consistency check warning: failed to remove record {num}, reason: {e}")
            orphans_file = file_numbers - db_numbers
            removed_files = 0
            for num in orphans_file:
                fname = file_map[num]
                print(f"Consistency check: removing orphan file {fname}")
                try:
                    self._delete_file_set(os.path.join(audio_dir, fname))
                    removed_files += 1
                except Exception as e:
                    print(f"Consistency check warning: failed to remove file {fname}, reason: {e}")
            print(f"Consistency check completed, removed {removed_records} records and {removed_files} files")
            try:
                project_root = os.path.dirname(os.path.abspath(__file__))
                text_dir = os.path.join(project_root, 'text')
                if os.path.exists(text_dir):
                    print(f"Consistency check: Removing legacy text folder: {text_dir}")
                    shutil.rmtree(text_dir, ignore_errors=True)
            except Exception as e:
                print(f"Consistency check warning: failed to remove text folder: {e}")
        except Exception as e:
            print(f"Consistency check failed: {e}")
        self.finished.emit()

    def _delete_file_set(self, file_path):
        dirname = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        name_without_ext = os.path.splitext(filename)[0]
        files_to_delete = [file_path]
        for speed in ['0.5', '0.75']:
            variant_name = f"{name_without_ext}@{speed}.wav"
            files_to_delete.append(os.path.join(dirname, variant_name))
        for fpath in files_to_delete:
            if os.path.exists(fpath):
                os.remove(fpath)

class FileCleaner(QThread):
    def __init__(self, db_manager, list_panel):
        super().__init__()
        self.db_manager = db_manager
        self.list_panel = list_panel
        self.running = True

    def run(self):
        delay = app_config.cleanup_delay_seconds
        print(f"[Cleanup] Scheduled in {delay} seconds")
        for _ in range(delay):
            if not self.running: return
            time.sleep(1)
        while self.running:
            is_playing = self.list_panel.player.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            if not is_playing:
                self.perform_cleanup()
                break
            else:
                print("[Cleanup] Waiting for idle state...")
                time.sleep(5)

    def perform_cleanup(self):
        try:
            limit = app_config.max_display_dates
            dates_to_remove = self.db_manager.get_dates_exceeding_limit(limit)
            if dates_to_remove:
                print(f"[Cleanup] Cleanup started, found {len(dates_to_remove)} dates exceeding limit of {limit}")
                recordings_to_remove = self.db_manager.get_recordings_by_date_list(dates_to_remove)
                removed_count = 0
                for rec in recordings_to_remove:
                    number = rec['number']
                    date_str = rec['date']
                    try:
                        self._delete_files_for_number(number)
                        self.db_manager.delete_recording(number)
                        print(f"Cleanup: removed record number={number} for date {date_str}")
                        removed_count += 1
                    except Exception as e:
                        print(f"Cleanup warning: failed to delete record {number}, reason: {e}")
                print(f"Cleanup completed, removed {removed_count} records")
        except Exception as e:
            print(f"[Cleanup] Error: {e}")

    def _delete_files_for_number(self, number):
        audio_dir = app_config.save_dir
        filename = f"{number}.wav"
        file_path = os.path.join(audio_dir, filename)
        files_to_delete = [file_path]
        for speed in ['0.5', '0.75']:
            variant_name = f"{number}@{speed}.wav"
            files_to_delete.append(os.path.join(audio_dir, variant_name))
        for fpath in files_to_delete:
            if os.path.exists(fpath):
                try:
                    os.remove(fpath)
                except Exception as e:
                    print(f"Cleanup warning: failed to delete file {os.path.basename(fpath)}, reason: {e}")