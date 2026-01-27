import configparser
import os

class Config:
    def __init__(self, config_path='config.ini'):
        self.config_path = config_path
        self.config = configparser.ConfigParser()
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")
        self.config.read(config_path)

    def save(self):
        with open(self.config_path, 'w') as configfile:
            self.config.write(configfile)

    @property
    def start_silence_duration(self):
        return self.config.getfloat('Audio', 'start_silence_duration', fallback=6.0)

    @property
    def max_recording_duration(self):
        return self.config.getfloat('Audio', 'max_recording_duration', fallback=30.0)

    @property
    def silence_threshold_db(self):
        return self.config.getfloat('Audio', 'silence_threshold_db', fallback=-40.0)

    @property
    def end_silence_duration(self):
        return self.config.getfloat('Audio', 'end_silence_duration', fallback=1.5)

    @property
    def save_dir(self):
        return self.config.get('Paths', 'save_dir', fallback='audio')

    @property
    def ui_ball_diameter(self):
        return self.config.getint('UI', 'ball_diameter', fallback=45)

    @property
    def ui_panel_width(self):
        return self.config.getint('UI', 'panel_width', fallback=290)

    @property
    def ui_panel_max_height(self):
        return self.config.getint('UI', 'panel_max_height', fallback=400)

    @property
    def ui_opacity(self):
        return self.config.getfloat('UI', 'opacity', fallback=0.9)

    @property
    def ui_animation_duration(self):
        return self.config.getint('UI', 'animation_duration', fallback=250)

    @property
    def ui_font_size(self):
        return self.config.getint('UI', 'font_size', fallback=15)

    @property
    def ui_text_color(self):
        return self.config.get('UI', 'text_color', fallback='#FFFFFF')

    @property
    def ui_play_button_size(self):
        return self.config.getint('UI', 'play_button_size', fallback=24)

    @property
    def ui_play_button_color(self):
        return self.config.get('UI', 'play_button_color', fallback='#81D4FA')

    @property
    def ui_play_button_playing_color(self):
        return self.config.get('UI', 'play_button_playing_color', fallback='#4CAF50')

    @property
    def ui_play_button_paused_color(self):
        return self.config.get('UI', 'play_button_paused_color', fallback='#FF9800')

    @property
    def ui_item_playing_bg(self):
        return self.config.get('UI', 'item_playing_bg', fallback='rgba(0, 0, 0, 0.1)')

    @property
    def ui_item_paused_bg(self):
        return self.config.get('UI', 'item_paused_bg', fallback='rgba(255, 152, 0, 0.1)')

    @property
    def ui_max_filename_chars(self):
        return self.config.getint('UI', 'max_filename_chars', fallback=22)

    @property
    def ui_scrollbar_width(self):
        return self.config.getint('UI', 'scrollbar_width', fallback=4)

    @property
    def ui_item_spacing(self):
        return self.config.getint('UI', 'item_spacing', fallback=8)

    @property
    def ui_refresh_interval(self):
        return self.config.getint('UI', 'refresh_interval', fallback=2000)

    @property
    def ui_last_position(self):
        pos_str = self.config.get('UI', 'last_position', fallback='')
        if not pos_str:
            return None
        try:
            x, y = map(int, pos_str.split(','))
            return (x, y)
        except:
            return None

    @ui_last_position.setter
    def ui_last_position(self, value):
        if value and len(value) == 2:
            self.config.set('UI', 'last_position', f"{value[0]},{value[1]}")
            self.save()

    @property
    def ui_top_bar_spacing(self):
        return self.config.getint('UI', 'top_bar_spacing', fallback=10)

    @property
    def ui_mode_btn_width(self):
        return self.config.getint('UI', 'mode_btn_width', fallback=50)

    @property
    def ui_mode_btn_height(self):
        return self.config.getint('UI', 'mode_btn_height', fallback=26)

    @property
    def ui_loop_lbl_width(self):
        return self.config.getint('UI', 'loop_lbl_width', fallback=30)

    @property
    def ui_loop_lbl_height(self):
        return self.config.getint('UI', 'loop_lbl_height', fallback=26)

    @property
    def ui_toggle_width(self):
        return self.config.getint('UI', 'toggle_width', fallback=50)

    @property
    def ui_toggle_height(self):
        return self.config.getint('UI', 'toggle_height', fallback=26)

    @property
    def play_last_mode(self):
        return self.config.get('PlayMode', 'last_mode', fallback='mode2')

    @play_last_mode.setter
    def play_last_mode(self, value):
        self.config.set('PlayMode', 'last_mode', value)
        self.save()

    @property
    def play_mode2_loop_count(self):
        return self.config.getint('PlayMode', 'mode2_loop_count', fallback=3)

    @play_mode2_loop_count.setter
    def play_mode2_loop_count(self, value):
        self.config.set('PlayMode', 'mode2_loop_count', str(value))
        self.save()

    @property
    def play_auto_enabled(self):
        return self.config.getboolean('PlayMode', 'auto_enabled', fallback=False)

    @play_auto_enabled.setter
    def play_auto_enabled(self, value):
        self.config.set('PlayMode', 'auto_enabled', str(value))
        self.save()

    @property
    def slow_generate_versions(self):
        return self.config.getboolean('SlowAudio', 'generate_slow_versions', fallback=True)

    @property
    def slow_speeds(self):
        speeds_str = self.config.get('SlowAudio', 'slow_speeds', fallback='0.5, 0.75')
        try:
            return [float(s.strip()) for s in speeds_str.split(',')]
        except:
            return [0.5, 0.75]

    @property
    def game_min_text_length(self):
        return self.config.getint('WordGame', 'min_text_length', fallback=30)

    @property
    def game_clickable_text_color(self):
        return self.config.get('WordGame', 'clickable_text_color', fallback='#FFEB3B')

    @property
    def game_window_width(self):
        return self.config.getint('WordGame', 'game_window_width', fallback=400)

    @property
    def game_window_height(self):
        return self.config.getint('WordGame', 'game_window_height', fallback=500)

    @property
    def menu_bg_color(self):
        return self.config.get('ContextMenu', 'bg_color', fallback='#2b2b2b')

    @property
    def menu_text_color(self):
        return self.config.get('ContextMenu', 'text_color', fallback='#ffffff')

    @property
    def menu_border_color(self):
        return self.config.get('ContextMenu', 'border_color', fallback='#3d3d3d')

    @property
    def menu_hover_bg_color(self):
        return self.config.get('ContextMenu', 'hover_bg_color', fallback='#3d3d3d')

    @property
    def menu_font_size(self):
        return self.config.getint('ContextMenu', 'font_size', fallback=14)

    @property
    def date_row_height(self):
        return self.config.getint('DateFilter', 'date_row_height', fallback=30)

    @property
    def dropdown_width(self):
        return self.config.getint('DateFilter', 'dropdown_width', fallback=100)

    @property
    def dropdown_margin_left(self):
        return self.config.getint('DateFilter', 'dropdown_margin_left', fallback=10)

    @property
    def dropdown_margin_top(self):
        return self.config.getint('DateFilter', 'dropdown_margin_top', fallback=5)

    @property
    def empty_list_hint_text(self):
        return self.config.get('DateFilter', 'empty_list_hint_text', fallback='今天没有录音')

    @property
    def empty_list_hint_color(self):
        return self.config.get('DateFilter', 'empty_list_hint_color', fallback='#888888')

    @property
    def max_display_dates(self):
        return self.config.getint('DateFilter', 'max_display_dates', fallback=15)

    @property
    def cleanup_delay_seconds(self):
        return self.config.getint('Cleanup', 'cleanup_delay_seconds', fallback=60)

    @property
    def db_path(self):
        return self.config.get('Database', 'db_path', fallback='data.db')

    @property
    def db_wal_mode(self):
        return self.config.getboolean('Database', 'wal_mode', fallback=True)

    @property
    def db_busy_timeout(self):
        return self.config.getint('Database', 'busy_timeout', fallback=30000)

    @property
    def db_retry_count(self):
        return self.config.getint('Database', 'retry_count', fallback=3)

    @property
    def review_window_width(self):
        return self.config.getint('ReviewWindow', 'window_width', fallback=240)

    @property
    def review_window_height(self):
        return self.config.getint('ReviewWindow', 'window_height', fallback=140)

    @property
    def review_opacity(self):
        return self.config.getfloat('ReviewWindow', 'opacity', fallback=0.95)

    @property
    def review_font_size(self):
        return self.config.getint('ReviewWindow', 'font_size', fallback=18)

    @property
    def review_word_color(self):
        return self.config.get('ReviewWindow', 'word_color', fallback='#FFFFFF')

    @property
    def review_box_indicator_color(self):
        return self.config.get('ReviewWindow', 'box_indicator_color', fallback='#4A90D9')

    @property
    def review_last_position(self):
        try:
            x = self.config.get('ReviewWindow', 'last_position_x', fallback='')
            y = self.config.get('ReviewWindow', 'last_position_y', fallback='')
            if x and y:
                return (int(x), int(y))
            return None
        except:
            return None

    @review_last_position.setter
    def review_last_position(self, value):
        if value and len(value) == 2:
            self.config.set('ReviewWindow', 'last_position_x', str(value[0]))
            self.config.set('ReviewWindow', 'last_position_y', str(value[1]))
            self.save()

    @property
    def review_window_width(self) -> int:
        return self.config.getint('ReviewWindow.Layout', 'window_width', fallback=240)

    @property
    def review_window_height(self) -> int:
        return self.config.getint('ReviewWindow.Layout', 'window_height', fallback=140)

    @property
    def review_row1_height(self) -> int:
        return self.config.getint('ReviewWindow.Layout', 'row1_height', fallback=30)

    @property
    def review_row2_height(self) -> int:
        return self.config.getint('ReviewWindow.Layout', 'row2_height', fallback=20)

    @property
    def review_row3_height(self) -> int:
        return self.config.getint('ReviewWindow.Layout', 'row3_height', fallback=50)

    @property
    def review_row4_height(self) -> int:
        return self.config.getint('ReviewWindow.Layout', 'row4_height', fallback=40)

    @property
    def review_padding(self) -> tuple:
        left = self.config.getint('ReviewWindow.Layout', 'padding_left', fallback=12)
        right = self.config.getint('ReviewWindow.Layout', 'padding_right', fallback=12)
        top = self.config.getint('ReviewWindow.Layout', 'padding_top', fallback=8)
        bottom = self.config.getint('ReviewWindow.Layout', 'padding_bottom', fallback=8)
        return (left, top, right, bottom)

    @property
    def review_element_spacing(self) -> int:
        return self.config.getint('ReviewWindow.Layout', 'element_spacing', fallback=10)

    @property
    def review_play_btn_diameter(self) -> int:
        return self.config.getint('ReviewWindow.Layout', 'play_btn_diameter', fallback=28)

    @property
    def review_action_btn_size(self) -> tuple:
        w = self.config.getint('ReviewWindow.Layout', 'action_btn_width', fallback=80)
        h = self.config.getint('ReviewWindow.Layout', 'action_btn_height', fallback=32)
        return (w, h)

    @property
    def review_action_btn_spacing(self) -> int:
        return self.config.getint('ReviewWindow.Layout', 'action_btn_spacing', fallback=20)

    @property
    def review_toggle_size(self) -> tuple:
        w = self.config.getint('ReviewWindow.Layout', 'toggle_width', fallback=36)
        h = self.config.getint('ReviewWindow.Layout', 'toggle_height', fallback=18)
        return (w, h)

    @property
    def review_toggle_colors(self) -> dict:
        return {
            'off': self.config.get('ReviewWindow.Layout', 'toggle_off_color', fallback='#555555'),
            'on': self.config.get('ReviewWindow.Layout', 'toggle_on_color', fallback='#4A90D9'),
            'knob': self.config.get('ReviewWindow.Layout', 'toggle_knob_color', fallback='#FFFFFF')
        }

    @property
    def review_word_font_size_override(self) -> int:
        return self.config.getint('ReviewWindow.Layout', 'word_font_size_override', fallback=0)

    @property
    def review_auto_play_delay(self) -> float:
        return self.config.getfloat('ReviewWindow', 'auto_play_delay', fallback=1.0)

    # ==================== 阶段四：Leitner 盒子间隔配置 ====================
    @property
    def review_box_1_interval(self) -> int:
        return self.config.getint('ReviewWindow', 'box_1_interval', fallback=1)

    @property
    def review_box_2_interval(self) -> int:
        return self.config.getint('ReviewWindow', 'box_2_interval', fallback=2)

    @property
    def review_box_3_interval(self) -> int:
        return self.config.getint('ReviewWindow', 'box_3_interval', fallback=4)

    @property
    def review_box_4_interval(self) -> int:
        return self.config.getint('ReviewWindow', 'box_4_interval', fallback=7)

    @property
    def review_box_5_interval(self) -> int:
        return self.config.getint('ReviewWindow', 'box_5_interval', fallback=14)

    @property
    def review_max_box_level(self) -> int:
        return self.config.getint('ReviewWindow', 'max_box_level', fallback=5)

    @property
    def review_max_word_length(self) -> int:
        return self.config.getint('ReviewWindow', 'max_word_length', fallback=35)

    def get_box_interval(self, box_level):
        """根据盒子等级获取间隔天数"""
        intervals = {
            1: self.review_box_1_interval,
            2: self.review_box_2_interval,
            3: self.review_box_3_interval,
            4: self.review_box_4_interval,
            5: self.review_box_5_interval,
        }
        return intervals.get(box_level, 14)

try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, 'config.ini')
    app_config = Config(config_path)
except Exception as e:
    print(f"Error loading config: {e}")
    app_config = None