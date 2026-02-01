"""
ctrl_trigger.py - Ctrl 长按录音触发器

功能：
1. 检测纯 Ctrl 键长按 >= 1.5秒（期间无其他按键）
2. 释放后 100ms 内有其他按键则取消触发
3. 使用 winocr 获取鼠标悬浮位置的单词
4. 清洗文本（去除开头/结尾的 !?.,）
5. 校验文本（只允许 a-zA-Z'- 和空格）
6. 重复文本：等系统声音结束 -> 延迟 -> 播放已有录音
7. 新文本：录制 -> 保存 -> 刷新 UI
8. 支持即时取消：再次按 Ctrl 可取消当前流程
"""
import re
import time
import threading
import socket
import ctypes
import asyncio
from ctypes import wintypes
from pynput import keyboard
from PIL import ImageGrab
from winocr import recognize_pil
from config_loader import app_config
from db_manager import DatabaseManager
from audio_recorder import AudioRecorder


# 可清洗的标点（只在开头和结尾）
STRIP_CHARS = "!?.,"

# 清洗后，文本只能包含这些字符
VALID_PATTERN = re.compile(r"^[a-zA-Z'\- ]+$")

# OCR 配置
OCR_REGION_WIDTH = 500   # 截图宽度
OCR_REGION_HEIGHT = 100  # 截图高度
H_SHRINK_RATIO = 0.03    # 水平收缩比例
V_SHRINK_RATIO = 0.05    # 垂直收缩比例
MIN_SHRINK_PX = 2        # 最小收缩像素


def get_cursor_position():
    """获取当前鼠标位置"""
    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def shrink_bbox(x, y, w, h, h_ratio=H_SHRINK_RATIO, v_ratio=V_SHRINK_RATIO, min_shrink=MIN_SHRINK_PX):
    """
    收缩边界框，生成单词识别区域
    
    Args:
        x, y, w, h: 原始边界框
        h_ratio: 水平收缩比例（左右各收缩）
        v_ratio: 垂直收缩比例（上下各收缩）
        min_shrink: 最小收缩像素
    
    Returns:
        (new_x, new_y, new_w, new_h): 收缩后的边界框
    """
    h_shrink = max(w * h_ratio, min_shrink)
    v_shrink = max(h * v_ratio, min_shrink)
    
    new_x = x + h_shrink
    new_y = y + v_shrink
    new_w = w - 2 * h_shrink
    new_h = h - 2 * v_shrink
    
    # 确保宽高不为负
    if new_w <= 0 or new_h <= 0:
        return x, y, w, h  # 返回原始框
    
    return new_x, new_y, new_w, new_h


def point_in_rect(px, py, x, y, w, h):
    """检查点是否在矩形内（包含边框）"""
    return x <= px <= x + w and y <= py <= y + h


def get_word_at_cursor():
    """
    使用 winocr 获取鼠标位置的单词
    
    策略：
    1. 截取鼠标周围区域
    2. winocr 识别所有单词及其边界框
    3. 对每个单词的边界框进行收缩
    4. 检查鼠标是否在收缩后的区域内
    5. 如果在，返回该单词；否则返回 None
    
    Returns:
        str: 识别到的单词
        None: 未识别到或识别失败
    """
    try:
        # 1. 获取鼠标位置
        cursor_x, cursor_y = get_cursor_position()
        print(f"[CtrlTrigger] DEBUG: Mouse position = ({cursor_x}, {cursor_y})")
        
        # 2. 计算截图区域（鼠标居中）
        left = cursor_x - OCR_REGION_WIDTH // 2
        top = cursor_y - OCR_REGION_HEIGHT // 2
        right = left + OCR_REGION_WIDTH
        bottom = top + OCR_REGION_HEIGHT
        
        # 3. 截图
        screenshot = ImageGrab.grab(bbox=(left, top, right, bottom))
        print(f"[CtrlTrigger] DEBUG: Screenshot region = ({left}, {top}, {right}, {bottom})")
        
        # 4. 使用 winocr 进行 OCR 识别（英文）
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(recognize_pil(screenshot, 'en'))
        finally:
            loop.close()
        
        # 5. 鼠标在截图中的相对位置
        rel_cursor_x = OCR_REGION_WIDTH // 2
        rel_cursor_y = OCR_REGION_HEIGHT // 2
        
        # 6. 遍历每个识别到的单词
        word_count = 0
        for line in result.lines:
            for word_obj in line.words:
                word_count += 1
        print(f"[CtrlTrigger] DEBUG: OCR found {word_count} words")
        
        for line in result.lines:
            for word_obj in line.words:
                word = word_obj.text
                
                # 跳过空文本
                if not word or not word.strip():
                    continue
                
                # 获取边界框（winocr 的 bounding_rect）
                bbox = word_obj.bounding_rect
                x = bbox.x
                y = bbox.y
                w = bbox.width
                h = bbox.height
                
                # 收缩边界框
                sx, sy, sw, sh = shrink_bbox(x, y, w, h)
                
                print(f"[CtrlTrigger] DEBUG: Word '{word}' bbox=({x},{y},{w},{h}) -> shrunk=({sx:.1f},{sy:.1f},{sw:.1f},{sh:.1f})")
                
                # 检查鼠标是否在收缩后的区域内
                if point_in_rect(rel_cursor_x, rel_cursor_y, sx, sy, sw, sh):
                    print(f"[CtrlTrigger] OCR matched word: '{word}'")
                    return word.strip()
        
        print("[CtrlTrigger] OCR: No word found at cursor position")
        return None
        
    except Exception as e:
        print(f"[CtrlTrigger] OCR error: {e}")
        import traceback
        traceback.print_exc()
        return None


