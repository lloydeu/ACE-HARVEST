
import json
import os

# ========================================
# GPIO PIN ASSIGNMENTS
# ========================================

PIN_EMERGENCY_STOP = 17
PIN_BUTTON_START = 27
PIN_BUTTON_STOP = 22
PIN_BUTTON_WINCH_UP = 23
PIN_BUTTON_WINCH_DOWN = 24

PIN_WINCH_RELAY_FORWARD = 25
PIN_WINCH_RELAY_REVERSE = 8

PIN_LIQUID_LEVEL = 4

# MCP3008 SPI pins (default)
PIN_SPI_CS = 5

# ========================================
# NETWORK CONFIGURATION
# ========================================

DEFAULT_CONFIG = {
    'rpi_top_ip': '192.168.43.6',
    'rpi_top_port': 5002,
    'video_port': 5001,
    
    'alert_phone': '+639123456789',
    'alert_cooldown': 300,  # 5 minutes
    
    'display_width': 800,
    'display_height': 480,
    'display_overlay': True,
    'video_enabled': True,
    'video_quality': 'medium',
    
    'air780e_port': '/dev/ttyUSB0',
    'air780e_baud': 115200,
    
    'joystick_mode': 'analog',  # 'usb' or 'analog'
}

# ========================================
# CONFIGURATION MANAGER
# ========================================

class Config:
    """Persistent configuration storage"""
    
    def __init__(self, config_file='/home/pi/.robot_config.json'):
        self.config_file = config_file
        self.config = self.load()
    
    def load(self):
        """Load config from file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    loaded = json.load(f)
                    # Merge with defaults
                    cfg = DEFAULT_CONFIG.copy()
                    cfg.update(loaded)
                    return cfg
            except:
                pass
        return DEFAULT_CONFIG.copy()
    
    def save(self):
        """Save config to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            return True
        except:
            return False
    
    def get(self, key, default=None):
        """Get config value"""
        return self.config.get(key, default)
    
    def set(self, key, value):
        """Set config value"""
        self.config[key] = value
        self.save()

# ========================================
# GLOBAL STATE
# ========================================

state = {
    # System status
    'running': False,
    'emergency_stop': False,
    
    # Inputs
    'joystick_x': 0.0,
    'joystick_y': 0.0,
    'liquid_detected': False,
    
    # Outputs
    'winch_direction': 'stop',  # 'forward', 'reverse', 'stop'
    
    # Communication
    'top_connected': False,
    'telemetry': {},
    
    # Display
    'camera_active': False,
}

# Global config instance
config = Config()
