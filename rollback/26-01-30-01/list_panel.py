"""
list_panel.py - 列表面板
包含: ListPanel, AudioListItem, DateFilterComboBox, ModeSelector
"""

import os
from datetime import datetime
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QComboBox, QMenu)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor, QAction
from PyQt6.QtMultimedia import QMediaPlayer
from config_loader import app_config
from widgets import ToggleSwitch, ClickableLabel
from ui_services import FileCleaner
from review_window import ReviewWindow


class DateFilterComboBox(QComboBox):
    def __init__(self, list_panel, parent=None):
        super().__init__(parent)
        self.list_panel = list_panel

    def showPopup(self):
        if hasattr(self.list_panel, 'is_date_menu_open'):
            self.list_panel.is_date_menu_open = True
        super().showPopup()

    def hidePopup(self):
        super().hidePopup()
        if hasattr(self.list_panel, 'is_date_menu_open'):
            self.list_panel.is_date_menu_open = False
        QTimer.singleShot(100, self._check_collapse)

    def _check_collapse(self):
        cursor_pos = QCursor.pos()
        if not self.list_panel.geometry().contains(cursor_pos) and \
            not self.list_panel.ball_widget.geometry().contains(cursor_pos):
                self.list_panel.ball_widget.collapse_panel()


class ModeSelector(QWidget):
    interaction = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.init_ui()
        self.update_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(app_config.ui_top_bar_spacing)
        self.mode1_btn = QPushButton("Mode1")
        self.mode1_btn.setFixedSize(app_config.ui_mode_btn_width, app_config.ui_mode_btn_height)
        self.mode1_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode1_btn.clicked.connect(lambda: self.set_mode('mode1'))
        self.mode2_btn = QPushButton("Mode2")
        self.mode2_btn.setFixedSize(app_config.ui_mode_btn_width, app_config.ui_mode_btn_height)
        self.mode2_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode2_btn.clicked.connect(lambda: self.set_mode('mode2'))
        self.loop_lbl = QPushButton(f"x{app_config.play_mode2_loop_count}")
        self.loop_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self.loop_lbl.setFixedSize(app_config.ui_loop_lbl_width, app_config.ui_loop_lbl_height)
        self.loop_lbl.setStyleSheet("color: white; border: none; font-weight: bold;")
        self.loop_lbl.clicked.connect(self.toggle_loop_count)
        self.auto_switch = ToggleSwitch(width=app_config.ui_toggle_width, height=app_config.ui_toggle_height)
        self.auto_switch.setChecked(app_config.play_auto_enabled)
        self.auto_switch.toggled.connect(self.on_auto_toggled)
        self.auto_switch.setToolTip("录音完成后自动播放")
        layout.addWidget(self.mode1_btn)
        layout.addWidget(self.mode2_btn)
        layout.addWidget(self.loop_lbl)
        layout.addWidget(self.auto_switch)
        layout.addStretch()

    def on_auto_toggled(self, checked):
        app_config.play_auto_enabled = checked
        self.interaction.emit()

    def set_mode(self, mode):
        app_config.play_last_mode = mode
        self.update_ui()
        self.interaction.emit()

    def toggle_loop_count(self):
        current = app_config.play_mode2_loop_count
        opts = [3, 5, 7]
        try:
            idx = opts.index(current)
            next_val = opts[(idx + 1) % len(opts)]
        except:
            next_val = 3
        app_config.play_mode2_loop_count = next_val
        self.loop_lbl.setText(f"x{next_val}")
        self.loop_lbl.setStyleSheet("color: #81D4FA; border: none; font-weight: bold;")
        QTimer.singleShot(200, lambda: self.loop_lbl.setStyleSheet("color: white; border: none; font-weight: bold;"))
        self.interaction.emit()

    def update_ui(self):
        mode = app_config.play_last_mode
        active_style = """
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border-radius: 5px;
                padding: 3px 8px;
                border: none;
            }
        """
        inactive_style = """
            QPushButton {
                background-color: rgba(255,255,255,0.2);
                color: #DDD;
                border-radius: 5px;
                padding: 3px 8px;
                border: none;
            }
            QPushButton:hover {
                background-color: rgba(255,255,255,0.3);
            }
        """
        if mode == 'mode1':
            self.mode1_btn.setStyleSheet(active_style)
            self.mode2_btn.setStyleSheet(inactive_style)
            self.loop_lbl.setVisible(True)
            self.loop_lbl.setEnabled(False)
            self.loop_lbl.setStyleSheet("color: gray; border: none; font-weight: bold;")
        else:
            self.mode1_btn.setStyleSheet(inactive_style)
            self.mode2_btn.setStyleSheet(active_style)
            self.loop_lbl.setVisible(True)
            self.loop_lbl.setEnabled(True)
            self.loop_lbl.setStyleSheet("color: white; border: none; font-weight: bold;")
        self.loop_lbl.setText(f"x{app_config.play_mode2_loop_count}")


