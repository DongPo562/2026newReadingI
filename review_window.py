"""
review_window.py - Leitner复习窗口
包含: ReviewWindow, ReviewToggleSwitch
"""

import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStyleOption, QStyle)
from PyQt6.QtCore import Qt, QPoint, QTimer, QUrl
from PyQt6.QtGui import QPainter, QColor
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from config_loader import app_config
from style_manager import StyleManager
from widgets import ToggleSwitch
from text_processor import is_valid_word


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
        row1.addStretch()
        row1.addWidget(self.lbl_stats)
        row1.addStretch()
        row1.addWidget(self.btn_close)
        self.container1 = QWidget()
        self.container1.setObjectName("headerContainer")
        self.container1.setLayout(row1)
        main_layout.addWidget(self.container1)

        # Row 2: Word display
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
            self.lbl_word.setText("太棒了！没有需要复习的单词")
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
                QTimer.singleShot(500, self._replay_current)
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
        app_config.review_last_position = (self.x(), self.y())
        super().closeEvent(event)

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