import threading
import time
import math
import sys
from pynput import mouse
from clipboard_manager import capture_selection
from text_processor import process_text
from audio_recorder import AudioRecorder

class MainApp:
    def __init__(self):
        self.last_click_time = 0
        self.mouse_down_pos = None
        self.mouse_down_time = 0
        self.last_recorded_text = None
        
        self.current_recorder = None
        self.processing_thread = None
        self.stop_processing_flag = False
        
        print("[App] Initialized. Listening for events...")

    def stop_current_tasks(self):
        """
        Stops any running recording or processing.
        """
        # Stop recorder if active
        if self.current_recorder and self.current_recorder.is_alive():
            print("[App] Stopping active recording...")
            self.current_recorder.stop()
            self.current_recorder.join(timeout=1.0) # Wait a bit
            self.current_recorder = None
            
        # Signal processing thread to stop (if we could)
        self.stop_processing_flag = True

    def on_click(self, x, y, button, pressed):
        if button != mouse.Button.left:
            return

        if pressed:
            self.mouse_down_pos = (x, y)
            self.mouse_down_time = time.time()
        else:
            # Mouse Up
            current_time = time.time()
            is_trigger = False
            trigger_type = ""

            # Check Drag
            if self.mouse_down_pos:
                dist = math.hypot(x - self.mouse_down_pos[0], y - self.mouse_down_pos[1])
                # Threshold for drag: 5 pixels?
                if dist > 5:
                    is_trigger = True
                    trigger_type = "Drag"
            
            # Check Double Click (if not drag)
            if not is_trigger:
                # Simple double click detection: 
                # If time since last click (release) is short
                if (current_time - self.last_click_time) < 0.5:
                    is_trigger = True
                    trigger_type = "Double Click"
            
            self.last_click_time = current_time
            
            if is_trigger:
                print(f"[Trigger] {trigger_type} detected.")
                self.handle_trigger()

    def handle_trigger(self):
        # Stop existing
        self.stop_current_tasks()
        
        # Start new processing in a thread
        self.stop_processing_flag = False
        self.processing_thread = threading.Thread(target=self.run_process_flow)
        self.processing_thread.start()

    def run_process_flow(self):
        # 1. Clipboard Capture
        # This takes ~0.6s. 
        # Check flag occasionally?
        if self.stop_processing_flag: return
        
        try:
            # capture_selection handles backup -> Ctrl+C -> get -> restore
            new_content = capture_selection()
        except Exception as e:
            print(f"[App] Clipboard error: {e}")
            return
            
        if self.stop_processing_flag: return

        # 2. Validation & Cleaning
        is_valid, chosen_words = process_text(new_content, self.last_recorded_text)
        
        if not is_valid:
            # If invalid, we just stop.
            return
            
        self.last_recorded_text = chosen_words
        
        if self.stop_processing_flag: return

        # 3. Audio Recording
        # Create recorder
        self.current_recorder = AudioRecorder(chosen_words)
        self.current_recorder.start()

    def run(self):
        with mouse.Listener(on_click=self.on_click) as listener:
            listener.join()

if __name__ == "__main__":
    app = MainApp()
    try:
        app.run()
    except KeyboardInterrupt:
        print("[App] Exiting...")
