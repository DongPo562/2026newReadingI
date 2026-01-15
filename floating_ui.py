import sys
import os
import time
import math
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QScrollArea, QFrame, QMenu, 
                             QGraphicsDropShadowEffect, QSizePolicy)
from PyQt6.QtCore import (Qt, QTimer, QPoint, QRect, QPropertyAnimation, 
                          QEasingCurve, pyqtSignal, QSize, QEvent, QUrl, QObject)
from PyQt6.QtGui import (QPainter, QColor, QBrush, QPen, QCursor, QLinearGradient, 
                         QPainterPath, QIcon, QAction, QRegion)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices
from config_loader import app_config

class AudioPlayer(QObject):
    state_changed = pyqtSignal(bool) # True if playing, False if stopped
    
    def __init__(self):
        super().__init__()
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        
        # Dynamic Device Switching
        self.media_devices = QMediaDevices()
        self.media_devices.audioOutputsChanged.connect(self._update_audio_output)
        self._update_audio_output() # Initial set
        
        self.player.setAudioOutput(self.audio_output)
        self.current_file = None
        self.player.playbackStateChanged.connect(self._on_state_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.errorOccurred.connect(self._on_error)
        
        # Playback Logic State
        self.playback_queue = [] # List of files to play
        self.current_queue_index = 0
        self.repeat_count = 0 # For Mode 2
        self.current_repeat = 0
        
    def _update_audio_output(self):
        default_device = QMediaDevices.defaultAudioOutput()
        self.audio_output.setDevice(default_device)
        # print(f"Audio Output Switched to: {default_device.description()}")

    def play(self, file_path):
        # Ensure correct device before playing
        self._update_audio_output()
        
        # Determine mode and setup queue
        mode = app_config.play_last_mode
        
        # Stop current if any
        self.player.stop()
        self.playback_queue = []
        self.current_queue_index = 0
        self.current_repeat = 0
        
        # Base logic: find variations
        # file_path is the 1.0x version (filtered list)
        # Parse filename to get parts
        dirname = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        
        # mental models are_2026-01-14.wav
        parts = filename.rsplit('_', 1)
        if len(parts) != 2:
            # Fallback normal play
            self.playback_queue = [file_path]
        else:
            text_part = parts[0]
            date_part = parts[1]
            
            if mode == 'mode1': # Progressive
                # 0.5, 0.75, 1.0
                speeds = [0.5, 0.75]
                files = []
                for s in speeds:
                    fname = f"{text_part}@{s}_{date_part}"
                    fpath = os.path.join(dirname, fname)
                    if os.path.exists(fpath):
                        files.append(fpath)
                files.append(file_path) # 1.0x
                
                # Loop 3 times? "自动循环播放 3 次" -> Means the sequence [0.5, 0.75, 1.0] plays 3 times?
                # Or just plays once? "三次播放的文件依次为...". Seems it means 1 cycle of 3 files.
                # "自动循环播放 3 次" usually means Play (Seq) -> Play (Seq) -> Play (Seq).
                # But description says:
                # "三次播放的文件依次为：第一次：0.5... 第二次：0.75... 第三次：1..."
                # This sounds like ONE sequence of 3 files. "Loop 3 times" might be confusing wording for "Play 3 variations".
                # Let's assume it plays the sequence [0.5, 0.75, 1.0] once.
                
                self.playback_queue = files
                
            else: # mode2 (Repeat)
                # Play 1.0x for N times
                count = app_config.play_mode2_loop_count
                self.playback_queue = [file_path] * count

        self.play_next_in_queue()

    def play_next_in_queue(self):
        if self.current_queue_index < len(self.playback_queue):
            next_file = self.playback_queue[self.current_queue_index]
            self.current_queue_index += 1
            
            self.current_file = next_file
            self.player.setSource(QUrl.fromLocalFile(next_file))
            self.audio_output.setVolume(1.0)
            self.player.play()
        else:
            self.stop()

    def toggle_playback(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        elif self.player.playbackState() == QMediaPlayer.PlaybackState.PausedState and self.current_file:
            self.player.play()
        elif self.current_file:
             self.player.play()

    def stop(self):
        self.player.stop()
        self.current_file = None
        self.playback_queue = []
        self.state_changed.emit(False) 

    def _on_state_changed(self, state):
        self.state_changed.emit(state == QMediaPlayer.PlaybackState.PlayingState)

    def _on_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            # Play next
            QTimer.singleShot(100, self.play_next_in_queue)
            
    def _on_error(self):
        print(f"Player Error: {self.player.errorString()}")
        # Skip to next
        self.play_next_in_queue()

    def is_playing(self, file_path):
        # Logic is tricky here because actual playing file might be a variant (0.5x)
        # But UI item represents the 1.0x file.
        # So we should check if current_file matches 1.0x OR is a variant of it.
        if not self.current_file: return False
        
        if self.current_file == file_path: return True
        
        # Check variant
        # file_path: name_date.wav
        # current: name@0.5_date.wav
        # Check if current starts with name and ends with date, and has @
        # Simplified: check if they share the same directory and base structure
        
        if os.path.dirname(file_path) != os.path.dirname(self.current_file):
            return False
            
        fname_orig = os.path.basename(file_path)
        fname_curr = os.path.basename(self.current_file)
        
        # If filtered list logic is strict (no @ in original), 
        # then variant must have @.
        if '@' not in fname_orig and '@' in fname_curr:
            # Check if removing @... matches
            # name@0.5_date -> name_date
            # Regex or split
            parts = fname_curr.rsplit('_', 1)
            if len(parts) == 2:
                text_part = parts[0].split('@')[0]
                date_part = parts[1]
                reconstructed = f"{text_part}_{date_part}"
                return reconstructed == fname_orig
                
        return False

class ModeSelector(QWidget):
    interaction = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.init_ui()
        self.update_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)
        
        # Mode 1 Button
        self.mode1_btn = QPushButton("Mode1")
        self.mode1_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode1_btn.clicked.connect(lambda: self.set_mode('mode1'))
        
        # Mode 2 Button
        self.mode2_btn = QPushButton("Mode2")
        self.mode2_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode2_btn.clicked.connect(lambda: self.set_mode('mode2'))
        
        # Loop Count Label (Clickable)
        self.loop_lbl = QPushButton(f"x{app_config.play_mode2_loop_count}")
        self.loop_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self.loop_lbl.setFixedWidth(30)
        self.loop_lbl.setStyleSheet("color: white; border: none; font-weight: bold;")
        self.loop_lbl.clicked.connect(self.toggle_loop_count)
        
        layout.addWidget(self.mode1_btn)
        layout.addWidget(self.mode2_btn)
        layout.addWidget(self.loop_lbl)
        layout.addStretch()

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
        
        # Visual feedback
        anim = QPropertyAnimation(self.loop_lbl, b"styleSheet")
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
            self.loop_lbl.setVisible(False)
        else:
            self.mode1_btn.setStyleSheet(inactive_style)
            self.mode2_btn.setStyleSheet(active_style)
            self.loop_lbl.setVisible(True)
            self.loop_lbl.setText(f"x{app_config.play_mode2_loop_count}")

class AudioListItem(QWidget):
    play_requested = pyqtSignal(str) 
    
    def __init__(self, file_path, player, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.player = player
        self.filename = os.path.basename(file_path)
        self.processed_name = self._process_filename(self.filename)
        
        self.init_ui()
        self.player.state_changed.connect(self.update_state)

    def _process_filename(self, filename):
        name_part = filename.split('_')[0]
        display_text = name_part
        if len(display_text) > app_config.ui_max_filename_chars:
            display_text = display_text[:app_config.ui_max_filename_chars] + "..."
        return display_text

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(app_config.ui_item_spacing)

        # Play Button
        self.play_btn = QPushButton()
        btn_size = app_config.ui_play_button_size
        self.play_btn.setFixedSize(btn_size, btn_size)
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.clicked.connect(self.on_play_click)

        layout.addWidget(self.play_btn)

        # Label
        self.label = QLabel(self.processed_name)
        self.label.setStyleSheet(f"font-size: {app_config.ui_font_size}px; color: {app_config.ui_text_color};")
        
        full_processed = self.filename.split('_')[0]
        self.label.setToolTip(full_processed)
        
        layout.addWidget(self.label)
        layout.addStretch()

        self.setStyleSheet("background-color: transparent;")
        self.update_icon(False)

    def update_icon(self, is_playing):
        btn_color = app_config.ui_play_button_color
        btn_size = app_config.ui_play_button_size
        radius = btn_size // 2
        font_size = max(10, btn_size // 2)

        if is_playing:
            self.play_btn.setText("II") 
            self.play_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #4CAF50;
                    border-radius: {radius}px;
                    color: white;
                    font-weight: bold;
                    font-size: {font_size}px;
                }}
            """)
        else:
            self.play_btn.setText("▶")
            self.play_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {btn_color};
                    border-radius: {radius}px;
                    color: white;
                    font-size: {font_size}px;
                    padding-left: 2px;
                }}
                QPushButton:hover {{
                    background-color: #4CAF50;
                }}
            """)

    def on_play_click(self):
        anim = QPropertyAnimation(self.play_btn, b"geometry")
        self.play_requested.emit(self.file_path)

    def update_state(self):
        # We need to periodically check because is_playing logic depends on current_file
        # which changes during sequence.
        # But state_changed only emits on Play/Stop/Pause transition.
        # When switching file in queue, it might Stop -> Play quickly.
        
        is_playing = self.player.is_playing(self.file_path)
        self.update_icon(is_playing)
        if is_playing:
            self.setStyleSheet("""
                QWidget {
                    background-color: rgba(0, 0, 0, 0.1);
                    border-left: 2px solid #4CAF50;
                }
            """)
        else:
            self.setStyleSheet("QWidget { background-color: transparent; border: none; }")

    def enterEvent(self, event):
        if not self.player.is_playing(self.file_path):
            self.setStyleSheet("background-color: rgba(255, 255, 255, 0.1);")
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.player.is_playing(self.file_path):
            self.setStyleSheet("background-color: transparent;")
        else:
             self.setStyleSheet("""
                QWidget {
                    background-color: rgba(0, 0, 0, 0.1);
                    border-left: 2px solid #4CAF50;
                }
            """)
        super().leaveEvent(event)
    
    def delete_file(self):
        try:
            if self.player.is_playing(self.file_path):
                self.player.stop()
            os.remove(self.file_path)
        except Exception as e:
            print(f"Error deleting file: {e}")

