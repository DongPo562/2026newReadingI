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
from config_loader import app_config as config


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
        self.mouse_down_pos = None
        self.mouse_down_time = 0
        self.last_recorded_text = None
        self.current_recorder = None
        self.processing_thread = None
        self.stop_processing_flag = False

        # ====== 点击判定相关 ======
        self.click_count = 0
        self.last_click_time = 0
        self.pending_trigger_timer = None
        self.trigger_lock = threading.Lock()

        # 从配置读取参数
        self.double_click_threshold = config.click_double_click_threshold
        self.multi_click_wait = config.click_multi_click_wait
        self.drag_distance_threshold = config.click_drag_distance_threshold

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

            # 检查三击标志位（如果是由程序模拟的三击，忽略之）
            if alt_trigger.triple_click_in_progress:
                self.last_click_time = current_time
                return

            # Check Drag - 拖拽立即触发，不进入延迟判定
            if self.mouse_down_pos:
                dist = math.hypot(x - self.mouse_down_pos[0], y - self.mouse_down_pos[1])
                if dist > self.drag_distance_threshold:
                    self._cancel_pending_trigger()
                    print("[Trigger] Drag detected.")
                    self.handle_trigger("drag")
                    return

            # 处理点击计数
            with self.trigger_lock:
                # 判断是否为连续点击
                if (current_time - self.last_click_time) < self.double_click_threshold:
                    self.click_count += 1
                else:
                    self.click_count = 1

                self.last_click_time = current_time

                # 如果达到双击条件，安排延迟触发
                if self.click_count >= 2:
                    self._schedule_trigger()

    def _schedule_trigger(self):
        """安排延迟触发，等待可能的更多点击"""
        # 取消已有的定时器
        if self.pending_trigger_timer and self.pending_trigger_timer.is_alive():
            self.pending_trigger_timer.cancel()

        # 启动新定时器
        self.pending_trigger_timer = threading.Timer(
            self.multi_click_wait,
            self._execute_trigger
        )
        self.pending_trigger_timer.daemon = True
        self.pending_trigger_timer.start()

    def _cancel_pending_trigger(self):
        """取消待处理的触发"""
        with self.trigger_lock:
            if self.pending_trigger_timer and self.pending_trigger_timer.is_alive():
                self.pending_trigger_timer.cancel()
                self.pending_trigger_timer = None
            self.click_count = 0

    def _execute_trigger(self):
        """执行触发（定时器回调）"""
        with self.trigger_lock:
            click_count = self.click_count
            self.click_count = 0
            self.pending_trigger_timer = None

        if click_count >= 3:
            # 三击及以上：仅识别，不触发任何操作
            print(f"[Trigger] triple_click detected ({click_count} clicks) - ignored.")
        elif click_count == 2:
            # 双击：触发录音流程
            print("[Trigger] double_click detected.")
            self.handle_trigger("double_click")

    def handle_trigger(self, trigger_type="unknown"):
        """处理触发（双击/三击/拖拽）：直接录音"""
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
        self._cancel_pending_trigger()
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