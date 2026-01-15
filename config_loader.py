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

    # UI Settings
    @property
    def ui_ball_diameter(self):
        return self.config.getint('UI', 'ball_diameter', fallback=45)

    @property
    def ui_panel_width(self):
        return self.config.getint('UI', 'panel_width', fallback=280)

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

    # PlayMode Settings
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

    # SlowAudio Settings
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

# Global instance
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, 'config.ini')
    app_config = Config(config_path)
except Exception as e:
    print(f"Error loading config: {e}")
    app_config = None