class ListPanel(QWidget):
    def __init__(self, player, ball_widget):
        super().__init__()
        self.player = player
        self.ball_widget = ball_widget 
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # Container for style
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
        
        # Mode Selector (Fixed at top)
        self.mode_selector = ModeSelector()
        if self.ball_widget:
            self.mode_selector.interaction.connect(self.ball_widget.raise_)
        self.container_layout.addWidget(self.mode_selector)
        
        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: rgba(255,255,255,0.1);")
        line.setFixedHeight(1)
        self.container_layout.addWidget(line)
        
        # Scroll Area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        # Disable Horizontal Scrollbar
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{
                width: {app_config.ui_scrollbar_width}px;
                background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255, 255, 255, 0.3);
                border-radius: 2px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
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
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_list)
        self.timer.start(app_config.ui_refresh_interval)
        
        self.last_files = []
        self.refresh_list()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self.player.toggle_playback()
            event.accept()
        else:
            super().keyPressEvent(event)

    def refresh_list(self):
        audio_dir = app_config.save_dir
        if not os.path.exists(audio_dir):
            self.clear_list()
            lbl = QLabel("暂无录音文件")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: #AAA; font-size: {app_config.ui_font_size}px;")
            self.scroll_layout.insertWidget(0, lbl)
            self.last_files = []
            return

        try:
            # Filter logic: exclude files with @0.5 or @0.75
            # Original files: name_date.wav
            # Variants: name@0.5_date.wav
            
            all_files = os.listdir(audio_dir)
            files = []
            for f in all_files:
                if not f.endswith('.wav'): continue
                if '@' in f: continue # Filter variants
                files.append(os.path.join(audio_dir, f))
                
            files.sort(key=os.path.getmtime, reverse=True)
        except Exception as e:
            print(f"Error refreshing list: {e}")
            return 
        
        if files == self.last_files:
            return
            
        self.last_files = files
        self.clear_list()
        
        if not files:
            lbl = QLabel("暂无录音文件")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: #AAA; font-size: {app_config.ui_font_size}px;")
            self.scroll_layout.insertWidget(0, lbl)
        else:
            for f in files:
                item = AudioListItem(f, self.player)
                item.play_requested.connect(self.on_play_requested)
                self.scroll_layout.insertWidget(self.scroll_layout.count()-1, item)
                
    def on_play_requested(self, file_path):
        self.player.play(file_path)
        if self.ball_widget:
            self.ball_widget.raise_()

    def clear_list(self):
        while self.scroll_layout.count() > 1:
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def leaveEvent(self, event):
        cursor_pos = QCursor.pos()
        if not self.ball_widget.geometry().contains(cursor_pos):
             self.ball_widget.collapse_panel()
        super().leaveEvent(event)
    
    def mousePressEvent(self, event):
        if self.ball_widget:
            self.ball_widget.raise_()
        super().mousePressEvent(event)

