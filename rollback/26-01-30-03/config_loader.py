import configparser
import os

class Config:
    def init(self, config_path='config.ini'):
        self.config_path = config_path
        self.config = configparser.ConfigParser()
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")
        self.config.read(config_path)

try:
    current_dir = os.path.dirname(os.path.abspath(file))
    config_path = os.path.join(current_dir, 'config.ini')
    app_config = Config(config_path)
except Exception as e:
    print(f"Error loading config: {e}")
    app_config = None