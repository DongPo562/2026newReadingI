import threading
import time
import math
import sys
import socket
import os
from pynput import mouse
from clipboard_manager import capture_selection
from text_processor import process_text
from audio_recorder import AudioRecorder

class ExitServer(threading.Thread):
    def __init__(self, app_instance):
        super().__init__()
        self.app = app_instance
        self.daemon = True

    def run(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(('127.0.0.1', 65433))
            server.listen(1)
            # print("[ExitServer] Listening on 65433...")
            while True:
                conn, addr = server.accept()
                with conn:
                    data = conn.recv(1024)
                    if data.decode().strip() == "EXIT":
                        print("[ExitServer] Exit signal received.")
                        self.app.shutdown()
                        break
        except Exception as e:
            print(f"[ExitServer] Error: {e}")

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
            self.current_recorder.join(timeout=1.0)  # Wait a bit
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
        if self.stop_processing_flag:
            return

        try:
            # capture_selection handles backup -> Ctrl+C -> get -> restore
            new_content = capture_selection()
        except Exception as e:
            print(f"[App] Clipboard error: {e}")
            return

        if self.stop_processing_flag:
            return

        # 2. Validation & Cleaning
        is_valid, chosen_words = process_text(new_content, self.last_recorded_text)

        if not is_valid:
            # If invalid, we just stop.
            return

        self.last_recorded_text = chosen_words

        if self.stop_processing_flag:
            return

        # Stop Playback before recording
        print("[App] Recording triggered - stopping current playback")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                s.connect(('127.0.0.1', 65432))
                s.sendall(b"STOP_PLAYBACK")
        except Exception as e:
            print(f"[App] Warning: Could not stop playback (UI might be closed): {e}")

        # 3. Audio Recording
        # Create recorder
        self.current_recorder = AudioRecorder(new_content)
        self.current_recorder.start()

    def shutdown(self):
        print("[App] Shutting down...")
        self.stop_current_tasks()
        if hasattr(self, 'listener') and self.listener:
            self.listener.stop()
        os._exit(0)

    def run(self):
        # Start Exit Server
        self.exit_server = ExitServer(self)
        self.exit_server.start()

        self.listener = mouse.Listener(on_click=self.on_click)
        self.listener.start()
        self.listener.join()

if __name__ == "__main__":
    app = MainApp()
    try:
        app.run()
    except KeyboardInterrupt:
        print("[App] Exiting...")