class FloatingBall(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.diameter = app_config.ui_ball_diameter
        self.setFixedSize(self.diameter, self.diameter)
        
        # Initial Position
        last_pos = app_config.ui_last_position
        if last_pos:
            self.move(last_pos[0], last_pos[1])
        else:
            screen_geo = QApplication.primaryScreen().geometry()
            # Middle-Right: x = width - diameter - 50, y = height/2
            self.move(screen_geo.width() - self.diameter - 50, (screen_geo.height() - self.diameter) // 2)
        
        self.dragging = False
        self.drag_position = QPoint()
        
        self.player = AudioPlayer()
        self.panel = ListPanel(self.player, self)
        
        self.anim = QPropertyAnimation(self.panel, b"geometry")
        self.anim.setDuration(app_config.ui_animation_duration)
        self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Gradient Background
        gradient = QLinearGradient(0, 0, self.diameter, self.diameter)
        gradient.setColorAt(0.0, QColor("#66BB6A")) 
        gradient.setColorAt(1.0, QColor("#43A047"))
        
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, self.diameter, self.diameter)
        
        # Ear Icon
        painter.setPen(QPen(QColor("white"), 2))
        path = QPainterPath()
        
        cx, cy = self.diameter / 2, self.diameter / 2
        s = self.diameter / 45.0
        
        path.moveTo(cx - 5*s, cy - 8*s)
        path.cubicTo(cx + 8*s, cy - 12*s, cx + 10*s, cy + 5*s, cx + 2*s, cy + 10*s)
        path.cubicTo(cx - 2*s, cy + 12*s, cx - 6*s, cy + 8*s, cx - 6*s, cy + 5*s)
        
        path.moveTo(cx - 2*s, cy - 4*s)
        path.cubicTo(cx + 3*s, cy - 4*s, cx + 4*s, cy + 2*s, cx + 1*s, cy + 4*s)
        
        painter.drawPath(path)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            self.raise_() 

    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() & Qt.MouseButton.LeftButton:
            new_pos = event.globalPosition().toPoint() - self.drag_position
            self.move(new_pos)
            
            if self.panel.isVisible():
                self.update_panel_position()
            
            self.raise_()
            event.accept()

    def mouseReleaseEvent(self, event):
        if self.dragging:
            self.dragging = False
            # Save position
            app_config.ui_last_position = (self.x(), self.y())

    def enterEvent(self, event):
        if not self.dragging:
            self.expand_panel()
        super().enterEvent(event)

    def leaveEvent(self, event):
        cursor_pos = QCursor.pos()
        if self.panel.isVisible():
            if not self.panel.geometry().contains(cursor_pos):
                self.collapse_panel()
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self.player.toggle_playback()
            event.accept()
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        refresh_action = QAction("刷新列表", self)
        refresh_action.triggered.connect(self.panel.refresh_list)
        exit_action = QAction("退出程序", self)
        exit_action.triggered.connect(QApplication.instance().quit)
        
        menu.addAction(refresh_action)
        menu.addAction(exit_action)
        menu.exec(event.globalPos())

    def expand_panel(self):
        if self.panel.isVisible():
            self.raise_()
            return
            
        target_width = app_config.ui_panel_width
        target_height = app_config.ui_panel_max_height # Fixed height as requested
        
        ball_geo = self.geometry()
        
        target_x = ball_geo.x() + self.diameter - target_width
        target_y = ball_geo.y() + self.diameter - target_height
        
        start_rect = QRect(ball_geo.x(), ball_geo.y(), self.diameter, self.diameter)
        end_rect = QRect(target_x, target_y, target_width, target_height)
        
        self.panel.setGeometry(start_rect)
        self.panel.show()
        
        self.anim.setStartValue(start_rect)
        self.anim.setEndValue(end_rect)
        self.anim.start()
        
        self.raise_()

    def collapse_panel(self):
        if not self.panel.isVisible():
            return
            
        ball_geo = self.geometry()
        start_rect = self.panel.geometry()
        end_rect = QRect(ball_geo.x(), ball_geo.y(), self.diameter, self.diameter)
        
        self.anim.setStartValue(start_rect)
        self.anim.setEndValue(end_rect)
        self.anim.finished.connect(self._on_collapse_finished)
        self.anim.start()
        self.raise_()

    def _on_collapse_finished(self):
        self.panel.hide()
        try:
            self.anim.finished.disconnect(self._on_collapse_finished)
        except:
            pass
        self.raise_()

    def update_panel_position(self):
        if self.panel.isVisible():
            target_width = self.panel.width()
            target_height = self.panel.height()
            ball_geo = self.geometry()
            target_x = ball_geo.x() + self.diameter - target_width
            target_y = ball_geo.y() + self.diameter - target_height
            self.panel.move(target_x, target_y)
            self.raise_() 

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FloatingBall()
    window.show()
    sys.exit(app.exec())