def clean_and_validate(text):
    """
    清洗并校验文本
    
    Returns:
        str: 清洗后的有效文本
        None: 校验失败
    """
    if not text:
        return None
    
    # 第一步：去除开头和结尾的 !?.，
    cleaned = text.strip(STRIP_CHARS).strip()
    
    if not cleaned:
        return None
    
    # 第二步：校验只包含合法字符
    if not VALID_PATTERN.match(cleaned):
        return None
    
    return cleaned


class CtrlTriggerListener:
    """
    Ctrl 长按触发器
    
    监听 Ctrl 键长按事件，触发录音流程。
    支持即时取消：再次触发时会取消当前正在运行的流程。
    """
    
    def __init__(self):
        # 从配置读取参数
        self.enabled = app_config.ctrl_trigger_enabled
        self.hold_duration = app_config.ctrl_trigger_hold_duration
        self.cancel_window = app_config.ctrl_trigger_cancel_window
        self.sound_detect_timeout = app_config.ctrl_trigger_sound_detect_timeout
        self.duplicate_play_delay = app_config.ctrl_trigger_duplicate_play_delay
        
        # 状态变量
        self.ctrl_press_time = None
        self.other_key_pressed = False
        self.trigger_pending = False
        self.release_time = None
        
        # 键盘监听器
        self.listener = None
        self.cancel_timer = None
        
        # 取消机制
        self.cancel_event = threading.Event()
        self.current_thread = None
        
        # 数据库管理器
        self.db = DatabaseManager()
        self.db.connect()
        
        print(f"[CtrlTrigger] Initialized (enabled={self.enabled})")
        if self.enabled:
            print(f"[CtrlTrigger] Config: hold={self.hold_duration}s, "
                  f"cancel_window={self.cancel_window}s, "
                  f"sound_timeout={self.sound_detect_timeout}s")
    
    def start(self):
        """启动监听器"""
        if not self.enabled:
            print("[CtrlTrigger] Disabled, not starting listener")
            return
        
        self.listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release
        )
        self.listener.start()
        print("[CtrlTrigger] Listener started")
    
    def stop(self):
        """停止监听器"""
        if self.listener:
            self.listener.stop()
            self.listener = None
        if self.cancel_timer:
            self.cancel_timer.cancel()
            self.cancel_timer = None
        # 取消正在运行的流程
        self.cancel_event.set()
        print("[CtrlTrigger] Listener stopped")
    
    def _is_ctrl_key(self, key):
        """检查是否是 Ctrl 键"""
        return key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r, keyboard.Key.ctrl)
    
    def _on_key_press(self, key):
        """按键按下事件"""
        if self._is_ctrl_key(key):
            # Ctrl 键按下
            if self.ctrl_press_time is None:
                self.ctrl_press_time = time.time()
                self.other_key_pressed = False
                print("[CtrlTrigger] Ctrl pressed, starting timer")
        else:
            # 其他键按下
            if self.ctrl_press_time is not None:
                # Ctrl 按住期间有其他键按下，标记为无效
                self.other_key_pressed = True
                print(f"[CtrlTrigger] Other key pressed during Ctrl hold, invalidated")
            
            if self.trigger_pending:
                # 释放后等待期间有其他键按下，取消触发
                self.trigger_pending = False
                if self.cancel_timer:
                    self.cancel_timer.cancel()
                    self.cancel_timer = None
                print(f"[CtrlTrigger] Key pressed during cancel window, trigger cancelled")
    
    def _on_key_release(self, key):
        """按键释放事件"""
        if not self._is_ctrl_key(key):
            return
        
        if self.ctrl_press_time is None:
            return
        
        held_duration = time.time() - self.ctrl_press_time
        self.ctrl_press_time = None
        
        print(f"[CtrlTrigger] Ctrl released after {held_duration:.2f}s")
        
        # 检查是否满足触发条件
        if held_duration < self.hold_duration:
            print(f"[CtrlTrigger] Hold duration too short ({held_duration:.2f}s < {self.hold_duration}s)")
            return
        
        if self.other_key_pressed:
            print("[CtrlTrigger] Other key was pressed during hold, not triggering")
            self.other_key_pressed = False
            return
        
        # 满足条件，进入取消窗口等待期
        self.trigger_pending = True
        self.release_time = time.time()
        
        # 设置定时器，等待取消窗口结束后触发
        self.cancel_timer = threading.Timer(
            self.cancel_window,
            self._execute_trigger
        )
        self.cancel_timer.start()
        print(f"[CtrlTrigger] Waiting {self.cancel_window}s for cancel window")
    
    def _execute_trigger(self):
        """执行触发流程"""
        if not self.trigger_pending:
            print("[CtrlTrigger] Trigger was cancelled")
            return
        
        self.trigger_pending = False
        
        # 如果有旧流程在运行，立即取消
        if self.current_thread and self.current_thread.is_alive():
            print("[CtrlTrigger] Cancelling previous flow immediately...")
            self.cancel_event.set()
            # 等待旧线程退出（最多等 0.5 秒）
            self.current_thread.join(timeout=0.5)
            if self.current_thread.is_alive():
                print("[CtrlTrigger] Warning: Previous thread still alive, proceeding anyway")
        
        # 清除取消标志，启动新流程
        self.cancel_event.clear()
        print("[CtrlTrigger] Executing trigger...")
        
        # 在新线程中执行，避免阻塞键盘监听
        self.current_thread = threading.Thread(target=self._run_process_flow)
        self.current_thread.start()
    
    def _run_process_flow(self):
        """处理流程"""
        try:
            # 检查取消标志
            if self.cancel_event.is_set():
                print("[CtrlTrigger] Flow cancelled at start")
                return
            
            # 1. 使用 OCR 获取鼠标悬浮位置的单词
            raw_text = get_word_at_cursor()
            print(f"[CtrlTrigger] Got text: '{raw_text}'")
            
            if self.cancel_event.is_set():
                print("[CtrlTrigger] Flow cancelled after getting text")
                return
            
            # 2. 清洗并校验文本
            cleaned_text = clean_and_validate(raw_text)
            if cleaned_text is None:
                print("[CtrlTrigger] Text validation failed, aborting")
                return
            
            print(f"[CtrlTrigger] Cleaned text: '{cleaned_text}'")
            
            # 3. 查询数据库是否已存在
            from text_processor import extract_letter_sequence
            letter_seq = extract_letter_sequence(cleaned_text)
            existing = self.db.get_recording_by_letter_sequence(letter_seq)
            
            if self.cancel_event.is_set():
                print("[CtrlTrigger] Flow cancelled after DB check")
                return
            
            if existing:
                # 重复文本
                print(f"[CtrlTrigger] Duplicate found: number={existing['number']}")
                self._handle_duplicate(existing)
            else:
                # 新文本
                print("[CtrlTrigger] New text, starting recording")
                self._handle_new_text(cleaned_text)
                
        except Exception as e:
            print(f"[CtrlTrigger] Error in process flow: {e}")
            import traceback
            traceback.print_exc()
    
    def _handle_duplicate(self, existing_record):
        """
        处理重复文本：等待系统声音结束后播放已有录音
        
        Args:
            existing_record: 数据库中已存在的记录
        """
        number = existing_record['number']
        
        # 等待系统声音（使用 AudioRecorder 的声音检测逻辑）
        print(f"[CtrlTrigger] Waiting for system sound (timeout={self.sound_detect_timeout}s)")
        
        sound_detected = self._wait_for_sound()
        
        if not sound_detected:
            print("[CtrlTrigger] No sound detected or cancelled, aborting")
            return
        
        # 等待声音结束
        print("[CtrlTrigger] Sound detected, waiting for it to end")
        if not self._wait_for_sound_end():
            print("[CtrlTrigger] Cancelled while waiting for sound end")
            return
        
        # 检查取消标志
        if self.cancel_event.is_set():
            print("[CtrlTrigger] Cancelled before playback")
            return
        
        # 延迟后播放
        print(f"[CtrlTrigger] Sound ended, waiting {self.duplicate_play_delay}s before playback")
        time.sleep(self.duplicate_play_delay)
        
        # 再次检查取消标志
        if self.cancel_event.is_set():
            print("[CtrlTrigger] Cancelled before sending play command")
            return
        
        # 发送播放命令到 UI
        self._send_play_command(number)
    
    def _handle_new_text(self, text):
        """
        处理新文本：启动录音
        
        Args:
            text: 清洗后的文本
        """
        # 检查取消标志
        if self.cancel_event.is_set():
            print("[CtrlTrigger] Cancelled before starting recording")
            return
        
        # 发送停止当前播放命令
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                s.connect(('127.0.0.1', 65432))
                s.sendall(b"STOP_PLAYBACK")
        except Exception as e:
            print(f"[CtrlTrigger] Warning: Could not stop playback: {e}")
        
        # 启动录音，使用 CtrlTrigger 配置的超时时间
        recorder = AudioRecorder(text, start_silence_duration=self.sound_detect_timeout)
        recorder.start()
    
    def _wait_for_sound(self):
        """
        等待系统声音出现
        
        Returns:
            bool: 是否检测到声音（False 也可能表示被取消）
        """
        import soundcard as sc
        import numpy as np
        
        start_time = time.time()
        silence_threshold = app_config.silence_threshold_db
        
        try:
            # 获取默认扬声器的回环设备
            speakers = sc.all_speakers()
            default_speaker = sc.default_speaker()
            loopback = sc.get_microphone(id=str(default_speaker.name), include_loopback=True)
            
            with loopback.recorder(samplerate=44100, channels=2) as recorder:
                while time.time() - start_time < self.sound_detect_timeout:
                    # 检查取消标志
                    if self.cancel_event.is_set():
                        print("[CtrlTrigger] _wait_for_sound cancelled")
                        return False
                    
                    # 读取一小段音频
                    data = recorder.record(numframes=4410)  # 0.1秒
                    
                    # 计算音量（dB）
                    if len(data) > 0:
                        rms = np.sqrt(np.mean(data ** 2))
                        if rms > 0:
                            db = 20 * np.log10(rms)
                            if db > silence_threshold:
                                return True
                
        except Exception as e:
            print(f"[CtrlTrigger] Error detecting sound: {e}")
        
        return False
    
    def _wait_for_sound_end(self):
        """
        等待系统声音结束（静音持续一段时间）
        
        Returns:
            bool: True 表示正常结束，False 表示被取消
        """
        import soundcard as sc
        import numpy as np
        
        silence_threshold = app_config.silence_threshold_db
        end_silence_duration = app_config.end_silence_duration
        silence_start = None
        
        try:
            default_speaker = sc.default_speaker()
            loopback = sc.get_microphone(id=str(default_speaker.name), include_loopback=True)
            
            with loopback.recorder(samplerate=44100, channels=2) as recorder:
                while True:
                    # 检查取消标志
                    if self.cancel_event.is_set():
                        print("[CtrlTrigger] _wait_for_sound_end cancelled")
                        return False
                    
                    data = recorder.record(numframes=4410)  # 0.1秒
                    
                    if len(data) > 0:
                        rms = np.sqrt(np.mean(data ** 2))
                        db = 20 * np.log10(rms) if rms > 0 else -100
                        
                        if db <= silence_threshold:
                            if silence_start is None:
                                silence_start = time.time()
                            elif time.time() - silence_start >= end_silence_duration:
                                return True
                        else:
                            silence_start = None
                            
        except Exception as e:
            print(f"[CtrlTrigger] Error waiting for sound end: {e}")
        
        return False
    
    def _send_play_command(self, number):
        """
        发送播放命令到 UI 进程
        
        Args:
            number: 录音编号
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.0)
                s.connect(('127.0.0.1', 65432))
                # 发送播放命令，格式：PLAY:number
                s.sendall(f"PLAY:{number}".encode())
                print(f"[CtrlTrigger] Sent play command for number={number}")
        except Exception as e:
            print(f"[CtrlTrigger] Failed to send play command: {e}")