class AudioListItem(QWidget):
    play_requested = pyqtSignal(int)
    game_requested = pyqtSignal(str)

    def __init__(self, recording_data, player, list_panel, parent=None):
        super().__init__(parent)
        self.data = recording_data
        self.number = recording_data['number']
        self.content = recording_data['content']
        self.player = player
        self.list_panel = list_panel
        self.is_playable = self._check_game_availability()
        self.init_ui()
        self.player.state_changed.connect(self.update_state)

    def _check_game_availability(self):
        if self.content and len(self.content) > app_config.game_min_text_length:
            return True
        return False

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(app_config.ui_item_spacing)
        self.play_btn = QPushButton()
        btn_size = app_config.ui_play_button_size
        self.play_btn.setFixedSize(btn_size, btn_size)
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.clicked.connect(self.on_play_click)
        layout.addWidget(self.play_btn)
        display_text = self.content
        if len(display_text) > app_config.ui_max_filename_chars:
            display_text = display_text[:app_config.ui_max_filename_chars] + "..."
        if self.is_playable:
            self.label = ClickableLabel(display_text)
            self.label.setCursor(Qt.CursorShape.PointingHandCursor)
            hl_color = app_config.game_clickable_text_color
            self.label.setStyleSheet(f"""
                QLabel {{
                    font-size: {app_config.ui_font_size}px;
                    color: {app_config.ui_text_color};
                }}
                QLabel:hover {{
                    color: {hl_color};
                }}
            """)
            self.label.clicked.connect(self.on_game_click)
        else:
            self.label = QLabel(display_text)
            self.label.setStyleSheet(f"font-size: {app_config.ui_font_size}px; color: {app_config.ui_text_color};")
        self.label.setToolTip(self.content)
        self.label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.label.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.label)
        layout.addStretch()
        self.setStyleSheet("background-color: transparent;")
        self.update_icon(False)

    def on_game_click(self):
        if self.content:
            self.game_requested.emit(self.content)

    def update_icon(self, state_str):
        btn_size = app_config.ui_play_button_size
        radius = btn_size // 2
        font_size = max(10, btn_size // 2)
        if state_str == "playing":
            self.play_btn.setText("II")
            color = app_config.ui_play_button_playing_color
            self.play_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    border-radius: {radius}px;
                    color: white;
                    font-weight: bold;
                    font-size: {font_size}px;
                }}
            """)
        elif state_str == "paused":
            self.play_btn.setText("▶")
            color = app_config.ui_play_button_paused_color
            self.play_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    border-radius: {radius}px;
                    color: white;
                    font-size: {font_size}px;
                    padding-left: 2px;
                }}
            """)
        else:
            self.play_btn.setText("▶")
            color = app_config.ui_play_button_color
            self.play_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    border-radius: {radius}px;
                    color: white;
                    font-size: {font_size}px;
                    padding-left: 2px;
                }}
                QPushButton:hover {{}}
            """)

    def on_play_click(self):
        self.play_requested.emit(self.number)

    def update_state(self, state=None):
        if state is None or isinstance(state, bool):
            state = self.player.player.playbackState()
        is_playing = self.player.is_playing(self.number)
        if is_playing:
            if state == QMediaPlayer.PlaybackState.PlayingState:
                self.update_icon("playing")
                self.setStyleSheet(f"""
                    QWidget {{
                        background-color: {app_config.ui_item_playing_bg};
                        border-left: 2px solid #4CAF50;
                    }}
                """)
            elif state == QMediaPlayer.PlaybackState.PausedState:
                self.update_icon("paused")
                self.setStyleSheet(f"""
                    QWidget {{
                        background-color: {app_config.ui_item_paused_bg};
                        border-left: 2px solid #FF9800;
                    }}
                """)
            else:
                self.update_icon("stopped")
                self.setStyleSheet("QWidget { background-color: transparent; border: none; }")
        else:
            self.update_icon("stopped")
            self.setStyleSheet("QWidget { background-color: transparent; border: none; }")

    def enterEvent(self, event):
        if not self.player.is_playing(self.number):
            self.setStyleSheet("background-color: rgba(255, 255, 255, 0.1);")
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.player.is_playing(self.number):
            self.setStyleSheet("background-color: transparent;")
        else:
            self.setStyleSheet(f"""
                QWidget {{
                    background-color: {app_config.ui_item_playing_bg};
                    border-left: 2px solid #4CAF50;
                }}
            """)
        super().leaveEvent(event)

    def show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {app_config.menu_bg_color};
                color: {app_config.menu_text_color};
                border: 1px solid {app_config.menu_border_color};
                font-size: {app_config.menu_font_size}px;
                padding: 5px;
            }}
            QMenu::item {{}}
            QMenu::item:selected {{
                background-color: {app_config.menu_hover_bg_color};
            }}
        """)
        del_action = QAction("删除", self)
        del_action.triggered.connect(self.delete_item)
        menu.addAction(del_action)
        self.list_panel.is_menu_open = True
        menu.aboutToHide.connect(lambda: setattr(self.list_panel, 'is_menu_open', False))
        menu.exec(self.label.mapToGlobal(pos))

    def delete_item(self):
        if self.player.is_playing(self.number):
            self.player.stop()
        deleted_number = self.number  # 保存被删除的 number
        try:
            self.list_panel.db_manager.delete_recording(self.number)
            print(f"[Delete] removed record number={self.number}")
            audio_dir = app_config.save_dir
            filename = f"{self.number}.wav"
            file_path = os.path.join(audio_dir, filename)
            files_to_delete = [file_path]
            for speed in ['0.5', '0.75']:
                variant_name = f"{self.number}@{speed}.wav"
                files_to_delete.append(os.path.join(audio_dir, variant_name))
            for fpath in files_to_delete:
                try:
                    if os.path.exists(fpath):
                        os.remove(fpath)
                except Exception as e:
                    print(f"[Delete] Warning: failed to delete file {os.path.basename(fpath)}, reason: {e}")
            self.list_panel.refresh_list(force_ui_update=True)
            # 阶段六：发射删除信号通知复习窗口
            self.list_panel.recording_deleted.emit(deleted_number)
        except Exception as e:
            print(f"[Delete] Error: {e}")


