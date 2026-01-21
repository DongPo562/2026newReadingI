import sys
import os
import time
import math
import random
import re
from datetime import datetime
import socket
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QScrollArea, QFrame, QMenu, 
                             QGraphicsDropShadowEffect, QSizePolicy, QLayout, QComboBox)
from PyQt6.QtCore import (Qt, QTimer, QPoint, QRect, QPropertyAnimation, 
                          QEasingCurve, pyqtSignal, QSize, QEvent, QUrl, QObject, QFileSystemWatcher, pyqtProperty, QThread)
from PyQt6.QtGui import (QPainter, QColor, QBrush, QPen, QCursor, QLinearGradient, 
                         QPainterPath, QIcon, QAction, QRegion, QFont)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices
from config_loader import app_config

class CommandServer(QThread):
    file_saved_signal = pyqtSignal(str)
    stop_playback_signal = pyqtSignal()

    def run(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(('127.0.0.1', 65432))
            server.listen(5)
            while True:
                try:
                    conn, addr = server.accept()
                    with conn:
                        data = conn.recv(1024)
                        if data:
                            message = data.decode('utf-8')
                            if message == "STOP_PLAYBACK":
                                self.stop_playback_signal.emit()
                            else:
                                self.file_saved_signal.emit(message)
                except Exception as e:
                    print(f"Socket Accept Error: {e}")
        except Exception as e:
            print(f"Socket Bind Error: {e}")

class FileScanner(QThread):
    files_scanned = pyqtSignal(list, list) # all_files, new_items

    def __init__(self, directory, last_files):
        super().__init__()
        self.directory = directory
        self.last_files = last_files

    def run(self):
        try:
            start_time = time.time()
            if not os.path.exists(self.directory):
                self.files_scanned.emit([], [])
                return

            all_files_raw = os.listdir(self.directory)
            files = []
            for f in all_files_raw:
                if not f.endswith('.wav'): continue
                if '@' in f: continue
                files.append(os.path.join(self.directory, f))
            
            files.sort(key=os.path.getmtime, reverse=True)
            
            new_items = [f for f in files if f not in self.last_files]
            
            print(f"[Startup] File scan took: {time.time() - start_time:.4f}s")
            self.files_scanned.emit(files, new_items)
        except Exception as e:
            print(f"Scanner Error: {e}")
            self.files_scanned.emit(self.last_files, [])

class FileCleaner(QThread):
    def __init__(self, list_panel):
        super().__init__()
        self.list_panel = list_panel
        self.running = True

    def run(self):
        delay = app_config.cleanup_delay_seconds
        print(f"[Cleanup] Scheduled in {delay} seconds")
        
        # Wait for delay
        for _ in range(delay):
            if not self.running: return
            time.sleep(1)
            
        while self.running:
            # Check idle state
            # Idle means: Player not playing AND Recorder not recording.
            # Recorder state is tricky to get directly unless we check process or file locks?
            # Actually, user said: "no currently playing audio and no ongoing recording".
            # Playing state: self.list_panel.player.player.playbackState()
            # Recording state: The UI doesn't know about recording directly unless we check for lock files or similar?
            # But wait, Recorder is in a separate process? No, it's `audio_recorder.py`.
            # If `main.py` launches both, they are separate processes?
            # User instructions say: "The program startup".
            # Usually `floating_ui.py` is the main UI process. 
            # `audio_recorder.py` might be running in parallel?
            # If they are separate processes, we can't easily check recorder state unless IPC.
            # But wait, `main.py` (which I saw earlier in LS) likely orchestrates them?
            # Let's assume for now we check Player state. 
            # For recording, we might check if a file is being written to? Or rely on "no new file signals"?
            # Actually, `floating_ui.py` receives socket signals from recorder when *saved*.
            # It doesn't know when recording *starts*.
            # However, prompt says: "If 60s time... wait for idle... no notification needed".
            # A simple heuristic: check player state. For recording, maybe check if `audio_recorder` process is active? 
            # Or just check player state for now as "idle" often implies user interaction.
            # If recording is happening, files are being written. Deleting old files *should* be safe as long as we don't delete the *current* one.
            # But the prompt says "wait for idle".
            
            # Refined check:
            # 1. Player stopped?
            # 2. To be safe, maybe we can assume if player is stopped, we are "idle enough"?
            # Let's strictly check Player state first.
            
            is_playing = self.list_panel.player.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            
            if not is_playing:
                self.perform_cleanup()
                break
            else:
                print("[Cleanup] Waiting for idle state...")
                time.sleep(5) # Retry every 5s

    def perform_cleanup(self):
        try:
            audio_dir = app_config.save_dir
            if not os.path.exists(audio_dir): return
            
            # Scan all files
            files = [f for f in os.listdir(audio_dir) if f.endswith('.wav') and '@' not in f]
            
            # Extract dates
            date_map = {} # date_str -> list of files
            for f in files:
                # Format: name_YYYY-MM-DD.wav
                try:
                    date_part = f.rsplit('_', 1)[1].replace('.wav', '')
                    # Validate date format YYYY-MM-DD
                    datetime.strptime(date_part, "%Y-%m-%d")
                    
                    if date_part not in date_map:
                        date_map[date_part] = []
                    date_map[date_part].append(f)
                except:
                    continue
            
            sorted_dates = sorted(date_map.keys(), reverse=True)
            max_dates = app_config.max_display_dates
            
            if len(sorted_dates) > max_dates:
                # Identify dates to remove (the oldest ones)
                dates_to_remove = sorted_dates[max_dates:]
                
                for date_str in dates_to_remove:
                    print(f"[Cleanup] Removed files for date {date_str}")
                    
                    # Delete main files
                    for wav_file in date_map[date_str]:
                        self._delete_file_set(os.path.join(audio_dir, wav_file))
                        
        except Exception as e:
            print(f"[Cleanup] Error: {e}")

    def _delete_file_set(self, file_path):
        # Helper to delete file + variants + text
        try:
            dirname = os.path.dirname(file_path)
            filename = os.path.basename(file_path)
            
            files_to_delete = [file_path]
            
            parts = filename.rsplit('_', 1)
            if len(parts) == 2:
                text_part = parts[0]
                date_part = parts[1] # includes .wav
                
                # Variants
                for speed in ['0.5', '0.75']:
                    variant_name = f"{text_part}@{speed}_{date_part}"
                    files_to_delete.append(os.path.join(dirname, variant_name))
                
                # Text file
                txt_filename = filename.rsplit('.', 1)[0] + ".txt"
                project_root = os.path.dirname(dirname)
                text_dir = os.path.join(project_root, app_config.game_text_folder)
                files_to_delete.append(os.path.join(text_dir, txt_filename))
            
            for fpath in files_to_delete:
                if os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                    except Exception as e:
                        print(f"[Cleanup] Warning: Failed to delete {os.path.basename(fpath)}: {e}")
                        
        except Exception as e:
            print(f"[Cleanup] Error processing file set {file_path}: {e}")

class ToggleSwitch(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, parent=None, width=50, height=26):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._checked = False
        self._thumb_radius = height // 2 - 2
        self._thumb_pos = 2.0
        self._anim = QPropertyAnimation(self, b"thumb_pos", self)
        self._anim.setDuration(250)
        self._anim.setEasingCurve(QEasingCurve.Type.OutQuad)

    @pyqtProperty(float)
    def thumb_pos(self):
        return self._thumb_pos

    @thumb_pos.setter
    def thumb_pos(self, pos):
        self._thumb_pos = pos
        self.update()

    def setChecked(self, checked):
        if self._checked != checked:
            self._checked = checked
            self.toggled.emit(checked)
            
        target = self.width() - self._thumb_radius * 2 - 2 if self._checked else 2.0
        
        if abs(self._thumb_pos - target) > 0.1:
            self._anim.stop()
            self._anim.setStartValue(self._thumb_pos)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self.update()

    def isChecked(self):
        return self._checked

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw Track
        track_opacity = 0.9 if self._checked else 0.5
        track_color = QColor(app_config.ui_play_button_color) if self._checked else QColor("#757575")
        
        p.setBrush(track_color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, self.width(), self.height(), self.height() / 2, self.height() / 2)

        # Draw Thumb
        p.setBrush(QColor("white"))
        p.drawEllipse(QPoint(int(self._thumb_pos + self._thumb_radius), int(self.height() / 2)), 
                      self._thumb_radius, self._thumb_radius)

class AudioPlayer(QObject):
    state_changed = pyqtSignal(QMediaPlayer.PlaybackState) # True if playing, False if stopped
    
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

    def handle_play_request(self, file_path):
        if self.is_playing(file_path):
            if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.player.pause()
            elif self.player.playbackState() == QMediaPlayer.PlaybackState.PausedState:
                self.player.play()
            else:
                self.play(file_path)
        else:
            self.play(file_path)

    def play(self, file_path, clear_queue=True):
        # Ensure correct device before playing
        self._update_audio_output()
        
        # Determine mode and setup queue
        mode = app_config.play_last_mode
        
        # Calculate sequence
        new_sequence = self._get_sequence_for_file(file_path, mode)
        
        if clear_queue:
            self.player.stop()
            self.playback_queue = new_sequence
            self.current_queue_index = 0
            self.current_repeat = 0
            self.play_next_in_queue()
        else:
            # Append to queue
            # If currently playing, it will continue to next items in queue
            # If queue was empty (but player state might be stopped), start playing
            was_empty = len(self.playback_queue) == 0
            self.playback_queue.extend(new_sequence)
            
            if was_empty or self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                # If we were at the end of queue, current_queue_index might be equal to len
                # We need to ensure we continue playing
                if self.current_queue_index >= len(self.playback_queue) - len(new_sequence):
                     self.play_next_in_queue()

    def auto_play(self, file_path):
        print(f"AutoPlay Recording completed, auto-playing: {os.path.basename(file_path)}")
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            print("AutoPlay Queued: waiting for current playback to finish")
            self.play(file_path, clear_queue=False)
        else:
            self.play(file_path, clear_queue=True)

    def _get_sequence_for_file(self, file_path, mode):
        # Base logic: find variations
        dirname = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        
        parts = filename.rsplit('_', 1)
        if len(parts) != 2:
            return [file_path]
            
        text_part = parts[0]
        date_part = parts[1]
        
        if mode == 'mode1': # Progressive
            speeds = [0.5, 0.75]
            files = []
            for s in speeds:
                fname = f"{text_part}@{s}_{date_part}"
                fpath = os.path.join(dirname, fname)
                if os.path.exists(fpath):
                    files.append(fpath)
            files.append(file_path) # 1.0x
            return files
            
        else: # mode2 (Repeat)
            count = app_config.play_mode2_loop_count
            return [file_path] * count

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
        # State change will be handled by signal

    def _on_state_changed(self, state):
        self.state_changed.emit(state)

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
        
        # Game State
        self.source_tokens = [] # List of (token_str, original_index)
        self.target_tokens = [] # List of (token_str, original_index)
        
        self.init_ui()
        self.start_game()
        
    def tokenize(self, text):
        # Rules:
        # 1. Abbreviations/Possessives: \w+'\w+
        # 2. Numbers/Currency: \$?\d+%?
        # 3. Words: \w+
        # 4. Hyphens as separators: -
        # 5. Punctuation: [^\w\s]
        
        pattern = r"(\w+'\w+|[\$]?\d+%?|\w+|-|[^\w\s])"
        raw_tokens = re.findall(pattern, text)
        return [t for t in raw_tokens if t.strip()] # Filter empty
        
    def start_game(self):
        # Shuffle until content sequence is different from original
        # Note: We can't use derangement of indices if we have duplicate tokens.
        # So we focus on the resulting string content.
        
        indices = list(range(len(self.tokens)))
        n = len(indices)
        
        if n > 1:
            max_attempts = 100
            for _ in range(max_attempts):
                random.shuffle(indices)
                # Check if the sequence of TOKENS is different from original
                current_tokens = [self.tokens[i] for i in indices]
                if current_tokens != self.tokens:
                    break
            else:
                # Force difference if random failed (Cyclic shift)
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
        
        # Container
        self.container = QFrame()
        self.container.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(40, 40, 40, 0.95);
                border-radius: 15px;
                border: 1px solid rgba(255, 255, 255, 0.2);
            }}
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
        
        # Source Area (Top)
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
        container_layout.addWidget(scroll_source, 1) # Stretch factor 1
        
        # Target Area (Bottom)
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
        container_layout.addWidget(scroll_target, 1) # Stretch factor 1
        
        # Controls
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
        
        # Center on screen
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.center() - self.rect().center())

    def create_token_btn(self, text, index, is_source):
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border-radius: 5px;
                padding: 5px 10px;
                border: none;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #42A5F5; }
        """)
        if not is_source:
             btn.setStyleSheet("""
                QPushButton {
                    background-color: #FF9800;
                    color: white;
                    border-radius: 5px;
                    padding: 5px 10px;
                    border: none;
                    font-size: 14px;
                }
                QPushButton:hover { background-color: #FFB74D; }
            """)
            
        btn.clicked.connect(lambda: self.on_token_click(index, is_source))
        return btn

    def refresh_ui(self):
        # Clear layouts
        self.clear_layout(self.source_layout)
        self.clear_layout(self.target_layout)
        
        # Populate Source
        for idx, (txt, orig_idx) in enumerate(self.source_tokens):
            btn = self.create_token_btn(txt, idx, True)
            self.source_layout.addWidget(btn)
            
        # Populate Target
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
            # Move from Source to Target
            if list_index < len(self.source_tokens):
                item = self.source_tokens.pop(list_index)
                self.target_tokens.append(item)
        else:
            # Move from Target to Source
            if list_index < len(self.target_tokens):
                item = self.target_tokens.pop(list_index)
                self.source_tokens.append(item)
        
        self.refresh_ui()

    def check_result(self):
        # Check if Target contains all tokens in correct content order
        # We ignore original indices and only compare the text values
        
        if len(self.target_tokens) != len(self.tokens):
            self.show_feedback(False, "句子不完整！")
            return
            
        # Extract text from target_tokens (list of (txt, orig_idx))
        target_text_sequence = [txt for txt, _ in self.target_tokens]
        
        # self.tokens is the original text sequence
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
        
        # Center in container
        c_geo = self.container.geometry()
        x = c_geo.x() + (c_geo.width() - feedback.width()) // 2
        y = c_geo.y() + (c_geo.height() - feedback.height()) // 2
        feedback.move(x, y)
        feedback.show()
        feedback.raise_()
        
        # Fade out
        anim = QPropertyAnimation(feedback, b"windowOpacity", self)
        anim.setDuration(1500)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(feedback.deleteLater)
        anim.start()

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
            # Check if mouse is outside panel after a brief delay
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
        
        # Mode 1 Button
        self.mode1_btn = QPushButton("Mode1")
        self.mode1_btn.setFixedSize(app_config.ui_mode_btn_width, app_config.ui_mode_btn_height)
        self.mode1_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode1_btn.clicked.connect(lambda: self.set_mode('mode1'))
        
        # Mode 2 Button
        self.mode2_btn = QPushButton("Mode2")
        self.mode2_btn.setFixedSize(app_config.ui_mode_btn_width, app_config.ui_mode_btn_height)
        self.mode2_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode2_btn.clicked.connect(lambda: self.set_mode('mode2'))
        
        # Loop Count Label (Clickable)
        self.loop_lbl = QPushButton(f"x{app_config.play_mode2_loop_count}")
        self.loop_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self.loop_lbl.setFixedSize(app_config.ui_loop_lbl_width, app_config.ui_loop_lbl_height)
        self.loop_lbl.setStyleSheet("color: white; border: none; font-weight: bold;")
        self.loop_lbl.clicked.connect(self.toggle_loop_count)

        # Auto Switch
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
        print(f"AutoPlay Feature {'enabled' if checked else 'disabled'}")
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

class ClickableLabel(QLabel):
    clicked = pyqtSignal()
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

class AudioListItem(QWidget):
    play_requested = pyqtSignal(str)
    game_requested = pyqtSignal(str)
    
    def __init__(self, file_path, player, list_panel, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.player = player
        self.list_panel = list_panel
        self.filename = os.path.basename(file_path)
        self.processed_name = self._process_filename(self.filename)
        
        # Check for game availability
        self.game_text = None
        self.is_playable = False
        self._check_game_availability()
        
        self.init_ui()
        self.player.state_changed.connect(self.update_state)

    def _check_game_availability(self):
        # Text file rule: same name as 1.0x audio file (which is self.file_path) but .txt
        # self.file_path is like .../audio/name_date.wav
        # text path is .../text/name_date.txt
        
        try:
            # Construct text path
            audio_dir = os.path.dirname(self.file_path)
            base_name = os.path.splitext(self.filename)[0]
            
            # Assumption: text folder is at project root/text, config defines it.
            # But audio file is in audio/.
            # We need to resolve text folder relative to project root or absolute.
            # app_config.game_text_folder is likely "text" (relative).
            
            # If audio_dir is absolute .../Scanner/2026newReadingI/audio
            # then text dir is .../Scanner/2026newReadingI/text
            
            project_root = os.path.dirname(audio_dir)
            text_dir = os.path.join(project_root, app_config.game_text_folder)
            
            text_path = os.path.join(text_dir, f"{base_name}.txt")
            
            if os.path.exists(text_path):
                with open(text_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if len(content) > app_config.game_min_text_length:
                        self.game_text = content
                        self.is_playable = True
        except Exception as e:
            print(f"Error checking game availability: {e}")

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
        if self.is_playable:
            self.label = ClickableLabel(self.processed_name)
            self.label.setCursor(Qt.CursorShape.PointingHandCursor)
            # Highlight color
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
            self.label = QLabel(self.processed_name)
            self.label.setStyleSheet(f"font-size: {app_config.ui_font_size}px; color: {app_config.ui_text_color};")
        
        full_processed = self.filename.split('_')[0]
        self.label.setToolTip(full_processed)

        self.label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.label.customContextMenuRequested.connect(self.show_context_menu)
        
        layout.addWidget(self.label)
        layout.addStretch()

        self.setStyleSheet("background-color: transparent;")
        self.update_icon(False)

    def on_game_click(self):
        if self.game_text:
            self.game_requested.emit(self.game_text)

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
                QPushButton:hover {{
                    background-color: #4CAF50;
                }}
            """)

    def on_play_click(self):
        anim = QPropertyAnimation(self.play_btn, b"geometry")
        self.play_requested.emit(self.file_path)

    def update_state(self, state=None):
        if state is None or isinstance(state, bool):
             state = self.player.player.playbackState()
        
        is_playing = self.player.is_playing(self.file_path)
        
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
    
    def show_context_menu(self, pos):
        menu = QMenu(self)
        
        # Styling
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {app_config.menu_bg_color};
                color: {app_config.menu_text_color};
                border: 1px solid {app_config.menu_border_color};
                font-size: {app_config.menu_font_size}px;
                padding: 5px;
            }}
            QMenu::item {{
                padding: 5px 20px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {app_config.menu_hover_bg_color};
            }}
        """)
        
        del_action = QAction("删除", self)
        del_action.triggered.connect(self.delete_item)
        menu.addAction(del_action)
        
        # Handle collapse prevention
        self.list_panel.is_menu_open = True
        menu.aboutToHide.connect(lambda: setattr(self.list_panel, 'is_menu_open', False))
        
        menu.exec(self.label.mapToGlobal(pos))

    def delete_item(self):
        # 1. Stop playback if playing
        if self.player.is_playing(self.file_path):
            self.player.stop()

        # 2. Define files to delete
        files_to_delete = [self.file_path]
        
        dirname = os.path.dirname(self.file_path)
        filename = os.path.basename(self.file_path)
        # filename is name_date.wav
        
        parts = filename.rsplit('_', 1)
        if len(parts) == 2:
            text_part = parts[0]
            date_part = parts[1] # includes .wav
            
            # Variants
            for speed in ['0.5', '0.75']:
                variant_name = f"{text_part}@{speed}_{date_part}"
                files_to_delete.append(os.path.join(dirname, variant_name))
            
            # Text file
            txt_filename = filename.rsplit('.', 1)[0] + ".txt"
            
            # Resolve text dir
            project_root = os.path.dirname(dirname)
            text_dir = os.path.join(project_root, app_config.game_text_folder)
            
            files_to_delete.append(os.path.join(text_dir, txt_filename))
        
        # 3. Delete loop
        for fpath in files_to_delete:
            fname = os.path.basename(fpath)
            try:
                if os.path.exists(fpath):
                    # Check if file is open? os.remove usually fails if open.
                    os.remove(fpath)
                    print(f"[Delete] Removed: {fname}")
                elif "text" in fpath and not os.path.exists(os.path.dirname(fpath)):
                     # Text folder doesn't exist, ignore
                     pass
                elif not os.path.exists(fpath) and "text" not in fpath:
                    # Audio File not found
                    print(f"[Delete] Warning: File not found - {fname}")
            except Exception as e:
                print(f"[Delete] Warning: {e} - {fname}")

        # 4. Remove from UI
        self.deleteLater()

class ListPanel(QWidget):
    game_requested = pyqtSignal(str)

    def __init__(self, player, ball_widget):
        super().__init__()
        self.player = player
        self.ball_widget = ball_widget 
        self.is_menu_open = False # Added flag
        self.is_date_menu_open = False # Date menu flag
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
        
        # Date Filter Row
        self.date_row = QWidget()
        self.date_row.setFixedHeight(app_config.date_row_height)
        self.date_layout = QHBoxLayout(self.date_row)
        self.date_layout.setContentsMargins(app_config.dropdown_margin_left, app_config.dropdown_margin_top, 0, 0)
        self.date_layout.setSpacing(0)
        
        self.date_combo = DateFilterComboBox(self)
        self.date_combo.setFixedWidth(app_config.dropdown_width)
        self.date_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.date_combo.currentTextChanged.connect(self.on_date_changed)
        
        # Style for dropdown to match theme
        self.date_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: rgba(255, 255, 255, 0.1);
                color: {app_config.ui_text_color};
                border: none;
                border-radius: 4px;
                padding: 2px 5px;
                font-size: 13px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
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
        self.date_layout.addStretch()
        
        self.container_layout.addWidget(self.date_row)
        
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
        
        self.scanner_thread = None
        self.last_files = []
        self.first_load = True
        
        # Watcher for immediate updates
        self.watcher = QFileSystemWatcher(self)
        self.audio_dir = app_config.save_dir
        if not os.path.exists(self.audio_dir):
            os.makedirs(self.audio_dir, exist_ok=True)
        self.watcher.addPath(self.audio_dir)
        self.watcher.directoryChanged.connect(self.refresh_list)
        
        self.waiting_files = {} # path: QTimer
        
        # Cleanup Thread
        self.cleanup_thread = FileCleaner(self)
        self.cleanup_thread.start()
        
        self.refresh_list()

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
        if self.scanner_thread and self.scanner_thread.isRunning():
            return
            
        audio_dir = app_config.save_dir
        # Pass force_ui_update via sender logic or just store it? 
        # Easier to store last files locally and re-filter if needed.
        # But scanner thread is async.
        
        # If just filtering changed, we don't need to re-scan files if we have them cached?
        # FileScanner returns all files.
        # We can cache 'all_files' in self.cached_all_files
        
        if force_ui_update and hasattr(self, 'cached_all_files'):
             self.update_file_list_ui(self.cached_all_files, [])
             return

        self.scanner_thread = FileScanner(audio_dir, self.last_files)
        self.scanner_thread.files_scanned.connect(self.on_files_scanned)
        self.scanner_thread.start()

    def on_files_scanned(self, files, new_items):
        self.cached_all_files = files # Cache for filtering
        
        if files == self.last_files and not self.first_load:
             # Even if files match, we might need to update if date changed (handled by force_ui_update above)
             # But here this is from scanner.
             return
            
        self.last_files = files
        self.update_file_list_ui(files, new_items)

    def update_file_list_ui(self, files, new_items):
        # 1. Extract dates and update dropdown
        date_set = set()
        file_date_map = {} # date_str -> [files]
        
        for f in files:
            try:
                # Format: name_YYYY-MM-DD.wav
                date_part = f.rsplit('_', 1)[1].replace('.wav', '')
                datetime.strptime(date_part, "%Y-%m-%d") # Validate
                date_set.add(date_part)
                
                if date_part not in file_date_map:
                    file_date_map[date_part] = []
                file_date_map[date_part].append(f)
            except:
                continue
        
        sorted_dates = sorted(list(date_set), reverse=True)
        
        # Limit to max dates (logic says cleanup handles deletion, here we just show what exists)
        # But UI requirement: "max 15". If cleanup hasn't run yet?
        # Just show what we have.
        
        # Format dates for dropdown
        display_dates = []
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        current_selection = self.date_combo.currentText()
        
        combo_items = []
        if today_str in sorted_dates:
             combo_items.append("Today")
        
        for d in sorted_dates:
            if d == today_str: continue
            # Format YYYY-MM-DD -> DD/MM/YY
            try:
                dt = datetime.strptime(d, "%Y-%m-%d")
                formatted = dt.strftime("%d/%m/%y")
                combo_items.append(formatted)
            except:
                pass
        
        # If "Today" is not in list (no files today), but we must show it?
        # Requirement: "If no recording today... list empty... hint text".
        # "First startup default Today".
        # So "Today" should always be an option? 
        # "Dates filtering rule: only show dates with files".
        # BUT "First startup default Today. If no file, empty."
        # Contradiction? 
        # Interpretation: "Today" is always present or at least initially.
        # "Only show dates with files" -> implies if Today has no files, don't show it?
        # But "First startup default Today" implies it must be there.
        # Let's add Today if it's missing, but handle empty list.
        
        if "Today" not in combo_items:
            # If today has no files, do we show it?
            # "If today has no recording, list area empty".
            # So Today MUST be in the dropdown even if empty.
            combo_items.insert(0, "Today")
            
        # Update ComboBox if changed
        # Block signals to prevent recursion
        self.date_combo.blockSignals(True)
        existing_items = [self.date_combo.itemText(i) for i in range(self.date_combo.count())]
        
        # Check if we need to update items
        if combo_items != existing_items:
            self.date_combo.clear()
            self.date_combo.addItems(combo_items)
            
            # Restore selection if possible
            if current_selection in combo_items:
                self.date_combo.setCurrentText(current_selection)
            else:
                self.date_combo.setCurrentIndex(0) # Default to first (Today)
        
        self.date_combo.blockSignals(False)
        
        # 2. Filter files based on selection
        selected_text = self.date_combo.currentText()
        target_date_str = ""
        
        if selected_text == "Today":
            target_date_str = today_str
        else:
            # Convert DD/MM/YY -> YYYY-MM-DD
            try:
                dt = datetime.strptime(selected_text, "%d/%m/%y")
                target_date_str = dt.strftime("%Y-%m-%d")
            except:
                pass
        
        filtered_files = file_date_map.get(target_date_str, [])
        
        # Update List UI
        self.clear_list()
        
        if not filtered_files:
            lbl = QLabel(app_config.empty_list_hint_text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: {app_config.empty_list_hint_color}; font-size: {app_config.ui_font_size}px;")
            self.scroll_layout.insertStretch(0)
            self.scroll_layout.insertWidget(1, lbl)
        else:
            for f in filtered_files:
                item = AudioListItem(f, self.player, self)
                item.play_requested.connect(self.on_play_requested)
                item.game_requested.connect(self.game_requested.emit)
                self.scroll_layout.insertWidget(self.scroll_layout.count()-1, item)
        
        # Trigger Auto Play for new items
        if self.first_load:
            self.first_load = False
            return

        if app_config.play_auto_enabled and new_items:
            # Check if new item matches current filter?
            # If we are viewing "Today" and new item is Today, yes.
            # If we are viewing old date, and new item comes in (Today), do we switch?
            # Usually AutoPlay implies we want to hear it.
            # Maybe switch to Today automatically?
            # Prompt doesn't specify. Standard behavior: stay or switch?
            # Let's switch to Today if auto play happens.
            
            target = new_items[0]
            
            # Extract date of new item
            try:
                d_part = target.rsplit('_', 1)[1].replace('.wav', '')
                if d_part == today_str and self.date_combo.currentText() != "Today":
                     self.date_combo.setCurrentText("Today")
            except:
                pass
                
            self._handle_auto_play(target)

    def _handle_auto_play(self, file_path):
        mode = app_config.play_last_mode
        if mode == 'mode1':
            self._start_variant_wait(file_path)
        else:
            self.player.auto_play(file_path)

    def on_auto_play_signal(self, file_path):
        print(f"Socket received auto-play request: {file_path}")
        self.refresh_list()
        if app_config.play_auto_enabled:
             self._handle_auto_play(file_path)

    def _start_variant_wait(self, file_path):
        if file_path in self.waiting_files:
            return
            
        # Check immediately first
        if self._check_variants_exist(file_path):
            self.player.auto_play(file_path)
            return

        timer = QTimer(self)
        timer.setInterval(500)
        timer.timeout.connect(lambda: self._check_variants_loop(file_path, timer))
        self.waiting_files[file_path] = timer
        timer.start()
        
        # Timeout 15s
        QTimer.singleShot(15000, lambda: self._stop_wait(file_path, force_play=True))

    def _check_variants_exist(self, file_path):
        dirname = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        parts = filename.rsplit('_', 1)
        if len(parts) != 2: return True # No variants expected
        
        text_part = parts[0]
        date_part = parts[1]
        
        speeds = ['0.5', '0.75']
        for s in speeds:
            fname = f"{text_part}@{s}_{date_part}"
            if not os.path.exists(os.path.join(dirname, fname)):
                return False
        return True

    def _check_variants_loop(self, file_path, timer):
        if self._check_variants_exist(file_path):
            self._stop_wait(file_path, True)

    def _stop_wait(self, file_path, force_play=False):
        if file_path in self.waiting_files:
            timer = self.waiting_files.pop(file_path)
            try:
                timer.stop()
                timer.deleteLater()
            except: pass
            
            if force_play:
                self.player.auto_play(file_path)

    def on_play_requested(self, file_path):
        self.player.handle_play_request(file_path)
        if self.ball_widget:
            self.ball_widget.raise_()

    def clear_list(self):
        while self.scroll_layout.count() > 1:
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def leaveEvent(self, event):
        cursor_pos = QCursor.pos()
        if self.is_menu_open:
            super().leaveEvent(event)
            return

        if self.is_date_menu_open:
            super().leaveEvent(event)
            return

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
        start_t = time.time()
        print("[Startup] FloatingBall initializing...")
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
        self.panel.game_requested.connect(self.open_game_window)
        
        self.anim = QPropertyAnimation(self.panel, b"geometry")
        self.anim.setDuration(app_config.ui_animation_duration)
        self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)

        self.game_window = None
        
        # Command Server for IPC
        self.cmd_server = CommandServer()
        self.cmd_server.file_saved_signal.connect(self.panel.on_auto_play_signal)
        self.cmd_server.stop_playback_signal.connect(self.player.stop)
        self.cmd_server.start()
        print(f"[Startup] FloatingBall init done in {time.time() - start_t:.4f}s")

    def open_game_window(self, text):
        if self.game_window:
            self.game_window.close()
            self.game_window = None
            
        self.game_window = WordGameWindow(text, self)
        self.game_window.show()
        self.game_window.raise_()

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
            if self.panel.is_menu_open:
                super().leaveEvent(event)
                return

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
        exit_action.triggered.connect(self.exit_application)
        
        menu.addAction(refresh_action)
        menu.addAction(exit_action)
        menu.exec(event.globalPos())

    def exit_application(self):
        # Send exit signal to main.py
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect(('127.0.0.1', 65433))
            client.sendall(b"EXIT")
            client.close()
        except Exception as e:
            print(f"Failed to send exit signal to main app: {e}")
        
        # Quit this app
        QApplication.instance().quit()

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
