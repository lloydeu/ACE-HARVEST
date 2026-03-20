"""
Configuration and State Management - RPi Top
"""

import json
import os

DEFAULT_CONFIG = {
    'pico_port': '/dev/ttyACM0',
    'pico_baud': 115200,
    'rpi_bottom_ip': '192.168.43.99',
    'tcp_port': 5002,
    'video_port': 5001,
    'camera_width': 1280,
    'camera_height': 720,
    'camera_fps': 30,
    'camera_bitrate': 2000000,
}

class Config:
    def __init__(self, config_file='/home/pi/.robot_top_config.json'):
        self.config_file = config_file
        self.config = self.load()
    
    def load(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    loaded = json.load(f)	
                    cfg = DEFAULT_CONFIG.copy()
                    cfg.update(loaded)
                    return cfg
            except:
                pass
        return DEFAULT_CONFIG.copy()
    
    def save(self):
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            return True
        except:
            return False
    
    def get(self, key, default=None):
        return self.config.get(key, default)
    
    def set(self, key, value):
        self.config[key] = value
        self.save()

state = {
    'pico_connected': False,
    'camera_streaming': False,
    'bottom_server_running': False,
    'emergency_stop': False,
    'sensors': {},
    'camera': {},
    'last_update': 0,
}

config = Config()
