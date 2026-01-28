"""
word_game.py - 单词游戏窗口
包含: WordGameWindow, FlowLayout
"""

import random
import re
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QScrollArea, QFrame, QLayout, QSizePolicy, QApplication)
from PyQt6.QtCore import Qt, QRect, QPoint, QSize, QPropertyAnimation, pyqtProperty, QTimer
from config_loader import app_config


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, spacing=-1):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self.itemList = []

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self.itemList.append(item)

    def count(self):
        return len(self.itemList)

    def itemAt(self, index):
        if index >= 0 and index < len(self.itemList):
            return self.itemList[index]
        return None

    def takeAt(self, index):
        if index >= 0 and index < len(self.itemList):
            return self.itemList.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self._do_layout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self.itemList:
            size = size.expandedTo(item.minimumSize())
        size += QSize(2 * self.contentsMargins().top(), 2 * self.contentsMargins().top())
        return size

    def _do_layout(self, rect, test_only):
        x, y, line_height = rect.x(), rect.y(), 0
        spacing = self.spacing()
        for item in self.itemList:
            wid = item.widget()
            space_x = spacing + wid.style().layoutSpacing(QSizePolicy.ControlType.PushButton, QSizePolicy.ControlType.PushButton, Qt.Orientation.Horizontal)
            space_y = spacing + wid.style().layoutSpacing(QSizePolicy.ControlType.PushButton, QSizePolicy.ControlType.PushButton, Qt.Orientation.Vertical)
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x = next_x
            line_height = max(line_height, item.sizeHint().height())
        return y + line_height - rect.y()


