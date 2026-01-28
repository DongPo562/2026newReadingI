"""
audio_player.py - 音频播放器
包含: AudioPlayer
"""

import os
from PyQt6.QtCore import QObject, QUrl, QTimer, pyqtSignal
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices
from config_loader import app_config


class AudioPlayer(QObject):
    state_changed = pyqtSignal(QMediaPlayer.PlaybackState)

    def __init__(self):
        super().__init__()
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_devices = QMediaDevices()
        self.media_devices.audioOutputsChanged.connect(self._update_audio_output)
        self._update_audio_output()
        self.player.setAudioOutput(self.audio_output)
        self.current_number = None
        self.player.playbackStateChanged.connect(self._on_state_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.errorOccurred.connect(self._on_error)
        self.playback_queue = []
        self.current_queue_index = 0

    def _update_audio_output(self):
        default_device = QMediaDevices.defaultAudioOutput()
        self.audio_output.setDevice(default_device)

    def handle_play_request(self, number):
        if self.is_playing(number):
            if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.player.pause()
            elif self.player.playbackState() == QMediaPlayer.PlaybackState.PausedState:
                self.player.play()
            else:
                self.play(number)
        else:
            self.play(number)

    def play(self, number, clear_queue=True):
        self._update_audio_output()
        mode = app_config.play_last_mode
        new_sequence = self._get_sequence_for_number(number, mode)
        if clear_queue:
            self.player.stop()
            self.playback_queue = new_sequence
            self.current_queue_index = 0
            self.current_number = number
            self.play_next_in_queue()
        else:
            was_empty = len(self.playback_queue) == 0
            self.playback_queue.extend(new_sequence)
            if was_empty or self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self.play_next_in_queue()

    def auto_play(self, number):
        print(f"AutoPlay Recording completed, auto-playing: {number}")
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            print("AutoPlay Queued: waiting for current playback to finish")
            self.play(number, clear_queue=False)
        else:
            self.play(number, clear_queue=True)

    def _get_sequence_for_number(self, number, mode):
        audio_dir = app_config.save_dir
        base_path = os.path.join(audio_dir, f"{number}.wav")
        if mode == 'mode1':
            speeds = [0.5, 0.75]
            files = []
            for s in speeds:
                fpath = os.path.join(audio_dir, f"{number}@{s}.wav")
                if os.path.exists(fpath):
                    files.append(fpath)
            if os.path.exists(base_path):
                files.append(base_path)
            return files
        else:
            if os.path.exists(base_path):
                count = app_config.play_mode2_loop_count
                return [base_path] * count
            return []

    def play_next_in_queue(self):
        if self.current_queue_index < len(self.playback_queue):
            next_file = self.playback_queue[self.current_queue_index]
            self.current_queue_index += 1
            self.player.setSource(QUrl.fromLocalFile(next_file))
            self.audio_output.setVolume(1.0)
            self.player.play()
        else:
            self.stop()

    def toggle_playback(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        elif self.player.playbackState() == QMediaPlayer.PlaybackState.PausedState and self.current_number:
            self.player.play()
        elif self.current_number:
            self.play(self.current_number)

    def stop(self):
        self.player.stop()
        self.current_number = None
        self.playback_queue = []

    def _on_state_changed(self, state):
        self.state_changed.emit(state)

    def _on_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            QTimer.singleShot(100, self.play_next_in_queue)

    def _on_error(self):
        print(f"Player Error: {self.player.errorString()}")
        self.play_next_in_queue()

    def is_playing(self, number):
        return self.current_number == number