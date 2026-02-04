import threading
import time
import socket
import logging
import ctypes
from ctypes import wintypes
from pynput import keyboard
from pynput.mouse import Button, Controller as MouseController
from ui_automation import get_text_at_cursor
from text_processor import extract_letter_sequence
from db_manager import DatabaseManager
from config_loader import app_config
from auto_record_trigger import AutoRecordTrigger

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("AltTrigger")

# Mouse controller for triple-click
mouse_controller = MouseController()

# ==================== 全局标志位 ====================
# 用于通知 main.py 的双击检测器忽略三击产生的点击
triple_click_in_progress = False

def get_cursor_position():
    """获取当前鼠标位置"""
    pt = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return (pt.x, pt.y)

def triple_click(interval=0.05):
    """
    在当前鼠标位置执行三击
    Args:
        interval: 点击之间的间隔时间（秒）
    """
    global triple_click_in_progress
    # 设置标志位，通知 main.py 忽略这些点击
    triple_click_in_progress = True
    try:
        for i in range(3):
            mouse_controller.click(Button.left)
            if i < 2:  # 最后一次点击后不需要等待
                time.sleep(interval)
    finally:
        # 延迟重置标志位，确保 main.py 的检测器有时间看到
        def reset_flag():
            global triple_click_in_progress
            time.sleep(0.6)  # 等待超过双击检测窗口 (0.5s)
            triple_click_in_progress = False
        threading.Thread(target=reset_flag, daemon=True).start()

def get_trigger_keys(key_name):
    """
    根据配置的键名返回对应的 pynput Key 对象列表
    Args:
        key_name: 键名 (alt, ctrl, shift)
    Returns:
        list: 对应的 Key 对象列表
    """
    key_map = {
        'alt': [keyboard.Key.alt_l, keyboard.Key.alt_r],
        'ctrl': [keyboard.Key.ctrl_l, keyboard.Key.ctrl_r],
        'shift': [keyboard.Key.shift_l, keyboard.Key.shift_r],
    }
    return key_map.get(key_name.lower(), [keyboard.Key.alt_l, keyboard.Key.alt_r])

class AltTriggerListener(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = True
        self.last_trigger_time = 0

        # 从配置读取参数
        self.trigger_keys = get_trigger_keys(app_config.alt_trigger_key)
        self.triple_click_interval = app_config.alt_triple_click_interval
        self.wait_after_triple_click = app_config.alt_wait_after_triple_click
        self.debounce_interval = app_config.alt_debounce_interval
        self.play_count = app_config.alt_play_count

        self.db_manager = DatabaseManager()
        self.listener = None

        # 初始化自动补录触发器
        self.auto_record_trigger = AutoRecordTrigger()

        logger.info(f"[AltTrigger] Configured trigger key: {app_config.alt_trigger_key}")

    def run(self):
        logger.info("[AltTrigger] Starting listener...")
        with keyboard.Listener(on_release=self.on_release) as self.listener:
            self.listener.join()

    def stop(self):
        self.running = False
        if self.listener:
            self.listener.stop()

    def on_release(self, key):
        if not self.running:
            return False

        # 检查是否是配置的触发键
        if key in self.trigger_keys:
            current_time = time.time()
            if current_time - self.last_trigger_time < self.debounce_interval:
                return
            self.last_trigger_time = current_time
            threading.Thread(target=self._process_match, daemon=True).start()

    def _process_match(self):
        """处理匹配流程：三击选中 -> 查库 -> 播放或补录"""
        try:
            # 1. 执行三击选中文本
            print("[AltTrigger] Performing triple-click to select text...")
            triple_click(self.triple_click_interval)

            # 等待选中完成
            time.sleep(self.wait_after_triple_click)

            # 2. 使用 UI Automation 获取选中文本
            text = get_text_at_cursor()
            if not text:
                print("[AltTrigger] No text captured from UI Automation")
                return

            print(f"[AltTrigger] Captured text: {text[:100]}..." if len(text) > 100 else f"[AltTrigger] Captured text: {text}")

            if len(text) > 600:
                print(f"[AltTrigger] Text too long ({len(text)} chars), skipped")
                return

            # 3. 提取字母序列
            letter_seq = extract_letter_sequence(text)
            if not letter_seq:
                print("[AltTrigger] No letters extracted from text")
                return

            print(f"[AltTrigger] Letter sequence: {letter_seq[:50]}..." if len(letter_seq) > 50 else f"[AltTrigger] Letter sequence: {letter_seq}")

            # 4. 查询数据库
            record = self.db_manager.get_recording_by_letter_sequence(letter_seq)

            if record:
                # 匹配成功：播放录音
                number = record['number']
                print(f"[AltTrigger] Match found: #{number}, play_count={self.play_count}")
                self._send_play_command(number, self.play_count)
            else:
                # 匹配失败：触发自动补录流程
                print(f"[AltTrigger] No match found for sequence: {letter_seq[:30]}...")
                print("[AltTrigger] Triggering auto-record...")
                self.auto_record_trigger.trigger(text)

        except Exception as e:
            print(f"[AltTrigger] Error processing match: {e}")

    def _send_play_command(self, number, count=1):
        """
        发送播放命令到 UI 进程
        Args:
            number: 录音编号
            count: 播放次数
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.0)
                s.connect(('127.0.0.1', 65432))
                message = f"PLAY:{number}:{count}"
                s.sendall(message.encode('utf-8'))
        except Exception as e:
            print(f"[AltTrigger] Failed to send play command: {e}")