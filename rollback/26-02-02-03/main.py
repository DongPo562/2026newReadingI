import threading
import time
import math
import sys
import socket
import os
from pynput import mouse
from ui_automation import get_selected_text
from text_processor import process_text
from audio_recorder import AudioRecorder
import alt_trigger
import ctrl_trigger


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
        
        # 启动 Alt 键监听器
        self.alt_listener = alt_trigger.AltTriggerListener()
        self.alt_listener.start()
        # 启动 Ctrl 长按监听器
        self.ctrl_listener = ctrl_trigger.CtrlTriggerListener()
        self.ctrl_listener.start()

        print("[App] Initialized. Listening for events...")

    def stop_current_tasks(self):
        """Stops any running recording or processing."""
        if self.current_recorder and self.current_recorder.is_alive():
            print("[App] Stopping active recording...")
            self.current_recorder.stop()
            self.current_recorder.join(timeout=1.0)
            self.current_recorder = None

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

            # 检查三击标志位
            if alt_trigger.triple_click_in_progress:
                print("[Trigger] Ignored click (triple-click in progress)")
                self.last_click_time = current_time
                return

            # Check Drag
            if self.mouse_down_pos:
                dist = math.hypot(x - self.mouse_down_pos[0], y - self.mouse_down_pos[1])
                if dist > 5:
                    is_trigger = True
                    trigger_type = "Drag"

            # Check Double Click (if not drag)
            if not is_trigger:
                if (current_time - self.last_click_time) < 0.5:
                    is_trigger = True
                    trigger_type = "Double Click"

            self.last_click_time = current_time

            if is_trigger:
                print(f"[Trigger] {trigger_type} detected.")
                self.handle_trigger()

    def handle_trigger(self):
        self.stop_current_tasks()
        self.stop_processing_flag = False
        self.processing_thread = threading.Thread(target=self.run_process_flow)
        self.processing_thread.start()

    def run_process_flow(self):
        """处理流程：使用 UI Automation 获取选中文本"""
        if self.stop_processing_flag:
            return

        # ========== 1. 使用 UI Automation 获取选中文本 ==========
        try:
            # 短暂延迟，等待选中状态稳定
            time.sleep(0.05)
            new_content = get_selected_text()
        except Exception as e:
            print(f"[App] UI Automation error: {e}")
            return

        if self.stop_processing_flag:
            return

        # ========== 2. 文本校验 ==========
        is_valid, chosen_words = process_text(new_content, self.last_recorded_text)

        if not is_valid:
            return

        self.last_recorded_text = chosen_words

        if self.stop_processing_flag:
            return

        # ========== 3. 停止当前播放 ==========
        print("[App] Recording triggered - stopping current playback")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                s.connect(('127.0.0.1', 65432))
                s.sendall(b"STOP_PLAYBACK")
        except Exception as e:
            print(f"[App] Warning: Could not stop playback: {e}")

        # ========== 4. 开始录音 ==========
        self.current_recorder = AudioRecorder(new_content)
        self.current_recorder.start()

    def shutdown(self):
        print("[App] Shutting down...")
        self.stop_current_tasks()
        
        if hasattr(self, 'alt_listener') and self.alt_listener:
            self.alt_listener.stop()
        if hasattr(self, 'ctrl_listener') and self.ctrl_listener:
            self.ctrl_listener.stop()
        
        if hasattr(self, 'listener') and self.listener:
            self.listener.stop()
        os._exit(0)

    def run(self):
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