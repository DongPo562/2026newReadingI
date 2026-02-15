"""
emoji_trigger.py - 选中文本后触发 AI 生成 emoji 并插入
触发方式: Alt + \
"""
import threading
import time
from concurrent.futures import TimeoutError as FutureTimeoutError

import pyperclip
from pynput import keyboard
from pynput.keyboard import Controller as KeyboardController, Key

from ai_service import AIService
from config_loader import app_config
from ui_automation import get_selected_text


class EmojiTriggerListener:
    def __init__(self):
        self.enabled = app_config.emoji_trigger_enabled
        self.trigger_key = app_config.emoji_trigger_key
        self.trigger_delay = app_config.emoji_trigger_delay
        self._window_seconds = app_config.emoji_trigger_execution_window_seconds
        self.api_timeout = app_config.emoji_trigger_api_timeout
        self.fallback_emoji = app_config.emoji_trigger_fallback_emoji
        self.max_input_chars = app_config.emoji_trigger_max_input_chars

        self._last_trigger_time = 0.0
        self._cancel_event = threading.Event()
        self.listener = None
        self.alt_pressed = False
        self.keyboard_controller = KeyboardController()

        self.ai_service = AIService(
            model_id=app_config.emoji_trigger_model_id,
            enable_reasoning=app_config.emoji_trigger_enable_reasoning,
            api_timeout=self.api_timeout,
            enable_fallback=False,
            enable_retry=False,
        )

        print(f"[EmojiTrigger] Initialized (enabled={self.enabled}, trigger=Alt+\\, window={self._window_seconds}s)")

    def start(self):
        if not self.enabled:
            print("[EmojiTrigger] Disabled, not starting listener")
            return

        self.listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self.listener.start()
        print("[EmojiTrigger] Listener started")

    def stop(self):
        if self.listener:
            self.listener.stop()
            self.listener = None
        self.ai_service.shutdown()
        print("[EmojiTrigger] Listener stopped")

    def _is_backslash_key(self, key):
        try:
            if hasattr(key, "char") and key.char is not None:
                return key.char == self.trigger_key
            if hasattr(key, "vk"):
                return key.vk == 220
        except Exception:
            return False
        return False

    def _on_key_press(self, key):
        if key in (Key.alt_l, Key.alt_r):
            self.alt_pressed = True
            return
        if not (self.alt_pressed and self._is_backslash_key(key)):
            return

        now = time.time()
        if now - self._last_trigger_time < self._window_seconds:
            print("[EmojiTrigger] Within execution window, skipping")
            return

        self._cancel_event.set()
        self._cancel_event = threading.Event()
        self._last_trigger_time = now

        print("[EmojiTrigger] Alt+\\ detected")
        threading.Thread(target=self._process_trigger, daemon=True).start()

    def _on_key_release(self, key):
        if key in (Key.alt_l, Key.alt_r):
            self.alt_pressed = False

    def _contains_cjk_chars(self, text):
        for ch in text:
            code = ord(ch)
            if (
                0x4E00 <= code <= 0x9FFF
                or 0x3400 <= code <= 0x4DBF
                or 0x3040 <= code <= 0x30FF
                or 0x31F0 <= code <= 0x31FF
                or 0xAC00 <= code <= 0xD7AF
            ):
                return True
        return False

    def _validate_selection(self, text):
        if not text or not text.strip():
            print("[EmojiTrigger] Empty selection, skipping")
            return None

        cleaned = text.replace("\r", " ").replace("\n", " ").strip()
        if len(cleaned) > self.max_input_chars:
            print(f"[EmojiTrigger] Text too long ({len(cleaned)} > {self.max_input_chars}), skipping")
            return None

        if self._contains_cjk_chars(cleaned):
            print("[EmojiTrigger] Contains non-English chars, skipping")
            return None

        return cleaned

    def _insert_emoji(self, emoji_text):
        for key in (Key.ctrl_l, Key.ctrl_r, Key.alt_l, Key.alt_r, Key.shift):
            try:
                self.keyboard_controller.release(key)
            except Exception:
                pass

        self.keyboard_controller.press(Key.right)
        self.keyboard_controller.release(Key.right)
        time.sleep(0.1)

        pyperclip.copy(emoji_text)
        with self.keyboard_controller.pressed(Key.ctrl):
            self.keyboard_controller.press("v")
            self.keyboard_controller.release("v")

    def _process_trigger(self):
        cancel_event = self._cancel_event
        trigger_time = self._last_trigger_time

        try:
            time.sleep(self.trigger_delay)
            if cancel_event.is_set():
                print("[EmojiTrigger] Cancelled after delay")
                return

            selected = get_selected_text()
            cleaned_text = self._validate_selection(selected)
            if not cleaned_text:
                return

            print(f"[EmojiTrigger] Selected text: '{cleaned_text}'")
            fallback_mode = False
            emoji_text = ""

            future = self.ai_service.generate_emoji(cleaned_text)

            def late_response_monitor():
                try:
                    result = future.result(timeout=self.api_timeout + 20)
                    print(f"[EmojiTrigger] Late response received: '{result}'")
                except FutureTimeoutError:
                    print(f"[EmojiTrigger] No response after {self.api_timeout + 20}s")
                except Exception as e:
                    pass

            threading.Thread(target=late_response_monitor, daemon=True).start()

            try:
                emoji_text = future.result(timeout=self.api_timeout + 0.5)
            except FutureTimeoutError:
                fallback_mode = True
                print(f"[EmojiTrigger] API timeout, inserting fallback emoji '{self.fallback_emoji}'")
            except Exception:
                fallback_mode = True
                print(f"[EmojiTrigger] API failed, inserting fallback emoji '{self.fallback_emoji}'")

            if fallback_mode:
                emoji_text = self.fallback_emoji

            if cancel_event.is_set():
                print("[EmojiTrigger] Cancelled after API response")
                return

            if not fallback_mode and time.time() - trigger_time > self._window_seconds:
                print("[EmojiTrigger] Execution window expired, discarding")
                return

            latest_selected = get_selected_text()
            latest_cleaned = latest_selected.replace("\r", " ").replace("\n", " ").strip() if latest_selected else ""
            if not latest_cleaned:
                print("[EmojiTrigger] Selection changed during API wait, aborting insert")
                return
            if latest_cleaned != cleaned_text:
                print("[EmojiTrigger] Selection changed during API wait, continuing with non-empty selection")

            if cancel_event.is_set():
                print("[EmojiTrigger] Cancelled before insert")
                return

            self._insert_emoji(emoji_text)
            print(f"[EmojiTrigger] Inserted emoji '{emoji_text}' after '{cleaned_text}'")
        except Exception as e:
            print(f"[EmojiTrigger] Error: {e}")
