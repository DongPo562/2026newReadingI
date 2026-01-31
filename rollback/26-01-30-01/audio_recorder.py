import os
import threading
import time
import numpy as np
import soundcard as sc
import soundfile as sf
import re
import socket
from datetime import datetime
from config_loader import app_config
from db_manager import DatabaseManager
from audio_processor import generate_slow_audio
from text_processor import is_valid_word


class AudioRecorder(threading.Thread):
    def __init__(self, content):
        super().__init__()
        self.content = content
        self.running = True
        self.audio_data = []
        self.samplerate = 48000
        self.channels = 2
        self.blocksize = 4800
        self.start_time = None
        self.has_sound_started = False
        self.silence_start_time = None
        self.start_silence_duration = app_config.start_silence_duration
        self.max_duration = app_config.max_recording_duration
        self.silence_threshold_db = app_config.silence_threshold_db
        self.end_silence_duration = app_config.end_silence_duration
        self.save_dir = app_config.save_dir
        self.db_manager = DatabaseManager()

    def get_loopback_mic(self):
        try:
            default_speaker = sc.default_speaker()
            print(f"[Recorder] Default Speaker: {default_speaker.name}")
            all_mics = sc.all_microphones(include_loopback=True)
            physical_mics_ids = [m.id for m in sc.all_microphones(include_loopback=False)]
            loopback_candidates = [m for m in all_mics if m.id not in physical_mics_ids]
            for mic in loopback_candidates:
                if mic.name == default_speaker.name:
                    return mic
            fallback = sc.get_microphone(id=str(default_speaker.name), include_loopback=True)
            if fallback.id in [m.id for m in loopback_candidates]:
                return fallback
            print("[Recorder] Warning: Could not confirm loopback device identity. Using fallback.")
            return fallback
        except Exception as e:
            print(f"[Recorder] Error finding loopback: {e}")
            return None

    def run(self):
        print("[Recorder] Starting recording process...")
        try:
            mic = self.get_loopback_mic()
            if not mic:
                print("[Recorder] Error: Could not find loopback device.")
                return
            print(f"[Recorder] Recording from Loopback: {mic.name}")
            with mic.recorder(samplerate=self.samplerate) as recorder:
                self.start_time = time.time()
                while self.running:
                    data = recorder.record(numframes=self.blocksize)
                    rms = np.sqrt(np.mean(data**2))
                    db = 20 * np.log10(rms + 1e-9)
                    current_time = time.time()
                    elapsed = current_time - self.start_time
                    if not self.has_sound_started:
                        if db > self.silence_threshold_db:
                            self.has_sound_started = True
                            print("[Recorder] Sound detected! Recording...")
                            self.audio_data.append(data)
                            self.silence_start_time = None
                        else:
                            if elapsed > self.start_silence_duration:
                                print("[Recorder] Timeout: No sound detected.")
                                return
                            pass
                    else:
                        self.audio_data.append(data)
                        recorded_duration = (len(self.audio_data) * self.blocksize) / self.samplerate
                        if recorded_duration > self.max_duration:
                            print("[Recorder] Max duration reached.")
                            break
                        if db < self.silence_threshold_db:
                            if self.silence_start_time is None:
                                self.silence_start_time = current_time

                            elif (current_time - self.silence_start_time) >= self.end_silence_duration:
                                print("[Recorder] End silence detected.")
                                break
                        else:
                            self.silence_start_time = None
        except Exception as e:
            print(f"[Recorder] Error: {e}")
            return
        if self.audio_data:
            self.save_file()
        else:
            print("[Recorder] No audio data captured.")

    def stop(self):
        self.running = False

    def save_file(self):
        full_data = np.concatenate(self.audio_data, axis=0)
        thresh_linear = 10**(self.silence_threshold_db / 20)
        mono = np.mean(np.abs(full_data), axis=1)
        mask = mono > thresh_linear
        if not np.any(mask):
            print("[Recorder] Warning: Audio seems silent after capture.")
            return
        indices = np.where(mask)[0]
        start_idx = indices[0]
        end_idx = indices[-1]
        trimmed = full_data[start_idx:end_idx+1]
        max_val = np.max(np.abs(trimmed))
        if max_val > 0.01:
            target_peak = 0.9
            gain = target_peak / max_val
            trimmed = trimmed * gain
            print(f"[Recorder] Normalized audio (Gain: {gain:.2f}x)")
        pad_samples = int(0.3 * self.samplerate)
        silence_pad = np.zeros((pad_samples, self.channels), dtype=np.float32)
        final_data = np.concatenate([silence_pad, trimmed, silence_pad], axis=0)
        try:
            self._save_transaction_with_retry(final_data)
        except Exception as e:
            print(f"[Recorder] Final save failed: {e}")

    def _save_transaction_with_retry(self, final_data):
        for attempt in range(app_config.db_retry_count):
            try:
                self._execute_save_transaction(final_data)
                return
            except Exception as e:
                if "locked" in str(e).lower() and attempt < app_config.db_retry_count - 1:
                    print(f"[Recorder] Transaction locked, retrying ({attempt+1})...")
                    time.sleep(0.5)
                    continue
                raise e

    def _execute_save_transaction(self, final_data):
        conn = self.db_manager.get_connection()
        generated_files = []
        number = None  # 用于存储录音记录的 number
        try:
            cursor = conn.cursor()
            date_str = datetime.now().strftime("%Y-%m-%d")

            # ==================== 内容去重检测 ====================
            existing_record = self.db_manager.get_recording_by_content(self.content)
            
            if existing_record:
                # 内容已存在，执行覆盖逻辑
                number = existing_record['number']
                print(f"[Recorder] 检测到重复内容，覆盖旧录音 #{number}")
                
                # 删除旧的音频文件（1x 和变速版本）
                self._delete_old_audio_files(number)
                
                # 更新 date 字段为当天
                cursor.execute(
                    "UPDATE recordings SET date = ? WHERE number = ?",
                    (date_str, number)
                )
                print(f"[Recorder] 已更新录音 #{number} 的日期为 {date_str}")
                
            else:
                # 内容不存在，插入新记录
                cursor.execute(
                    "INSERT INTO recordings (content, date) VALUES (?, ?)",
                    (self.content, date_str)
                )
                number = cursor.lastrowid
                print(f"[Recorder] 创建新录音记录 #{number}")
                
                # 新记录：初始化单词复习字段
                if is_valid_word(self.content):
                    self._initialize_word_review_fields(cursor, number, date_str)
            # ==================== 内容去重检测结束 ====================

            if not os.path.exists(self.save_dir):
                os.makedirs(self.save_dir)

            filename_1x = f"{number}.wav"
            filepath_1x = os.path.join(self.save_dir, filename_1x)
            sf.write(filepath_1x, final_data, self.samplerate)
            generated_files.append(filepath_1x)

            if app_config.slow_generate_versions:
                slow_files = generate_slow_audio(filepath_1x, app_config.slow_speeds)
                generated_files.extend(slow_files)

            conn.commit()
            print(f"[Recorder] Successfully saved recording #{number}")
            
            # 通知 UI 并传递 number
            self.notify_ui(number)

        except Exception as e:
            conn.rollback()
            print(f"Recording save failed: {e}, transaction rolled back")
            for f in generated_files:
                try:
                    if os.path.exists(f):
                        os.remove(f)
                        print(f"Rollback cleanup: deleted {f}")
                except Exception as cleanup_error:
                    print(f"Rollback cleanup warning: failed to delete {f}, reason: {cleanup_error}")
            raise e

    def _delete_old_audio_files(self, number):
        """
        删除指定 number 的旧音频文件（1x 和所有变速版本）
        
        Args:
            number: 录音记录的 number
        """
        # 1x 版本
        filepath_1x = os.path.join(self.save_dir, f"{number}.wav")
        if os.path.exists(filepath_1x):
            try:
                os.remove(filepath_1x)
                print(f"[Recorder] 删除旧文件: {filepath_1x}")
            except Exception as e:
                print(f"[Recorder] Warning: 删除旧文件失败 {filepath_1x}: {e}")
        
        # 变速版本
        if app_config.slow_generate_versions:
            for speed in app_config.slow_speeds:
                slow_filepath = os.path.join(self.save_dir, f"{number}@{speed}.wav")
                if os.path.exists(slow_filepath):
                    try:
                        os.remove(slow_filepath)
                        print(f"[Recorder] 删除旧文件: {slow_filepath}")
                    except Exception as e:
                        print(f"[Recorder] Warning: 删除旧文件失败 {slow_filepath}: {e}")

    def _initialize_word_review_fields(self, cursor, number, date_str):
        """
        初始化单词的复习相关字段

        Args:
            cursor: 数据库游标
            number: 录音记录的 number
            date_str: 当前日期字符串 (YYYY-MM-DD)
        """
        try:
            cursor.execute("""
                UPDATE recordings 
                SET box_level = 1,
                    next_review_date = ?,
                    remember = 0,
                    forget = 0,
                    last_review_date = NULL
                WHERE number = ?
            """, (date_str, number))
            print(f"[Recorder] 单词 '{self.content}' 已初始化复习字段 (box_level=1, next_review_date={date_str})")
        except Exception as e:
            # 初始化失败不影响录音保存，仅打印警告
            print(f"[Recorder] Warning: 初始化单词复习字段失败: {e}")

    def notify_ui(self, number=None):
        """
        通知 UI 刷新列表并自动播放指定录音
        
        Args:
            number: 录音记录的 number，用于指定自动播放的录音
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.0)
                s.connect(('127.0.0.1', 65432))
                # 发送 UPDATE:{number} 格式的消息，让 UI 知道应该播放哪条录音
                if number is not None:
                    message = f"UPDATE:{number}"
                else:
                    message = "UPDATE"
                s.sendall(message.encode('utf-8'))
                print(f"[Recorder] Notified UI with message: {message}")
        except Exception as e:
            pass