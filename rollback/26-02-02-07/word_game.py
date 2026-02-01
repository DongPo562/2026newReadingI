"""
word_game.py - 单词还原句子游戏窗口
优化版本：标点和数字固定在原位，用户只需选择单词
包含: WordGameWindow, FlowLayout, TokenButton
"""
import random
import re
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QScrollArea, QFrame, QLayout, QSizePolicy, QApplication,
    QGraphicsOpacityEffect)
from PyQt6.QtCore import (Qt, QRect, QPoint, QSize, QPropertyAnimation, 
    QTimer, QEasingCurve, QParallelAnimationGroup)
from PyQt6.QtGui import QCursor
from config_loader import app_config


class FlowLayout(QLayout):
    """自适应流式布局，用于单词按钮排列"""
    
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
        if 0 <= index < len(self.itemList):
            return self.itemList[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self.itemList):
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
            space_x = spacing + wid.style().layoutSpacing(
                QSizePolicy.ControlType.PushButton, 
                QSizePolicy.ControlType.PushButton, 
                Qt.Orientation.Horizontal
            )
            space_y = spacing + wid.style().layoutSpacing(
                QSizePolicy.ControlType.PushButton, 
                QSizePolicy.ControlType.PushButton, 
                Qt.Orientation.Vertical
            )
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
    """单词还原句子游戏窗口 - 优化版"""
    
    # 样式常量
    STYLES = {
        'container': """
            QFrame {
                background-color: rgba(35, 35, 40, 0.98);
                border-radius: 16px;
                border: 1px solid rgba(255, 255, 255, 0.15);
            }
        """,
        'title': """
            color: #FFFFFF; 
            font-weight: bold; 
            font-size: 18px; 
            border: none; 
            background: transparent;
        """,
        'close_btn': """
            QPushButton { 
                color: #888; 
                font-size: 22px; 
                font-weight: bold;
                border: none; 
                background: transparent; 
                border-radius: 15px;
            }
            QPushButton:hover { 
                color: #FF5252; 
                background: rgba(255, 82, 82, 0.15);
            }
        """,
        'section_label': """
            color: #888; 
            font-size: 13px; 
            font-weight: 500;
            margin-top: 8px; 
            border: none; 
            background: transparent;
        """,
        'area_widget': """
            background: rgba(0, 0, 0, 0.25); 
            border-radius: 10px;
        """,
        'scroll_area': """
            background: transparent; 
            border: none;
        """,
        'progress_label': """
            color: #4FC3F7; 
            font-size: 13px; 
            font-weight: 500;
            border: none; 
            background: transparent;
        """,
        'word_btn_source': """
            QPushButton {
                background-color: #2196F3;
                color: white;
                border-radius: 6px;
                padding: 8px 14px;
                border: none;
                font-size: 15px;
                font-weight: 500;
            }
            QPushButton:hover { 
                background-color: #42A5F5; 
            }
            QPushButton:pressed {
                background-color: #1976D2;
            }
        """,
        'word_btn_target': """
            QPushButton {
                background-color: #FF9800;
                color: white;
                border-radius: 6px;
                padding: 8px 14px;
                border: none;
                font-size: 15px;
                font-weight: 500;
            }
            QPushButton:hover { 
                background-color: #FFB74D; 
            }
            QPushButton:pressed {
                background-color: #F57C00;
            }
        """,
        'fixed_btn': """
            QPushButton {
                background-color: #424242;
                color: #9E9E9E;
                border: 1px dashed #616161;
                border-radius: 6px;
                padding: 8px 14px;
                font-size: 15px;
            }
        """,
        'placeholder_btn': """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.08);
                color: #616161;
                border: 2px dashed #4A4A4A;
                border-radius: 6px;
                padding: 8px 14px;
                font-size: 15px;
                min-width: 50px;
            }
        """,
        'reset_btn': """
            QPushButton { 
                background-color: #616161; 
                color: white; 
                border-radius: 6px; 
                padding: 10px 24px; 
                border: none;
                font-size: 14px;
                font-weight: 500;
            }
            QPushButton:hover { 
                background-color: #757575; 
            }
            QPushButton:pressed {
                background-color: #515151;
            }
        """,
        'confirm_btn': """
            QPushButton { 
                background-color: #4CAF50; 
                color: white; 
                border-radius: 6px; 
                padding: 10px 24px; 
                border: none;
                font-size: 14px;
                font-weight: 500;
            }
            QPushButton:hover { 
                background-color: #66BB6A; 
            }
            QPushButton:pressed {
                background-color: #43A047;
            }
        """,
    }

    def __init__(self, full_text, parent=None):
        super().__init__(parent)
        self.full_text = full_text
        self.tokens = self.tokenize(full_text)
        
        # 分类 token
        self.word_tokens = []        # [(token, original_index), ...] 可选单词
        self.fixed_positions = {}    # {original_index: token} 固定项（标点/数字）
        self.classify_tokens()
        
        # 游戏状态
        self.source_words = []       # 待选区的单词 [(token, original_index), ...]
        self.selected_words = []     # 已选区的单词 [(token, original_index), ...]
        
        # 拖动支持
        self._drag_pos = None
        
        self.init_ui()
        self.start_game()

    def tokenize(self, text):
        """将文本分词为 token 列表"""
        # 改进的正则：匹配单词（含缩写）、带符号的数字、单独标点
        pattern = r"(\w+'\w+|\$?\d+\.?\d*%?|\w+|[^\w\s])"
        raw_tokens = re.findall(pattern, text)
        return [t for t in raw_tokens if t.strip()]

    def is_word_token(self, token):
        """判断是否为可选单词（包含字母）"""
        return bool(re.search(r'[a-zA-Z]', token))

    def classify_tokens(self):
        """将 token 分类为可选词和固定项"""
        self.word_tokens = []
        self.fixed_positions = {}
        
        for i, token in enumerate(self.tokens):
            if self.is_word_token(token):
                self.word_tokens.append((token, i))
            else:
                self.fixed_positions[i] = token

    def start_game(self):
        """开始/重置游戏"""
        # 检查是否有足够的单词进行游戏
        if len(self.word_tokens) < 2:
            self.show_feedback(False, "句子太短，无法进行游戏")
            QTimer.singleShot(1500, self.close)
            return
        
        # 打乱单词顺序（确保与原顺序不同）
        shuffled_words = self.word_tokens.copy()
        n = len(shuffled_words)
        
        if n > 1:
            max_attempts = 100
            for _ in range(max_attempts):
                random.shuffle(shuffled_words)
                # 检查是否与原顺序不同
                if [w[0] for w in shuffled_words] != [w[0] for w in self.word_tokens]:
                    break
            else:
                # 如果随机打乱后仍然相同，手动调整
                shuffled_words = shuffled_words[1:] + shuffled_words[:1]
        
        self.source_words = shuffled_words
        self.selected_words = []
        self.refresh_ui()

    def init_ui(self):
        """初始化 UI"""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # 使用配置中的窗口尺寸（建议 550x650）
        width = getattr(app_config, 'game_window_width', 550)
        height = getattr(app_config, 'game_window_height', 650)
        self.setFixedSize(width, height)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        
        # 主容器
        self.container = QFrame()
        self.container.setStyleSheet(self.STYLES['container'])
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(20, 16, 20, 20)
        container_layout.setSpacing(12)

        # === 标题栏 ===
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        title = QLabel("单词还原句子游戏")
        title.setStyleSheet(self.STYLES['title'])
        
        close_btn = QPushButton("×")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(self.STYLES['close_btn'])
        close_btn.clicked.connect(self.close)
        
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(close_btn)
        container_layout.addLayout(header_layout)

        # === 待选区 ===
        source_header = QHBoxLayout()
        lbl_source = QLabel("待选区")
        lbl_source.setStyleSheet(self.STYLES['section_label'])
        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet(self.STYLES['progress_label'])
        source_header.addWidget(lbl_source)
        source_header.addStretch()
        source_header.addWidget(self.progress_label)
        container_layout.addLayout(source_header)
        
        self.source_area = QWidget()
        self.source_area.setStyleSheet(self.STYLES['area_widget'])
        self.source_layout = FlowLayout(self.source_area, margin=12, spacing=10)
        
        scroll_source = QScrollArea()
        scroll_source.setWidget(self.source_area)
        scroll_source.setWidgetResizable(True)
        scroll_source.setStyleSheet(self.STYLES['scroll_area'])
        scroll_source.setMinimumHeight(120)
        container_layout.addWidget(scroll_source, 2)

        # === 已选区 ===
        lbl_target = QLabel("已选区")
        lbl_target.setStyleSheet(self.STYLES['section_label'])
        container_layout.addWidget(lbl_target)
        
        self.target_area = QWidget()
        self.target_area.setStyleSheet(self.STYLES['area_widget'])
        self.target_layout = FlowLayout(self.target_area, margin=12, spacing=10)
        
        scroll_target = QScrollArea()
        scroll_target.setWidget(self.target_area)
        scroll_target.setWidgetResizable(True)
        scroll_target.setStyleSheet(self.STYLES['scroll_area'])
        scroll_target.setMinimumHeight(150)
        container_layout.addWidget(scroll_target, 3)

        # === 操作按钮 ===
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 8, 0, 0)
        
        self.reset_btn = QPushButton("重置")
        self.reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_btn.setStyleSheet(self.STYLES['reset_btn'])
        self.reset_btn.clicked.connect(self.start_game)
        
        self.confirm_btn = QPushButton("确认")
        self.confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.confirm_btn.setStyleSheet(self.STYLES['confirm_btn'])
        self.confirm_btn.clicked.connect(self.check_result)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.reset_btn)
        btn_layout.addSpacing(16)
        btn_layout.addWidget(self.confirm_btn)
        container_layout.addLayout(btn_layout)
        
        main_layout.addWidget(self.container)

        # 居中显示
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.center() - self.rect().center())

    def create_word_btn(self, text, index, is_source):
        """创建可点击的单词按钮"""
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            self.STYLES['word_btn_source'] if is_source 
            else self.STYLES['word_btn_target']
        )
        btn.clicked.connect(lambda: self.on_word_click(index, is_source))
        return btn

    def create_fixed_btn(self, text):
        """创建固定的标点/数字按钮（不可点击）"""
        btn = QPushButton(text)
        btn.setStyleSheet(self.STYLES['fixed_btn'])
        btn.setEnabled(False)
        btn.setCursor(Qt.CursorShape.ForbiddenCursor)
        return btn

    def create_placeholder_btn(self):
        """创建占位符按钮"""
        btn = QPushButton("___")
        btn.setStyleSheet(self.STYLES['placeholder_btn'])
        btn.setEnabled(False)
        return btn

    def refresh_ui(self):
        """刷新 UI 显示"""
        self.clear_layout(self.source_layout)
        self.clear_layout(self.target_layout)
        
        # 更新进度显示
        total_words = len(self.word_tokens)
        selected_count = len(self.selected_words)
        self.progress_label.setText(f"已选 {selected_count}/{total_words} 个单词")
        
        # === 待选区：只显示剩余的可选单词 ===
        for idx, (txt, orig_idx) in enumerate(self.source_words):
            btn = self.create_word_btn(txt, idx, True)
            self.source_layout.addWidget(btn)
        
        # === 已选区：按原句位置显示，包含固定项和占位符 ===
        self.build_target_area()
        
        # 强制更新布局
        self.source_area.adjustSize()
        self.target_area.adjustSize()

    def build_target_area(self):
        """构建已选区显示（包含固定项和占位符）"""
        total_positions = len(self.tokens)
        word_index = 0  # 跟踪已选单词的索引
        
        for pos in range(total_positions):
            if pos in self.fixed_positions:
                # 固定项（标点/数字）
                btn = self.create_fixed_btn(self.fixed_positions[pos])
                self.target_layout.addWidget(btn)
            else:
                # 单词位置
                if word_index < len(self.selected_words):
                    # 已选择的单词
                    txt, orig_idx = self.selected_words[word_index]
                    btn = self.create_word_btn(txt, word_index, False)
                    self.target_layout.addWidget(btn)
                else:
                    # 占位符
                    btn = self.create_placeholder_btn()
                    self.target_layout.addWidget(btn)
                word_index += 1

    def clear_layout(self, layout):
        """清空布局中的所有组件"""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def on_word_click(self, list_index, is_source):
        """处理单词点击事件"""
        if is_source:
            # 从待选区移到已选区
            if list_index < len(self.source_words):
                item = self.source_words.pop(list_index)
                self.selected_words.append(item)
        else:
            # 从已选区移回待选区
            if list_index < len(self.selected_words):
                item = self.selected_words.pop(list_index)
                self.source_words.append(item)
        
        self.refresh_ui()

    def check_result(self):
        """检查答案是否正确"""
        total_words = len(self.word_tokens)
        
        if len(self.selected_words) != total_words:
            remaining = total_words - len(self.selected_words)
            self.show_feedback(False, f"还有 {remaining} 个单词未选择！")
            return
        
        # 比对单词顺序
        user_sequence = [txt for txt, _ in self.selected_words]
        correct_sequence = [txt for txt, _ in self.word_tokens]
        
        is_correct = (user_sequence == correct_sequence)
        
        if is_correct:
            self.show_feedback(True, "🎉 回答正确！")
            QTimer.singleShot(1500, self.close)
        else:
            self.show_feedback(False, "顺序错误，请重试！")

    def show_feedback(self, is_success, message):
        """显示反馈信息"""
        color = "#4CAF50" if is_success else "#F44336"
        
        feedback = QLabel(message, self)
        feedback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        feedback.setStyleSheet(f"""
            background-color: {color}; 
            color: white; 
            padding: 14px 28px; 
            border-radius: 10px; 
            font-weight: bold;
            font-size: 17px;
        """)
        feedback.adjustSize()
        
        # 居中显示
        c_geo = self.container.geometry()
        x = c_geo.x() + (c_geo.width() - feedback.width()) // 2
        y = c_geo.y() + (c_geo.height() - feedback.height()) // 2
        feedback.move(x, y)
        feedback.show()
        feedback.raise_()
        
        # 添加透明度效果
        opacity_effect = QGraphicsOpacityEffect(feedback)
        feedback.setGraphicsEffect(opacity_effect)
        
        # 淡出动画
        anim = QPropertyAnimation(opacity_effect, b"opacity", self)
        anim.setDuration(1500)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.InQuad)
        anim.finished.connect(feedback.deleteLater)
        anim.start()

    # === 窗口拖动支持 ===
    def mousePressEvent(self, event):
        """鼠标按下事件 - 开始拖动"""
        if event.button() == Qt.MouseButton.LeftButton:
            # 只允许从标题栏区域拖动（顶部 60px）
            if event.position().y() < 60:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()

    def mouseMoveEvent(self, event):
        """鼠标移动事件 - 执行拖动"""
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        """鼠标释放事件 - 结束拖动"""
        self._drag_pos = None
        event.accept()