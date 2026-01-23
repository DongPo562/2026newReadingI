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

class AudioRecorder(threading.Thread):
    def __init__(self, content):
        super().__init__()
        self.content = content
        self.running = True
        self.audio_data = []
        self.samplerate = 48000 # Default for WASAPI shared mode
        self.channels = 2  # Loopback usually stereo
        self.blocksize = 4800 # 0.1s chunks at 48k
        
        # State
        self.start_time = None
        self.has_sound_started = False
        self.silence_start_time = None
        
        # Config
        self.start_silence_duration = app_config.start_silence_duration
        self.max_duration = app_config.max_recording_duration
        self.silence_threshold_db = app_config.silence_threshold_db
        self.end_silence_duration = app_config.end_silence_duration
        self.save_dir = app_config.save_dir
        
        self.db_manager = DatabaseManager()

    def get_loopback_mic(self):
        """
        Robustly finds the loopback device corresponding to the default speaker.
        """
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
        
        # Setup Loopback
        try:
            mic = self.get_loopback_mic()
            
            if not mic:
                print("[Recorder] Error: Could not find loopback device.")
                return

            print(f"[Recorder] Recording from Loopback: {mic.name}")

            with mic.recorder(samplerate=self.samplerate) as recorder:
                self.start_time = time.time()
                
                while self.running:
                    # Read chunk
                    data = recorder.record(numframes=self.blocksize)
                    
                    # Calculate dB
                    rms = np.sqrt(np.mean(data**2))
                    db = 20 * np.log10(rms + 1e-9)
                    
                    # Logic
                    current_time = time.time()
                    elapsed = current_time - self.start_time
                    
                    # Phase 1: Waiting for sound
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
                            
                    # Phase 2: Recording
                    else:
                        self.audio_data.append(data)
                        
                        recorded_duration = (len(self.audio_data) * self.blocksize) / self.samplerate
                        if recorded_duration > self.max_duration:
                            print("[Recorder] Max duration reached.")
                            break
                            
                        # End silence check
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

        # 3. Post-processing and Save
        if self.audio_data:
            self.save_file()
        else:
            print("[Recorder] No audio data captured.")

    def stop(self):
        self.running = False

    def save_file(self):
        full_data = np.concatenate(self.audio_data, axis=0)
        
        # Determine non-silent indices
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
        
        # Normalization / Gain Compensation
        max_val = np.max(np.abs(trimmed))
        if max_val > 0.01:
            target_peak = 0.9
            gain = target_peak / max_val
            trimmed = trimmed * gain
            print(f"[Recorder] Normalized audio (Gain: {gain:.2f}x)")

        # Add padding (0.3s)
        pad_samples = int(0.3 * self.samplerate)
        silence_pad = np.zeros((pad_samples, self.channels), dtype=np.float32)
        
        final_data = np.concatenate([silence_pad, trimmed, silence_pad], axis=0)
        
        # Save Transaction
        try:
            self._save_transaction_with_retry(final_data)
        except Exception as e:
            print(f"[Recorder] Final save failed: {e}")

    def _save_transaction_with_retry(self, final_data):
        # We handle retry manually here because we want to retry the whole transaction
        # including file operations if DB locks (though files shouldn't lock, DB might).
        # Actually, standard DB retry logic usually applies to the DB commit/execute.
        # But here we have a mixed transaction (DB + File).
        
        # If DB is locked, we can retry.
        # If File fails, we shouldn't retry (likely permission or disk issue).
        
        # For simplicity and robustness, we can just try once, or retry only on DB specific errors.
        # But since we want "Atomic", let's try to follow the structure.
        
        for attempt in range(app_config.db_retry_count):
            try:
                self._execute_save_transaction(final_data)
                return
            except Exception as e:
                # If it's a DB locking error, we might want to retry
                # But if files were created, they are deleted in rollback.
                # So it's safe to retry from scratch.
                if "locked" in str(e).lower() and attempt < app_config.db_retry_count - 1:
                     print(f"[Recorder] Transaction locked, retrying ({attempt+1})...")
                     time.sleep(0.5)
                     continue
                raise e

    def _execute_save_transaction(self, final_data):
        conn = self.db_manager.get_connection()
        generated_files = []
        
        try:
            cursor = conn.cursor()
            
            # 1. Start Transaction (Implicit or explicit)
            # We use implicit transaction by executing INSERT
            
            # 2. Insert DB
            date_str = datetime.now().strftime("%Y-%m-%d")
            cursor.execute(
                "INSERT INTO recordings (content, date) VALUES (?, ?)",
                (self.content, date_str)
            )
            number = cursor.lastrowid
            
            # 3. Save 1x File
            if not os.path.exists(self.save_dir):
                os.makedirs(self.save_dir)
                
            filename_1x = f"{number}.wav"
            filepath_1x = os.path.join(self.save_dir, filename_1x)
            
            # Save using soundfile
            sf.write(filepath_1x, final_data, self.samplerate)
            generated_files.append(filepath_1x)
            
            # 4. Save Slow Versions
            if app_config.slow_generate_versions:
                # generate_slow_audio returns list of created files
                slow_files = generate_slow_audio(filepath_1x, app_config.slow_speeds)
                generated_files.extend(slow_files)
            
            # 5. Commit
            conn.commit()
            print(f"[Recorder] Successfully saved recording #{number}")
            
            # 6. Notify UI
            self.notify_ui()
            
        except Exception as e:
            # Rollback DB
            conn.rollback()
            print(f"Recording save failed: {e}, transaction rolled back")
            
            # Delete files
            for f in generated_files:
                try:
                    if os.path.exists(f):
                        os.remove(f)
                        print(f"Rollback cleanup: deleted {f}")
                except Exception as cleanup_error:
                     print(f"Rollback cleanup warning: failed to delete {f}, reason: {cleanup_error}")
            raise e

    def notify_ui(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.0)
                s.connect(('127.0.0.1', 65432))
                # Send a signal. The content doesn't matter much as UI reloads from DB.
                # But previously it sent filepath. Now just "UPDATE" or empty?
                # Requirement: "Socket message only as trigger signal"
                s.sendall(b"UPDATE")
            print(f"[Recorder] Notified UI")
        except Exception as e:
            # print(f"[Recorder] UI Notification failed: {e}")
            pass
