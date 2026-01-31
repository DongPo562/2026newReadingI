# -*- coding: utf-8 -*-
"""
review_window.py - Leitner复习窗口
包含: ReviewWindow, ReviewToggleSwitch
新增: 修饰键模拟功能 - 鼠标悬浮在单词区域时自动按下可配置的修饰键(默认Ctrl)
"""
import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStyleOption, QStyle)
from PyQt6.QtCore import Qt, QPoint, QTimer, QUrl, QEvent
from PyQt6.QtGui import QPainter, QColor
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from config_loader import app_config
from style_manager import StyleManager
from widgets import ToggleSwitch
from text_processor import is_valid_word

# 尝试导入 pynput，如果失败则使用 ctypes 作为备选
try:
    from pynput.keyboard import Key, Controller as KeyboardController
    PYNPUT_AVAILABLE = True
    # pynput 按键映射
    PYNPUT_KEY_MAP = {
        'alt': Key.alt_l,
        'ctrl': Key.ctrl_l,
        'shift': Key.shift_l,
    }
except ImportError:
    PYNPUT_AVAILABLE = False
    import ctypes
    # ctypes 虚拟键码映射
    CTYPES_KEY_MAP = {
        'alt': 0x12,    # VK_MENU
        'ctrl': 0x11,   # VK_CONTROL
        'shift': 0x10,  # VK_SHIFT
    }
    KEYEVENTF_KEYDOWN = 0x0000
    KEYEVENTF_KEYUP = 0x0002

# 按键显示名称映射
KEY_DISPLAY_NAMES = {
    'alt': 'Alt',
    'ctrl': 'Ctrl',
    'shift': 'Shift',
}

# 高亮动画持续时间（毫秒）
HIGHLIGHT_DURATION_MS = 1500
# 修饰键安全检查间隔（毫秒）
MODIFIER_SAFETY_CHECK_MS = 500

class ReviewToggleSwitch(ToggleSwitch):
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = app_config.review_toggle_colors
        track_color = QColor(colors['on']) if self._checked else QColor(colors['off'])
        p.setBrush(track_color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, self.width(), self.height(), self.height() / 2, self.height() / 2)
        p.setBrush(QColor(colors['knob']))
        p.drawEllipse(QPoint(int(self._thumb_pos + self._thumb_radius), int(self.height() / 2)),
            self._thumb_radius, self._thumb_radius)

