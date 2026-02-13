"""
quiz_card.py - 多题型答题卡片（阶段二）
"""
import sys
import json
import re
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QRadioButton,
    QButtonGroup,
    QScrollArea,
    QFrame,
    QGraphicsDropShadowEffect,
)

from db_manager import DatabaseManager
from config_loader import app_config


class QuizCard(QWidget):
    CARD_WIDTH = 800
    MIN_HEIGHT = 250
    MAX_HEIGHT = 700

    def __init__(self, question_id):
        super().__init__()
        self.db = DatabaseManager()
        self.question_id = question_id
        self.question_record = self.db.get_question(question_id)
        if not self.question_record:
            raise RuntimeError(f"Question not found: id={question_id}")

        self.question_data = self._load_question_data()
        self.question_type = self.question_data.get("type", "fill")
        self.current_answer = str(self.question_data.get("answer", "")).strip()
        self.option_buttons = []

        self.base_font_size = app_config.quiz_card_font_size
        self.opacity = app_config.quiz_card_opacity

        self._init_ui()
        self._show_question()

    def _load_question_data(self):
        raw = self.question_record["ai_question"] if "ai_question" in self.question_record.keys() else None
        try:
            if raw:
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
        except Exception as error:
            print(f"[QuizCard] Invalid ai_question JSON, fallback to local fill: {error}")

        content = self.question_record["content"]
        sentence_content = self.question_record["sentence_content"] or content
        return {
            "type": "fill",
            "question": sentence_content.replace(content, "", 1),
            "answer": content,
        }

    def _init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(self.opacity)
        self.setMinimumSize(self.CARD_WIDTH, self.MIN_HEIGHT)
        self.setMaximumSize(self.CARD_WIDTH, self.MAX_HEIGHT)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self.container = QWidget(self)
        self.container.setStyleSheet(
            """
            QWidget {
                background-color: #2b2b2b;
                border-radius: 12px;
                border: 1px solid #3d3d3d;
                color: #FFFFFF;
                font-family: 'Microsoft YaHei UI';
            }
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 8px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #555555;
                border-radius: 4px;
                min-height: 18px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            """
        )

        shadow = QGraphicsDropShadowEffect(self.container)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 140))
        self.container.setGraphicsEffect(shadow)

        outer_layout.addWidget(self.container)

        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(20, 18, 20, 16)
        self.layout.setSpacing(8)

        self.title_label = QLabel("")
        self.title_label.setFont(QFont("Microsoft YaHei UI", self.base_font_size, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #81D4FA; border: none; background: transparent;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.layout.addWidget(self.title_label)

        self.content_scroll = QScrollArea()
        self.content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.layout.addWidget(self.content_scroll, 1)

        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent; border: none;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 4, 8, 6)
        self.content_layout.setSpacing(10)
        self.content_scroll.setWidget(self.content_widget)

        self.question_label = QLabel("")
        self.question_label.setFont(QFont("Microsoft YaHei UI", self.base_font_size))
        self.question_label.setStyleSheet("color: #FFFFFF; border: none; background: transparent;")
        self.question_label.setWordWrap(True)
        self.question_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.question_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.content_layout.addWidget(self.question_label)

        self.answer_widget = QWidget()
        self.answer_widget.setStyleSheet("background: transparent; border: none;")
        self.answer_layout = QVBoxLayout(self.answer_widget)
        self.answer_layout.setContentsMargins(0, 0, 0, 0)
        self.answer_layout.setSpacing(6)
        self.content_layout.addWidget(self.answer_widget)

        self.result_label = QLabel("")
        self.result_label.setFont(QFont("Microsoft YaHei UI", self.base_font_size - 1))
        self.result_label.setMinimumHeight(28)
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.result_label.setStyleSheet("color: #BBBBBB; background: transparent; border: none;")
        self.result_label.setWordWrap(True)
        self.content_layout.addWidget(self.result_label)

        self.button_layout = QHBoxLayout()
        self.button_layout.setContentsMargins(0, 6, 0, 0)
        self.button_layout.setSpacing(8)
        self.button_layout.addStretch()
        self.layout.addLayout(self.button_layout)

        btn_font = QFont("Microsoft YaHei UI", max(self.base_font_size - 2, 10))

        self.submit_btn = QPushButton("提交")
        self.submit_btn.setFont(btn_font)
        self.submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.submit_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #4FC3F7;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 4px 14px;
            }
            QPushButton:hover { background-color: #63CDF8; }
            QPushButton:pressed { background-color: #3FB6EA; }
            QPushButton:disabled { background-color: #555555; color: #999999; }
            """
        )
        self.submit_btn.clicked.connect(self._submit_answer)
        self.button_layout.addWidget(self.submit_btn)

        self.close_btn = QPushButton("关闭")
        self.close_btn.setFont(btn_font)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #555555;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 4px 14px;
            }
            QPushButton:hover { background-color: #666666; }
            QPushButton:pressed { background-color: #474747; }
            """
        )
        self.close_btn.clicked.connect(self.close)
        self.button_layout.addWidget(self.close_btn)

        self._build_answer_area()

    def _sanitize_option_text(self, text: str) -> str:
        cleaned = re.sub(r"^\s*[A-Da-d][\.\):、]\s*", "", text or "")
        return cleaned.strip()

    def _build_answer_area(self):
        qtype = (self.question_type or "").lower()
        font_size = self.base_font_size

        title_map = {
            "choice": "选择题：请选出最恰当的选项",
            "fill": "填空题：请在下方补充缺少的单词",
            "qa": "问答题：请根据题目要求进行作答",
        }
        self.title_label.setText(title_map.get(qtype, "请回答以下问题"))
        self.question_label.setText(self.question_data.get("question", ""))

        if qtype == "choice":
            self.choice_group = QButtonGroup(self)
            self.option_buttons = []
            letters = ["A", "B", "C", "D"]
            options = self.question_data.get("options", [])

            for index in range(4):
                raw_text = options[index] if index < len(options) else ""
                option_text = self._sanitize_option_text(raw_text)

                radio = QRadioButton(f"{letters[index]}. {option_text}")
                radio.setFont(QFont("Microsoft YaHei UI", font_size))
                radio.setCursor(Qt.CursorShape.PointingHandCursor)
                radio.setStyleSheet(
                    """
                    QRadioButton {
                        color: #DDDDDD;
                        background-color: #333333;
                        border: 1px solid #333333;
                        border-radius: 6px;
                        padding: 8px 12px;
                    }
                    QRadioButton:hover {
                        background-color: #3a3a3a;
                    }
                    QRadioButton:checked {
                        color: #81D4FA;
                        background-color: #2a3a4a;
                        border: 1px solid #81D4FA;
                    }
                    QRadioButton::indicator {
                        width: 14px;
                        height: 14px;
                    }
                    """
                )

                self.choice_group.addButton(radio, index)
                self.option_buttons.append(radio)
                self.answer_layout.addWidget(radio)

        elif qtype == "qa":
            self.qa_input = QTextEdit()
            self.qa_input.setFont(QFont("Microsoft YaHei UI", font_size))
            self.qa_input.setPlaceholderText("在此输入您的答案...")
            self.qa_input.setMinimumHeight(84)
            self.qa_input.setStyleSheet(
                """
                QTextEdit {
                    background-color: #333333;
                    color: #FFFFFF;
                    border: 1px solid #555555;
                    border-radius: 6px;
                    padding: 8px;
                }
                QTextEdit:focus {
                    border: 1px solid #81D4FA;
                }
                """
            )
            self.answer_layout.addWidget(self.qa_input)

        else:
            self.fill_input = QLineEdit()
            self.fill_input.setFont(QFont("Microsoft YaHei UI", font_size))
            self.fill_input.setPlaceholderText("在此输入答案...")
            self.fill_input.setStyleSheet(
                """
                QLineEdit {
                    background-color: #333333;
                    color: #FFFFFF;
                    border: 1px solid #555555;
                    border-radius: 6px;
                    padding: 8px;
                }
                QLineEdit:focus {
                    border: 1px solid #81D4FA;
                }
                """
            )
            self.fill_input.returnPressed.connect(self._submit_answer)
            self.answer_layout.addWidget(self.fill_input)

        self.content_layout.addStretch(1)
        self._adjust_window_size()

    def _adjust_window_size(self):
        self.resize(self.CARD_WIDTH, self.MIN_HEIGHT)
        self.layout.activate()
        self.content_layout.activate()
        self.content_widget.adjustSize()
        QApplication.processEvents()

        desired_height = self.container.layout().sizeHint().height() + 2
        target_height = max(self.MIN_HEIGHT, min(self.MAX_HEIGHT, desired_height))
        self.resize(self.CARD_WIDTH, target_height)

        if desired_height > self.MAX_HEIGHT:
            self.content_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        else:
            self.content_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._center_on_screen()

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + (geo.height() - self.height()) // 2
        self.move(max(geo.x(), x), max(geo.y(), y))

    def _show_question(self):
        self._adjust_window_size()
        self.show()
        self.activateWindow()
        self.raise_()

        qtype = (self.question_type or "").lower()
        if qtype == "qa":
            self.qa_input.setFocus()
        elif qtype == "choice":
            if self.option_buttons:
                self.option_buttons[0].setFocus()
        else:
            self.fill_input.setFocus()
        print(f"[QuizCard] Showing question id={self.question_id}, type={qtype}")

    def _normalize(self, text):
        return (text or "").strip().lower()

    def _submit_answer(self):
        qtype = (self.question_type or "").lower()
        answered_time = datetime.now().strftime("%Y%m%d%H%M%S")
        user_answer = ""
        is_correct = None
        feedback = None

        if qtype == "choice":
            checked_id = self.choice_group.checkedId()
            if checked_id < 0:
                return

            letter = ["A", "B", "C", "D"][checked_id]
            user_answer = letter
            option_text = self.option_buttons[checked_id].text()
            clean_opt = self._sanitize_option_text(option_text.split(".", 1)[1] if "." in option_text else option_text)
            clean_ans = self._normalize(self.current_answer)
            is_correct = 1 if (
                self._normalize(letter) == clean_ans or self._normalize(clean_opt) == clean_ans
            ) else 0

        elif qtype == "qa":
            user_answer = self.qa_input.toPlainText().strip()
            if not user_answer:
                return
            is_correct = None

        else:
            user_answer = self.fill_input.text().strip()
            if not user_answer:
                return
            is_correct = 1 if self._normalize(user_answer) == self._normalize(self.current_answer) else 0

        try:
            self.db.update_answer(self.question_id, user_answer, is_correct, feedback, answered_time)
        except Exception as error:
            print(f"[QuizCard] DB update error: {error}")

        if qtype == "qa":
            self.result_label.setText("答案已记录，将在后续由 AI 批改")
            self.result_label.setStyleSheet(
                """
                QLabel {
                    color: #FFD54F;
                    background: transparent;
                    border: none;
                    padding: 2px 0px;
                }
                """
            )
        elif is_correct:
            self.result_label.setText("✅ 回答正确")
            self.result_label.setStyleSheet(
                """
                QLabel {
                    color: #4CAF50;
                    background: transparent;
                    border: none;
                    padding: 2px 0px;
                }
                """
            )
        else:
            self.result_label.setText(f"❌ 回答错误，正确答案是：{self.current_answer}")
            self.result_label.setStyleSheet(
                """
                QLabel {
                    color: #FF5252;
                    background: transparent;
                    border: none;
                    padding: 2px 0px;
                }
                """
            )

        self.submit_btn.setEnabled(False)
        if qtype == "choice":
            for button in self.option_buttons:
                button.setEnabled(False)
        elif qtype == "qa":
            self.qa_input.setEnabled(False)
        else:
            self.fill_input.setEnabled(False)

        self.content_scroll.verticalScrollBar().setValue(self.content_scroll.verticalScrollBar().maximum())
        print(f"[QuizCard] Answer submitted, id={self.question_id}, type={qtype}, correct={is_correct}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("[QuizCard] Usage: python quiz_card.py <question_id>")
        sys.exit(1)

    question_id = int(sys.argv[1])
    app = QApplication(sys.argv)
    card = QuizCard(question_id)
    sys.exit(app.exec())