class WordGameWindow(QWidget):
    def __init__(self, full_text, parent=None):
        super().__init__(parent)
        self.full_text = full_text
        self.tokens = self.tokenize(full_text)
        self.original_indices = list(range(len(self.tokens)))
        self.source_tokens = []
        self.target_tokens = []
        self.init_ui()
        self.start_game()

    def tokenize(self, text):
        pattern = r"(\w+'\w+|[\$]?\d+%?|\w+|-|[^\w\s])"
        raw_tokens = re.findall(pattern, text)
        return [t for t in raw_tokens if t.strip()]

    def start_game(self):
        indices = list(range(len(self.tokens)))
        n = len(indices)
        if n > 1:
            max_attempts = 100
            for _ in range(max_attempts):
                random.shuffle(indices)
                current_tokens = [self.tokens[i] for i in indices]
                if current_tokens != self.tokens:
                    break
            else:
                indices = indices[1:] + indices[:1]
        self.source_tokens = [(self.tokens[i], i) for i in indices]
        self.target_tokens = []
        self.refresh_ui()

    def init_ui(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(app_config.game_window_width, app_config.game_window_height)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        self.container = QFrame()
        self.container.setStyleSheet("""
            QFrame {
                background-color: rgba(40, 40, 40, 0.95);
                border-radius: 15px;
                border: 1px solid rgba(255, 255, 255, 0.2);
            }
        """)
        container_layout = QVBoxLayout(self.container)

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("单词还原句子游戏")
        title.setStyleSheet("color: white; font-weight: bold; font-size: 16px; border: none; background: transparent;")
        close_btn = QPushButton("×")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton { color: white; font-size: 20px; border: none; background: transparent; }
            QPushButton:hover { color: #FF5252; }
        """)
        close_btn.clicked.connect(self.close)
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(close_btn)
        container_layout.addLayout(header_layout)

        # Source area
        lbl_source = QLabel("待选区")
        lbl_source.setStyleSheet("color: #AAA; font-size: 12px; margin-top: 10px; border: none; background: transparent;")
        container_layout.addWidget(lbl_source)
        self.source_area = QWidget()
        self.source_area.setStyleSheet("background: rgba(0,0,0,0.2); border-radius: 8px;")
        self.source_layout = FlowLayout(self.source_area, margin=10, spacing=8)
        scroll_source = QScrollArea()
        scroll_source.setWidget(self.source_area)
        scroll_source.setWidgetResizable(True)
        scroll_source.setStyleSheet("background: transparent; border: none;")
        container_layout.addWidget(scroll_source, 1)

        # Target area
        lbl_target = QLabel("已选区")
        lbl_target.setStyleSheet("color: #AAA; font-size: 12px; margin-top: 10px; border: none; background: transparent;")
        container_layout.addWidget(lbl_target)
        self.target_area = QWidget()
        self.target_area.setStyleSheet("background: rgba(0,0,0,0.2); border-radius: 8px;")
        self.target_layout = FlowLayout(self.target_area, margin=10, spacing=8)
        scroll_target = QScrollArea()
        scroll_target.setWidget(self.target_area)
        scroll_target.setWidgetResizable(True)
        scroll_target.setStyleSheet("background: transparent; border: none;")
        container_layout.addWidget(scroll_target, 1)

        # Buttons
        btn_layout = QHBoxLayout()
        self.reset_btn = QPushButton("重置")
        self.reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_btn.setStyleSheet("""
            QPushButton { background-color: #757575; color: white; border-radius: 5px; padding: 8px 15px; border: none; }
            QPushButton:hover { background-color: #9E9E9E; }
        """)
        self.reset_btn.clicked.connect(self.start_game)
        self.confirm_btn = QPushButton("确认")
        self.confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.confirm_btn.setStyleSheet("""
            QPushButton { background-color: #4CAF50; color: white; border-radius: 5px; padding: 8px 15px; border: none; }
            QPushButton:hover { background-color: #66BB6A; }
        """)
        self.confirm_btn.clicked.connect(self.check_result)
        btn_layout.addStretch()
        btn_layout.addWidget(self.reset_btn)
        btn_layout.addWidget(self.confirm_btn)
        container_layout.addLayout(btn_layout)
        main_layout.addWidget(self.container)

        screen = QApplication.primaryScreen().geometry()
        self.move(screen.center() - self.rect().center())

    def create_token_btn(self, text, index, is_source):
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        style = """
            QPushButton {
                background-color: #2196F3;
                color: white;
                border-radius: 5px;
                padding: 5px 10px;
                border: none;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #42A5F5; }
        """
        if not is_source:
            style = """
                QPushButton {
                    background-color: #FF9800;
                    color: white;
                    border-radius: 5px;
                    padding: 5px 10px;
                    border: none;
                    font-size: 14px;
                }
                QPushButton:hover { background-color: #FFB74D; }
            """
        btn.setStyleSheet(style)
        btn.clicked.connect(lambda: self.on_token_click(index, is_source))
        return btn

    def refresh_ui(self):
        self.clear_layout(self.source_layout)
        self.clear_layout(self.target_layout)
        for idx, (txt, orig_idx) in enumerate(self.source_tokens):
            btn = self.create_token_btn(txt, idx, True)
            self.source_layout.addWidget(btn)
        for idx, (txt, orig_idx) in enumerate(self.target_tokens):
            btn = self.create_token_btn(txt, idx, False)
            self.target_layout.addWidget(btn)

    def clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def on_token_click(self, list_index, is_source):
        if is_source:
            if list_index < len(self.source_tokens):
                item = self.source_tokens.pop(list_index)
                self.target_tokens.append(item)
        else:
            if list_index < len(self.target_tokens):
                item = self.target_tokens.pop(list_index)
                self.source_tokens.append(item)
        self.refresh_ui()

    def check_result(self):
        if len(self.target_tokens) != len(self.tokens):
            self.show_feedback(False, "句子不完整！")
            return
        target_text_sequence = [txt for txt, _ in self.target_tokens]
        is_correct = (target_text_sequence == self.tokens)
        if is_correct:
            self.show_feedback(True, "回答正确！")
            QTimer.singleShot(1500, self.close)
        else:
            self.show_feedback(False, "顺序错误，请重试！")

    def show_feedback(self, is_success, message):
        color = "#4CAF50" if is_success else "#F44336"
        feedback = QLabel(message, self)
        feedback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        feedback.setStyleSheet(f"""
            background-color: {color}; 
            color: white; 
            padding: 10px 20px; 
            border-radius: 8px; 
            font-weight: bold;
            font-size: 16px;
        """)
        feedback.adjustSize()
        c_geo = self.container.geometry()
        x = c_geo.x() + (c_geo.width() - feedback.width()) // 2
        y = c_geo.y() + (c_geo.height() - feedback.height()) // 2
        feedback.move(x, y)
        feedback.show()
        feedback.raise_()
        anim = QPropertyAnimation(feedback, b"windowOpacity", self)
        anim.setDuration(1500)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(feedback.deleteLater)
        anim.start()