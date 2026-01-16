import os
import threading
import time
import numpy as np
import soundcard as sc
import soundfile as sf
import re
from datetime import datetime
from config_loader import app_config

class AudioRecorder(threading.Thread):
    def __init__(self, chosen_words):
        super().__init__()
        self.chosen_words = chosen_words
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

    def get_loopback_mic(self):
        """
        Robustly finds the loopback device corresponding to the default speaker.
        """
        try:
            default_speaker = sc.default_speaker()
            print(f"[Recorder] Default Speaker: {default_speaker.name}")
            
            # 1. Get all 'microphones' including loopback
            all_mics = sc.all_microphones(include_loopback=True)
            
            # 2. Get physical microphones (to exclude them)
            # Note: soundcard doesn't make this easy, but usually physical mics 
            # don't share the EXACT name with the Speaker unless it's a headset.
            # But headset HFP mic vs Stereo loopback is the issue.
            
            # Strategy: Look for a device in all_mics that matches the speaker name exactly.
            # If there are duplicates (e.g. Headset case), we need to distinguish.
            # Usually the Loopback device comes *first* or *last*? No guarantee.
            # However, physical mics usually have distinct IDs.
            
            # Better Strategy: 
            # Iterate and find the one that is NOT a physical mic? 
            # How? `sc.all_microphones(include_loopback=False)` gives physical ones.
            
            physical_mics_ids = [m.id for m in sc.all_microphones(include_loopback=False)]
            
            loopback_candidates = [m for m in all_mics if m.id not in physical_mics_ids]
            
            # Now find the one matching the speaker
            for mic in loopback_candidates:
                if mic.name == default_speaker.name:
                    return mic
            
            # Fallback: if no exact name match (rare), try fuzzy?
            # Or just take the first loopback? No, that might be a different device.
            # Try finding one with "Loopback" in name? (Not standard on Windows)
            
            # If we are here, maybe the name doesn't match exactly.
            # Try `sc.get_microphone(id=str(default_speaker.name), include_loopback=True)`
            # but verifying it's in loopback_candidates.
            
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

            # Use native samplerate if possible, or 48000.
            # We use 48000 as it's standard for Windows WASAPI shared mode.
            with mic.recorder(samplerate=self.samplerate) as recorder:
                self.start_time = time.time()
                
                while self.running:
                    # Read chunk
                    data = recorder.record(numframes=self.blocksize)
                    # data is (numframes, channels) float32
                    
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
            pass
        else:
            indices = np.where(mask)[0]
            start_idx = indices[0]
            end_idx = indices[-1]
            
            trimmed = full_data[start_idx:end_idx+1]
            
            # Normalization / Gain Compensation
            # Fix for Issue 2: Low volume when recording from speakers
            max_val = np.max(np.abs(trimmed))
            if max_val > 0.01: # Avoid amplifying pure silence/noise
                target_peak = 0.9 # -1 dB roughly
                gain = target_peak / max_val
                # Only apply gain if it's significant amplification or reasonable attenuation
                # To be safe, let's just normalize to target_peak
                trimmed = trimmed * gain
                print(f"[Recorder] Normalized audio (Gain: {gain:.2f}x)")

            # Add padding (0.3s)
            pad_samples = int(0.3 * self.samplerate)
            silence_pad = np.zeros((pad_samples, self.channels), dtype=np.float32)
            
            final_data = np.concatenate([silence_pad, trimmed, silence_pad], axis=0)
            
            # Filename
            base_name = self.chosen_words[:30]
            base_name = re.sub(r'[\\/:*?"<>|]', '', base_name)
            base_name = base_name.strip()
            
            date_str = datetime.now().strftime("%Y-%m-%d")
            filename = f"{base_name}_{date_str}.wav"
            
            if not os.path.exists(self.save_dir):
                os.makedirs(self.save_dir)
                
            filepath = os.path.join(self.save_dir, filename)
            
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                    print(f"[Recorder] Deleted old file: {filepath}")
                except Exception as e:
                    print(f"[Recorder] Could not delete old file: {e}")
            
            sf.write(filepath, final_data, self.samplerate)
            print(f"[Recorder] Saved to: {filepath}")

            # Save Text File (Word Game)
            try:
                text_folder = app_config.game_text_folder
                if not os.path.exists(text_folder):
                    os.makedirs(text_folder)
                
                text_filename = f"{base_name}_{date_str}.txt"
                text_filepath = os.path.join(text_folder, text_filename)
                
                with open(text_filepath, 'w', encoding='utf-8') as f:
                    f.write(self.chosen_words)
                print(f"[Recorder] Saved text to: {text_filepath}")
            except Exception as e:
                print(f"[Recorder] Error saving text file: {e}")

            # Generate Slow Versions
            if app_config.slow_generate_versions:
                from audio_processor import generate_slow_audio
                threading.Thread(target=generate_slow_audio, args=(filepath, app_config.slow_speeds)).start()