class ListPanel(QWidget):
    game_requested = pyqtSignal(str)
    recording_deleted = pyqtSignal(int)  # 阶段六：录音删除信号，传递被删除的 number

    def __init__(self, player, ball_widget, db_manager):
        super().__init__()
        self.player = player
        self.ball_widget = ball_widget
        self.db_manager = db_manager
        self.is_menu_open = False
        self.is_date_menu_open = False
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.container = QFrame()
        self.container.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(30, 30, 30, {app_config.ui_opacity});
                border-radius: 15px;
            }}
        """)
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(10, 10, 10, 10)
        self.container_layout.setSpacing(5)
        self.mode_selector = ModeSelector()
        if self.ball_widget:
            self.mode_selector.interaction.connect(self.ball_widget.raise_)
        self.container_layout.addWidget(self.mode_selector)

        # Date row
        self.date_row = QWidget()
        self.date_row.setFixedHeight(app_config.date_row_height)
        self.date_layout = QHBoxLayout(self.date_row)
        self.date_layout.setContentsMargins(app_config.dropdown_margin_left, app_config.dropdown_margin_top, 0, 0)
        self.date_layout.setSpacing(0)
        self.date_combo = DateFilterComboBox(self)
        self.date_combo.setFixedWidth(app_config.dropdown_width)
        self.date_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.date_combo.currentTextChanged.connect(self.on_date_changed)
        self.date_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: rgba(255, 255, 255, 0.1);
                color: {app_config.ui_text_color};
                border: none;
                border-radius: 4px;
                padding: 2px 5px;
                font-size: 13px;
            }}
            QComboBox::drop-down {{}}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid {app_config.ui_text_color};
                margin-right: 5px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {app_config.menu_bg_color};
                color: {app_config.menu_text_color};
                selection-background-color: {app_config.menu_hover_bg_color};
                border: 1px solid {app_config.menu_border_color};
            }}
        """)
        self.date_layout.addWidget(self.date_combo)
        self.btn_review = QPushButton("Review")
        self.btn_review.setFixedSize(60, 24)
        self.btn_review.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_review.setStyleSheet("""
            QPushButton {
                background-color: #9B59B6;
                color: white;
                border-radius: 4px;
                border: none;
                font-size: 12px;
                margin-left: 10px;
            }
            QPushButton:hover { background-color: #8E44AD; }
        """)
        self.btn_review.clicked.connect(self.open_review_window)
        self.date_layout.addWidget(self.btn_review)
        self.date_layout.addStretch()
        self.container_layout.addWidget(self.date_row)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: rgba(255,255,255,0.1);")
        line.setFixedHeight(1)
        self.container_layout.addWidget(line)

        # Scroll area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(f"""
            QScrollArea {{}}
            QScrollBar:vertical {{
                width: {app_config.ui_scrollbar_width}px;
                background: transparent;
            }}
            QScrollBar::handle:vertical {{}}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{}}
        """)
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent;")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setSpacing(2)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.addStretch()
        self.scroll.setWidget(self.scroll_content)
        self.container_layout.addWidget(self.scroll)
        self.layout.addWidget(self.container)
        self.first_load = True
        self.cleanup_thread = FileCleaner(self.db_manager, self)
        self.cleanup_thread.start()
        self.review_window = None
        self.refresh_list()

    def open_review_window(self):
        if not self.review_window:
            self.review_window = ReviewWindow(self.db_manager)
            # 阶段六：连接删除信号到复习窗口的刷新槽
            self.recording_deleted.connect(self.review_window.on_recording_deleted)
        self.review_window.show()
        self.review_window.raise_()
        self.review_window.activateWindow()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self.player.toggle_playback()
            event.accept()
        else:
            super().keyPressEvent(event)

    def on_date_changed(self, text):
        print(f"[DateFilter] Selected: {text}")
        self.refresh_list(force_ui_update=True)

    def refresh_list(self, force_ui_update=False):
        try:
            dates = self.db_manager.get_all_dates(app_config.max_display_dates)
            today_str = datetime.now().strftime("%Y-%m-%d")
            combo_items = []
            if today_str in dates:
                combo_items.append("Today")
            for d in dates:
                if d == today_str:
                    continue
                try:
                    dt = datetime.strptime(d, "%Y-%m-%d")
                    formatted = dt.strftime("%d/%m/%y")
                    combo_items.append(formatted)
                except:
                    pass
            if "Today" not in combo_items:
                combo_items.insert(0, "Today")
            self.date_combo.blockSignals(True)
            current_selection = self.date_combo.currentText()
            existing_items = [self.date_combo.itemText(i) for i in range(self.date_combo.count())]
            if combo_items != existing_items:
                self.date_combo.clear()
                self.date_combo.addItems(combo_items)
                if current_selection in combo_items:
                    self.date_combo.setCurrentText(current_selection)
                else:
                    self.date_combo.setCurrentIndex(0)
            self.date_combo.blockSignals(False)
            selected_text = self.date_combo.currentText()
            target_date_str = ""
            if selected_text == "Today":
                target_date_str = today_str
            else:
                try:
                    dt = datetime.strptime(selected_text, "%d/%m/%y")
                    target_date_str = dt.strftime("%Y-%m-%d")
                except:
                    pass
            recordings = self.db_manager.get_recordings_by_date(target_date_str)
            self.clear_list()
            if not recordings:
                lbl = QLabel(app_config.empty_list_hint_text)
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setStyleSheet(f"color: {app_config.empty_list_hint_color}; font-size: {app_config.ui_font_size}px;")
                self.scroll_layout.insertStretch(0)
                self.scroll_layout.insertWidget(1, lbl)
            else:
                for rec in recordings:
                    item = AudioListItem(rec, self.player, self)
                    item.play_requested.connect(self.on_play_requested)
                    item.game_requested.connect(self.game_requested.emit)
                    self.scroll_layout.insertWidget(self.scroll_layout.count()-1, item)
        except Exception as e:
            print(f"Error refreshing list: {e}")

    def on_auto_play_signal(self, message):
        """
        处理来自后台进程的录音完成通知
        
        Args:
            message: Socket 消息，格式为 "UPDATE" 或 "UPDATE:{number}"
        """
        print(f"[ListPanel] Socket received signal: {message}")
        self.refresh_list(force_ui_update=True)
        
        # 通知复习窗口有新单词加入（如果窗口已打开）
        if self.review_window and self.review_window.isVisible():
            self.review_window.on_new_word_added()
        
        if app_config.play_auto_enabled:
            # 切换到 Today 视图
            if self.date_combo.currentText() != "Today":
                self.date_combo.setCurrentText("Today")
                self.refresh_list(force_ui_update=True)
            
            # 解析消息中的 number
            target_number = None
            if ":" in message:
                try:
                    # 消息格式: "UPDATE:{number}"
                    parts = message.split(":")
                    if len(parts) >= 2:
                        target_number = int(parts[1])
                        print(f"[ListPanel] 解析到目标录音 number: {target_number}")
                except (ValueError, IndexError) as e:
                    print(f"[ListPanel] 解析 number 失败: {e}")
            
            # 自动播放指定的录音
            if target_number is not None:
                # 播放消息中指定的录音
                self.player.auto_play(target_number)
            else:
                # 兼容旧逻辑：如果没有指定 number，播放列表第一条
                today_str = datetime.now().strftime("%Y-%m-%d")
                recordings = self.db_manager.get_recordings_by_date(today_str)
                if recordings:
                    newest = recordings[0]
                    self.player.auto_play(newest['number'])

    def on_play_requested(self, number):
        self.player.handle_play_request(number)
        if self.ball_widget:
            self.ball_widget.raise_()

    def clear_list(self):
        while self.scroll_layout.count() > 1:
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def leaveEvent(self, event):
        cursor_pos = QCursor.pos()
        if self.is_menu_open or self.is_date_menu_open:
            super().leaveEvent(event)
            return
        if not self.ball_widget.geometry().contains(cursor_pos):
            self.ball_widget.collapse_panel()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if self.ball_widget:
            self.ball_widget.raise_()
        super().mousePressEvent(event)