class ReviewWindow(QWidget):
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        stylesheet = StyleManager.load_stylesheet('review_window.qss')
        self.setStyleSheet(stylesheet)
        self.resize(app_config.review_window_width, app_config.review_window_height)
        pos = app_config.review_last_position
        if pos:
            self.move(pos[0], pos[1])
        else:
            from PyQt6.QtWidgets import QApplication
            screen = QApplication.primaryScreen().geometry()
            self.move(screen.center() - self.rect().center())
        self.dragging = False
        self.drag_position = QPoint()
        self.words = self._load_words_to_review()
        self.current_index = 0
        self.loop_count = 1

        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)

        self.current_play_count = 0
        self.target_play_count = 1
        self.is_playing = False
        self.auto_play_timer = QTimer()
        self.auto_play_timer.setSingleShot(True)
        self.auto_play_timer.timeout.connect(self._do_auto_play)

        # 高亮动画定时器
        self.highlight_timer = QTimer()
        self.highlight_timer.setSingleShot(True)
        self.highlight_timer.timeout.connect(self._remove_highlight)

        # ========== 修饰键模拟功能 ==========
        self.modifier_pressed = False
        # 从配置读取修饰键类型
        self.modifier_key_name = app_config.review_hover_modifier_key
        if self.modifier_key_name not in KEY_DISPLAY_NAMES:
            self.modifier_key_name = 'ctrl'  # 默认使用 Ctrl
        self.modifier_display_name = KEY_DISPLAY_NAMES[self.modifier_key_name]
        
        if PYNPUT_AVAILABLE:
            self.keyboard = KeyboardController()
            self.modifier_key = PYNPUT_KEY_MAP.get(self.modifier_key_name, Key.ctrl_l)
        else:
            self.keyboard = None
            self.modifier_key = CTYPES_KEY_MAP.get(self.modifier_key_name, 0x11)

        # 修饰键安全定时器：防止修饰键卡住
        self.modifier_safety_timer = QTimer()
        self.modifier_safety_timer.timeout.connect(self._check_modifier_safety)
        self.modifier_safety_timer.start(MODIFIER_SAFETY_CHECK_MS)

        self.init_ui()
        self.update_content()

    def init_ui(self):
        self.cfg = app_config
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Row 1: Header
        row1 = QHBoxLayout()
        row1.setSpacing(0)
        row1.setContentsMargins(0, 0, 0, 0)
        lbl_auto = QLabel("Auto")
        lbl_auto.setObjectName("autoLabel")
        toggle_w, toggle_h = self.cfg.review_toggle_size
        self.toggle_auto = ReviewToggleSwitch(width=toggle_w, height=toggle_h)
        self.toggle_auto.setObjectName("toggleSwitch")
        self.btn_loop = QPushButton("x1")
        self.btn_loop.setObjectName("loopCountBtn")
        self.btn_loop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_loop.clicked.connect(self.toggle_loop)

        # 修饰键状态指示按钮（动态显示配置的按键名称）
        self.btn_modifier_status = QPushButton(self.modifier_display_name)
        self.btn_modifier_status.setObjectName("altStatusBtn")
        self.btn_modifier_status.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_modifier_status.clicked.connect(self._on_modifier_button_clicked)
        self.btn_modifier_status.setProperty("active", "false")
        self.btn_modifier_status.setToolTip(f"鼠标悬浮单词区时自动按下{self.modifier_display_name}\n点击可手动释放")

        self.lbl_stats = QLabel("待复习: 0 今日完成: 0")
        self.lbl_stats.setObjectName("statsLabel")
        self.lbl_stats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_close = QPushButton("×")
        self.btn_close.setObjectName("closeBtn")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.close)
        row1.addWidget(lbl_auto)
        row1.addWidget(self.toggle_auto)
        row1.addWidget(self.btn_loop)
        row1.addWidget(self.btn_modifier_status)  # 添加修饰键状态按钮
        row1.addStretch()
        row1.addWidget(self.lbl_stats)
        row1.addStretch()
        row1.addWidget(self.btn_close)
        self.container1 = QWidget()
        self.container1.setObjectName("headerContainer")
        self.container1.setLayout(row1)
        main_layout.addWidget(self.container1)

        # Row 2: Word display (修饰键触发区域)
        row2 = QHBoxLayout()
        row2.setSpacing(0)
        row2.setContentsMargins(0, 0, 0, 0)
        self.btn_play = QPushButton("▶")
        self.btn_play.setObjectName("playBtn")
        self.btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_play.clicked.connect(self.on_play)
        self.lbl_word = QLabel("")
        self.lbl_word.setObjectName("wordLabel")
        font_override = self.cfg.review_word_font_size_override
        if font_override > 0:
            self.lbl_word.setStyleSheet(f"font-size: {font_override}px;")
        row2.addStretch()
        row2.addWidget(self.btn_play)
        row2.addWidget(self.lbl_word)
        row2.addStretch()
        self.container2 = QWidget()
        self.container2.setObjectName("wordContainer")
        self.container2.setLayout(row2)
        self.container2.installEventFilter(self)  # 安装事件过滤器监听鼠标进入/离开
        self.container2.setMouseTracking(True)
        main_layout.addWidget(self.container2)

        # Row 3: Action buttons
        row3 = QHBoxLayout()
        row3.setSpacing(30)
        row3.setContentsMargins(0, 0, 0, 0)
        self.btn_forget = QPushButton("不记得")
        self.btn_forget.setObjectName("forgetBtn")
        self.btn_forget.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_forget.clicked.connect(self.on_forget)
        self.btn_remember = QPushButton("记得")
        self.btn_remember.setObjectName("rememberBtn")
        self.btn_remember.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remember.clicked.connect(self.on_remember)
        row3.addStretch()
        row3.addWidget(self.btn_forget)
        row3.addWidget(self.btn_remember)
        row3.addStretch()
        self.container3 = QWidget()
        self.container3.setObjectName("actionContainer")
        self.container3.setLayout(row3)
        main_layout.addWidget(self.container3)

        self.lbl_complete = QLabel("完成！")
        self.lbl_complete.setObjectName("completeLabel")
        self.lbl_complete.hide()

    # ========== 修饰键模拟相关方法 ==========
    def eventFilter(self, obj, event):
        """事件过滤器：只监听 container2（单词区）的鼠标进入/离开"""
        if obj == self.container2:
            if event.type() == QEvent.Type.Enter:
                self._press_modifier()
            elif event.type() == QEvent.Type.Leave:
                self._release_modifier()
        return super().eventFilter(obj, event)

    def _press_modifier(self):
        """模拟按下修饰键"""
        if not self.modifier_pressed:
            try:
                if PYNPUT_AVAILABLE and self.keyboard:
                    self.keyboard.press(self.modifier_key)
                else:
                    ctypes.windll.user32.keybd_event(self.modifier_key, 0, KEYEVENTF_KEYDOWN, 0)
                self.modifier_pressed = True
                self._update_modifier_button(True)
                print(f"[ReviewWindow] {self.modifier_display_name} 已按下 (进入单词区)")
            except Exception as e:
                print(f"[ReviewWindow] 按下 {self.modifier_display_name} 失败: {e}")

    def _release_modifier(self):
        """释放修饰键"""
        if self.modifier_pressed:
            try:
                if PYNPUT_AVAILABLE and self.keyboard:
                    self.keyboard.release(self.modifier_key)
                else:
                    ctypes.windll.user32.keybd_event(self.modifier_key, 0, KEYEVENTF_KEYUP, 0)
                self.modifier_pressed = False
                self._update_modifier_button(False)
                print(f"[ReviewWindow] {self.modifier_display_name} 已释放 (离开单词区)")
            except Exception as e:
                print(f"[ReviewWindow] 释放 {self.modifier_display_name} 失败: {e}")

    def _update_modifier_button(self, active):
        """更新修饰键状态按钮的显示"""
        self.btn_modifier_status.setProperty("active", "true" if active else "false")
        self.btn_modifier_status.style().unpolish(self.btn_modifier_status)
        self.btn_modifier_status.style().polish(self.btn_modifier_status)

    def _on_modifier_button_clicked(self):
        """点击修饰键按钮：强制释放修饰键"""
        if self.modifier_pressed:
            self._release_modifier()
            print(f"[ReviewWindow] {self.modifier_display_name} 已手动释放")

    def _check_modifier_safety(self):
        """安全检查：窗口不可见或鼠标不在单词区时，强制释放修饰键"""
        if self.modifier_pressed:
            should_release = False
            if not self.isVisible():
                should_release = True
            elif hasattr(self, 'container2') and not self.container2.underMouse():
                should_release = True
            if should_release:
                self._release_modifier()
                print(f"[Safety] {self.modifier_display_name} 键已自动释放")

    def paintEvent(self, event):
        opt = QStyleOption()
        opt.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt, p, self)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F5:
            self._reload_stylesheet()
            print("[ReviewWindow] 样式已重新加载")
        super().keyPressEvent(event)

    def _reload_stylesheet(self):
        stylesheet = StyleManager.reload_stylesheet('review_window.qss')
        self.setStyleSheet(stylesheet)

    def toggle_loop(self):
        modes = [1, 2, 3]
        idx = modes.index(self.loop_count)
        self.loop_count = modes[(idx + 1) % len(modes)]
        self.btn_loop.setText(f"x{self.loop_count}")

    def update_content(self):
        if self.current_index < len(self.words):
            word_data = self.words[self.current_index]
            self.lbl_word.setText(word_data['word'])
            self.lbl_stats.setText(f"待复习: {len(self.words) - self.current_index} 今日完成: {self.current_index}")
        else:
            self.lbl_word.setText("太棒了！复习完成")
            self.lbl_stats.setText(f"待复习: 0 今日完成: {len(self.words)}")
            self.btn_play.setEnabled(False)
            self.btn_remember.setEnabled(False)
            self.btn_forget.setEnabled(False)

    def on_remember(self):
        if self.current_index < len(self.words):
            self._stop_playback()
            word = self.words[self.current_index]['word']
            print(f"用户点击了记得按钮，当前单词：{word}")
            self.current_index += 1
            self.update_content()
            self._trigger_auto_play()

    def on_forget(self):
        if self.current_index < len(self.words):
            self._stop_playback()
            word = self.words[self.current_index]['word']
            print(f"用户点击了不记得按钮，当前单词：{word}")
            self.current_index += 1
            self.update_content()
            self._trigger_auto_play()

    def on_play(self):
        if self.current_index >= len(self.words):
            return
        word_data = self.words[self.current_index]
        number = word_data.get('number')
        if not number:
            print(f"[ReviewWindow] 单词 {word_data['word']} 没有对应的音频编号")
            return
        audio_path = os.path.join(app_config.save_dir, f"{number}.wav")
        if not os.path.exists(audio_path):
            print(f"[ReviewWindow] 音频文件不存在: {audio_path}")
            return
        self.target_play_count = self.loop_count
        self.current_play_count = 0
        self._play_audio(audio_path)

    def _play_audio(self, audio_path):
        self.player.setSource(QUrl.fromLocalFile(audio_path))
        self.audio_output.setVolume(1.0)
        self.player.play()
        self.is_playing = True
        self._update_play_button_state(True)

    def _on_playback_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.StoppedState:
            self.is_playing = False
            self._update_play_button_state(False)

    def _on_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.current_play_count += 1
            if self.current_play_count < self.target_play_count:
                QTimer.singleShot(app_config.review_loop_interval_ms, self._replay_current)
            else:
                self.is_playing = False
                self._update_play_button_state(False)

    def _replay_current(self):
        if self.current_index < len(self.words):
            word_data = self.words[self.current_index]
            number = word_data.get('number')
            if number:
                audio_path = os.path.join(app_config.save_dir, f"{number}.wav")
                if os.path.exists(audio_path):
                    self._play_audio(audio_path)

    def _trigger_auto_play(self):
        if self.toggle_auto.isChecked() and self.current_index < len(self.words):
            delay_ms = int(app_config.review_auto_play_delay * 1000)
            self.auto_play_timer.start(delay_ms)

    def _do_auto_play(self):
        if self.current_index < len(self.words):
            self.on_play()

    def _stop_playback(self):
        self.auto_play_timer.stop()
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.stop()
        self.is_playing = False
        self._update_play_button_state(False)

    def _update_play_button_state(self, is_playing):
        self.btn_play.setProperty("playing", "true" if is_playing else "false")
        self.btn_play.style().unpolish(self.btn_play)
        self.btn_play.style().polish(self.btn_play)
        if is_playing:
            self.btn_play.setText("II")
        else:
            self.btn_play.setText("▶")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.dragging = False

    def closeEvent(self, event):
        """窗口关闭时确保释放修饰键"""
        self._release_modifier()
        self.modifier_safety_timer.stop()
        app_config.review_last_position = (self.x(), self.y())
        super().closeEvent(event)

    def hideEvent(self, event):
        """窗口隐藏时确保释放修饰键"""
        self._release_modifier()
        super().hideEvent(event)

    def _load_words_to_review(self):
        try:
            records = self.db_manager.get_words_to_review()
            words = []
            for rec in records:
                content = rec['content']
                if is_valid_word(content):
                    words.append({
                        'word': content,
                        'number': rec['number'],
                        'box_level': rec['box_level'] or 1,
                        'remember': rec['remember'] or 0,
                        'forget': rec['forget'] or 0
                    })
            print(f"[ReviewWindow] 加载了 {len(words)} 个待复习单词")
            return words
        except Exception as e:
            print(f"[ReviewWindow] 加载单词失败: {e}")
            return []

    def on_recording_deleted(self, deleted_number):
        """当主界面删除录音时调用，刷新复习列表"""
        # 检查当前显示的单词是否被删除
        current_word_deleted = False
        if self.current_index < len(self.words):
            current_word = self.words[self.current_index]
            if current_word.get('number') == deleted_number:
                current_word_deleted = True
                self._stop_playback()
        # 重新加载待复习列表
        self.words = self._load_words_to_review()
        # 调整当前索引
        if current_word_deleted:
            # 当前单词被删除，保持索引不变（自动显示下一个）
            if self.current_index >= len(self.words):
                self.current_index = max(0, len(self.words) - 1)
        else:
            # 当前单词未被删除，需要找到它的新位置
            if self.current_index < len(self.words):
                pass  # 保持当前索引
            else:
                self.current_index = max(0, len(self.words) - 1)
        # 重新启用按钮（如果有单词可复习）
        if self.words:
            self.btn_play.setEnabled(True)
            self.btn_remember.setEnabled(True)
            self.btn_forget.setEnabled(True)
        # 更新显示
        self.update_content()
        print(f"[ReviewWindow] 录音 {deleted_number} 已删除，列表已刷新")

    def on_new_word_added(self):
        """
        当数据库新增单词时调用
        - 如果窗口未显示，不处理
        - 刷新单词列表，但保持当前复习进度
        - 触发统计数字高亮动画
        """
        # 如果窗口未显示，不处理
        if not self.isVisible():
            return
        # 保存当前正在复习的单词（用于保持进度）
        current_word_number = None
        if self.current_index < len(self.words):
            current_word_number = self.words[self.current_index].get('number')
        # 记录旧的待复习数量
        old_pending_count = len(self.words) - self.current_index
        # 重新加载待复习列表
        self.words = self._load_words_to_review()
        # 计算新的待复习数量
        new_pending_count = len(self.words)
        # 找到当前单词的新位置（保持复习进度）
        if current_word_number is not None:
            for i, word in enumerate(self.words):
                if word.get('number') == current_word_number:
                    self.current_index = i
                    break
            else:
                # 当前单词不在列表中（可能已完成复习），保持索引不变
                if self.current_index >= len(self.words):
                    self.current_index = max(0, len(self.words) - 1)
        # 重新启用按钮（如果有单词可复习）
        if self.words:
            self.btn_play.setEnabled(True)
            self.btn_remember.setEnabled(True)
            self.btn_forget.setEnabled(True)
        # 更新显示
        self.update_content()
        # 如果有新单词加入，触发高亮动画
        new_actual_pending = len(self.words) - self.current_index
        if new_actual_pending > old_pending_count:
            self._trigger_highlight()
            print(f"[ReviewWindow] 新单词已加入，待复习: {old_pending_count} -> {new_actual_pending}")
        else:
            print(f"[ReviewWindow] 列表已刷新，无新单词（可能是句子）")

    def _trigger_highlight(self):
        """触发统计标签高亮动画"""
        self.lbl_stats.setProperty("highlight", "true")
        self.lbl_stats.style().unpolish(self.lbl_stats)
        self.lbl_stats.style().polish(self.lbl_stats)
        self.highlight_timer.start(HIGHLIGHT_DURATION_MS)

    def _remove_highlight(self):
        """移除统计标签高亮"""
        self.lbl_stats.setProperty("highlight", "false")
        self.lbl_stats.style().unpolish(self.lbl_stats)
        self.lbl_stats.style().polish(self.lbl_stats)