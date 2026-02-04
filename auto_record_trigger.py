import time
import winsound
import logging
import asyncio
import os
import socket
from typing import Optional, Tuple
import pyautogui
from winocr import recognize_pil
from PIL import ImageGrab
from config_loader import app_config
from audio_recorder import AudioRecorder

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("AutoRecord")

# pyautogui safety settings
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.01  # Minimal pause between pyautogui actions

# 调试模式：设为 True 时保存截图并打印详细 OCR 结果
DEBUG_MODE = True
DEBUG_SCREENSHOT_PATH = "ocr_debug.png"

class AutoRecordTrigger:
    """
    自动补录触发器

    当 Alt 键匹配失败时，自动触发 TTS 软件朗读并录制：
    1. 等待 TTS 软件的悬浮横条出现（AltTrigger 已经执行了三击选中文本）
    2. 使用 OCR 在鼠标上方区域搜索「朗读」
    3. 找到后点击朗读按钮，然后立即启动 AudioRecorder
    4. AudioRecorder 会自动录制系统音频并保存到数据库

    注意：本模块不执行三击，因为 AltTrigger 在调用本模块前已经执行了三击选中文本
    """

    def __init__(self):
        """
        初始化自动补录触发器，从配置文件读取参数
        """
        # 从配置文件读取参数
        self.wait_for_toolbar = app_config.auto_record_wait_for_toolbar
        self.ocr_search_offset_y = app_config.auto_record_ocr_search_offset_y
        self.ocr_search_width = app_config.auto_record_ocr_search_width

        logger.info("[AutoRecord] AutoRecordTrigger initialized")
        logger.info(f"[AutoRecord] Config: wait_for_toolbar={self.wait_for_toolbar}s, "
                    f"ocr_offset_y={self.ocr_search_offset_y}px, ocr_width={self.ocr_search_width}px")
        if DEBUG_MODE:
            logger.info(f"[AutoRecord] DEBUG MODE ENABLED - Screenshots will be saved to {DEBUG_SCREENSHOT_PATH}")

    def _calculate_search_region(self, x: int, y: int) -> Tuple[int, int, int, int]:
        """
        计算 OCR 搜索区域

        Args:
            x: 鼠标 x 坐标
            y: 鼠标 y 坐标

        Returns:
            Tuple[int, int, int, int]: (left, top, right, bottom) 屏幕区域坐标
        """
        left = max(0, x - 20)  # 留一点余量
        right = x + self.ocr_search_width
        top = max(0, y - self.ocr_search_offset_y)  # 横条在上方
        bottom = y - 10  # 不低于鼠标位置

        return (left, top, right, bottom)

    def ocr_find_text(self, region: Tuple[int, int, int, int], target_text: str = "朗") -> Optional[Tuple[int, int]]:
        """
        使用 OCR 在指定屏幕区域搜索目标文字

        Args:
            region: (left, top, right, bottom) 屏幕区域坐标
            target_text: 要搜索的目标文字，默认「朗」（因为 winocr 会把「朗读」拆成两个字）

        Returns:
            Optional[Tuple[int, int]]: 找到时返回屏幕绝对坐标（中心点），未找到返回 None
        """
        try:
            left, top, right, bottom = region

            # 确保区域有效
            if right <= left or bottom <= top:
                logger.warning(f"[AutoRecord] Invalid OCR region: {region}")
                return None

            # 截取屏幕区域
            screenshot = ImageGrab.grab(bbox=(left, top, right, bottom))

            # 调试：保存截图
            if DEBUG_MODE:
                try:
                    screenshot.save(DEBUG_SCREENSHOT_PATH)
                    logger.info(f"[AutoRecord] DEBUG: Screenshot saved to {DEBUG_SCREENSHOT_PATH}")
                except Exception as e:
                    logger.error(f"[AutoRecord] DEBUG: Failed to save screenshot: {e}")

            # 使用 winocr 进行 OCR 识别
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(recognize_pil(screenshot, 'zh-CN'))
            finally:
                loop.close()

            # 调试：打印所有 OCR 结果
            if DEBUG_MODE:
                logger.info(f"[AutoRecord] DEBUG: === OCR Results ===")
                logger.info(f"[AutoRecord] DEBUG: Total lines: {len(result.lines)}")
                for i, line in enumerate(result.lines):
                    logger.info(f"[AutoRecord] DEBUG: Line {i}: '{line.text}'")
                    for word in line.words:
                        bbox = word.bounding_rect
                        logger.info(f"[AutoRecord] DEBUG:   Word: '{word.text}' at ({bbox.x}, {bbox.y}, {bbox.width}x{bbox.height})")
                logger.info(f"[AutoRecord] DEBUG: === End OCR Results ===")

            # 搜索目标文字
            for line in result.lines:
                if target_text in line.text:
                    # 计算该文字在屏幕上的绝对坐标（中心点）
                    # line.words 包含每个词的边界框信息
                    for word in line.words:
                        if target_text in word.text:
                            # winocr 返回的是相对于截图的坐标
                            # 需要转换为屏幕绝对坐标
                            bbox = word.bounding_rect
                            center_x = left + bbox.x + bbox.width // 2
                            center_y = top + bbox.y + bbox.height // 2

                            logger.info(f"[AutoRecord] Found '{target_text}' at screen position ({center_x}, {center_y})")
                            return (center_x, center_y)

            logger.info(f"[AutoRecord] '{target_text}' not found in OCR result")
            return None

        except Exception as e:
            logger.error(f"[AutoRecord] OCR failed: {e}")
            return None

    def _play_failure_beep(self):
        """
        播放失败提示音
        """
        try:
            winsound.Beep(800, 200)  # 800Hz, 200ms
        except Exception as e:
            logger.error(f"[AutoRecord] Failed to play beep: {e}")

    def trigger(self, text: str) -> bool:
        """
        执行完整的自动补录流程

        注意：调用此方法前，AltTrigger 已经执行了三击选中文本，
        所以本方法不再执行三击，只等待悬浮条出现并点击朗读按钮。

        流程：
        1. 等待悬浮横条出现
        2. OCR 搜索「朗」按钮
        3. 找到后：发送静默录音命令 → 点击朗读按钮 → 启动 AudioRecorder
        4. AudioRecorder 会自动检测声音、录制、保存到数据库并通知 UI

        重要：必须先点击朗读按钮再启动 AudioRecorder，否则启动 AudioRecorder 的延迟
        可能导致选中状态丢失，TTS 会朗读鼠标悬浮的单词而不是选中的文本。

        Args:
            text: 匹配失败的文本（用于录音保存）

        Returns:
            bool: 是否成功触发 TTS 朗读和录音
        """
        try:
            logger.info(f"[AutoRecord] Starting auto-record for text: {text[:50]}..." if len(text) > 50 else f"[AutoRecord] Starting auto-record for text: {text}")

            # 1. 获取当前鼠标位置
            x, y = pyautogui.position()
            logger.info(f"[AutoRecord] Mouse position: ({x}, {y})")

            # 2. 等待悬浮横条出现（AltTrigger 已经执行了三击，不需要再次三击）
            logger.info(f"[AutoRecord] Waiting {self.wait_for_toolbar}s for toolbar to appear...")
            time.sleep(self.wait_for_toolbar)

            # 3. 计算 OCR 搜索区域
            region = self._calculate_search_region(x, y)
            logger.info(f"[AutoRecord] OCR search region: {region}")

            # 4. OCR 搜索「朗」（winocr 会把「朗读」拆成两个独立的字）
            button_pos = self.ocr_find_text(region, "朗")

            if button_pos:
                # 5. 找到了，执行点击和录音
                btn_x, btn_y = button_pos
                try:
                    # 5.1 发送 SILENT_RECORD_START 命令，通知 UI 进入静默录音模式
                    self._send_silent_record_command()

                    # 5.2 先点击朗读按钮，触发 TTS 播放
                    # 重要：必须在启动 AudioRecorder 之前点击，否则可能因为延迟导致选中状态丢失，
                    # TTS 会朗读鼠标悬浮的单词而不是选中的文本
                    pyautogui.click(btn_x, btn_y)
                    logger.info(f"[AutoRecord] Clicked '朗读' button at ({btn_x}, {btn_y})")

                    # 5.3 点击后立即启动 AudioRecorder
                    # AudioRecorder 有 start_silence_duration 秒（默认6秒）的等待声音窗口，
                    # 不会错过 TTS 的开头
                    logger.info(f"[AutoRecord] Starting AudioRecorder with content: {text[:30]}...")
                    recorder = AudioRecorder(text)
                    recorder.start()

                    # AudioRecorder 会在后台自动：
                    # - 检测声音开始
                    # - 录制音频
                    # - 检测声音结束
                    # - 保存到数据库
                    # - 通知 UI 刷新列表

                    return True
                except pyautogui.FailSafeException:
                    logger.warning("[AutoRecord] FailSafe triggered during click")
                    self._play_failure_beep()
                    return False
                except Exception as e:
                    logger.error(f"[AutoRecord] Failed to start recording or click button: {e}")
                    self._play_failure_beep()
                    return False
            else:
                # 6. 未找到，播放提示音并放弃
                logger.info("[AutoRecord] '朗读' button not found, playing failure beep")
                self._play_failure_beep()
                return False

        except Exception as e:
            logger.error(f"[AutoRecord] Auto-record trigger failed: {e}")
            self._play_failure_beep()
            return False

    def _send_silent_record_command(self):
        """
        发送静默录音命令到 UI 进程
        通知 UI 进程即将进行自动补录，根据配置决定是否在录音完成后自动播放
        """
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(1.0)  # 1秒超时
            client.connect(('127.0.0.1', 65432))
            client.sendall(b"SILENT_RECORD_START")
            client.close()
            logger.info("[AutoRecord] Sent SILENT_RECORD_START command to UI")
        except socket.timeout:
            logger.warning("[AutoRecord] Timeout sending SILENT_RECORD_START command")
        except ConnectionRefusedError:
            logger.warning("[AutoRecord] UI not available, SILENT_RECORD_START command not sent")
        except Exception as e:
            logger.error(f"[AutoRecord] Failed to send SILENT_RECORD_START command: {e}")