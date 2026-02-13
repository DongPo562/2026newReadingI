"""
quiz_trigger.py - Ctrl+U 出题触发器（阶段二）
"""
import threading
import time
import json
import subprocess
import sys
import os
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime
from pynput import keyboard
from ui_automation import get_selected_text, get_text_at_cursor
from db_manager import DatabaseManager
from config_loader import app_config
from ai_service import AIService

class QuizTriggerListener:
    def __init__(self):
        self.enabled = app_config.quiz_trigger_enabled
        self.trigger_delay = app_config.quiz_trigger_delay
        self.debounce_interval = app_config.quiz_trigger_debounce_interval
        self.api_timeout = app_config.quiz_trigger_api_timeout
        self.fallback_to_local = app_config.quiz_trigger_fallback_to_local

        self.listener = None
        self.ctrl_pressed = False
        self.last_trigger_time = 0.0

        self.ai_service = AIService()

        # 确保 review_questions 表和字段已就绪
        init_db = DatabaseManager()
        init_db.init_db()
        init_db.close()

        print(
            f"[QuizTrigger] Initialized "
            f"(enabled={self.enabled}, delay={self.trigger_delay}s, debounce={self.debounce_interval}s)"
        )

    def start(self):
        if not self.enabled:
            print("[QuizTrigger] Disabled, not starting listener")
            return
        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        )
        self.listener.start()
        print("[QuizTrigger] Listener started")

    def stop(self):
        if self.listener:
            self.listener.stop()
            self.listener = None
        self.ai_service.shutdown()
        print("[QuizTrigger] Listener stopped")

    def _is_u_key(self, key):
        try:
            if hasattr(key, "char") and key.char is not None:
                return key.char.lower() == "u" or key.char == "\x15"
            if hasattr(key, "vk"):
                return key.vk == 85
        except Exception:
            pass
        return False

    def _on_press(self, key):
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            self.ctrl_pressed = True
            return

        if not (self.ctrl_pressed and self._is_u_key(key)):
            return

        now = time.time()
        if now - self.last_trigger_time < self.debounce_interval:
            print("[QuizTrigger] Debounced duplicate Ctrl+U")
            return
        self.last_trigger_time = now

        print("[QuizTrigger] Ctrl+U detected")
        threading.Thread(target=self._process_trigger, daemon=True).start()

    def _on_release(self, key):
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            self.ctrl_pressed = False

    def _generate_local_fill_question(self, content, sentence_content):
        question_text = sentence_content.replace(content, "______", 1)
        if not question_text:
            question_text = f"Fill in the blank: ______ ({content})"
        return json.dumps(
            {"type": "fill", "question": question_text, "answer": content},
            ensure_ascii=False
        )

    def _launch_quiz_card(self, question_id):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        quiz_card_path = os.path.join(script_dir, "quiz_card.py")
        subprocess.Popen(
            [sys.executable, quiz_card_path, str(question_id)],
            cwd=script_dir
        )
        print(f"[QuizTrigger] Quiz card launched for question id={question_id}")

    def _process_trigger(self):
        try:
            time.sleep(self.trigger_delay)

            content = get_selected_text()
            if not content or not content.strip():
                print("[QuizTrigger] Empty content, skipping")
                return
            content = content.strip()
            print(f"[QuizTrigger] Content: '{content}'")

            sentence_content = get_text_at_cursor()
            if not sentence_content or not sentence_content.strip():
                print("[QuizTrigger] Empty sentence_content, using content as fallback")
                sentence_content = content
            sentence_content = sentence_content.strip()
            print(
                f"[QuizTrigger] Sentence: "
                f"'{sentence_content[:100]}{'...' if len(sentence_content) > 100 else ''}'"
            )

            save_time = datetime.now().strftime("%Y%m%d%H%M%S")
            db = DatabaseManager()
            question_id = db.insert_question(
                save_time=save_time,
                content=content,
                sentence_content=sentence_content,
                ai_question=None,
                ai_status="pending",
            )
            db.close()
            print(f"[QuizTrigger] Question saved, id={question_id}, ai_status=pending")

            future = self.ai_service.generate_question(question_id, content, sentence_content)

            try:
                status, result_json = future.result(timeout=self.api_timeout + 0.5)
            except FutureTimeoutError:
                print(f"[QuizTrigger] AI request timeout, id={question_id}")
                db = DatabaseManager()
                try:
                    if self.fallback_to_local:
                        fallback_json = self._generate_local_fill_question(content, sentence_content)
                        db.update_question_ai_result(question_id, fallback_json, "failed")
                    else:
                        db.update_question_status(question_id, "failed")
                finally:
                    db.close()
                if self.fallback_to_local:
                    self._launch_quiz_card(question_id)
                return
            except Exception as e:
                print(f"[QuizTrigger] AI future failed, id={question_id}: {e}")
                db = DatabaseManager()
                try:
                    if self.fallback_to_local:
                        fallback_json = self._generate_local_fill_question(content, sentence_content)
                        db.update_question_ai_result(question_id, fallback_json, "failed")
                    else:
                        db.update_question_status(question_id, "failed")
                finally:
                    db.close()
                if self.fallback_to_local:
                    self._launch_quiz_card(question_id)
                return

            db = DatabaseManager()
            try:
                db.update_question_ai_result(question_id, result_json, status)
                print(f"[QuizTrigger] AI result saved, id={question_id}, status={status}")
            except Exception as e:
                print(f"[QuizTrigger] Failed to save AI result: {e}")
            finally:
                db.close()

            if status == "success":
                self._launch_quiz_card(question_id)
                return

            # failed
            if self.fallback_to_local:
                self._launch_quiz_card(question_id)
            else:
                print(f"[QuizTrigger] AI failed and fallback disabled, id={question_id}")

        except Exception as e:
            print(f"[QuizTrigger] Error: {e}")
            import traceback
            traceback.print_exc()