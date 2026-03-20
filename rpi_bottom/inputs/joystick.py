"""Joystick Input Handler"""

try:
    import board
    import busio
    import digitalio
    from adafruit_mcp3xxx.mcp3008 import MCP3008
    from adafruit_mcp3xxx.analog_in import AnalogIn
    SPI_AVAILABLE = True
except ImportError:
    SPI_AVAILABLE = False

class JoystickInput:
    """Joystick input - MCP3008 analog"""
    
    def __init__(self, mode='analog'):
        self.mode = mode
        self.x_axis = 0.0
        self.y_axis = 0.0
        self.buttons = [False] * 12
           
        if mode == 'analog' and SPI_AVAILABLE:
            spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)
            cs = digitalio.DigitalInOut(board.D5)
            self.mcp = MCP3008(spi, cs)
            self.chan_x = AnalogIn(self.mcp, 0)
            self.chan_y = AnalogIn(self.mcp, 1)
            print("✓ Analog Joystick (MCP3008)")
        else:
            self.joystick = None
    
    def read(self):
        """Read joystick state"""
        if self.mode == 'analog':
            try:
                x_raw = self.chan_x.value
                y_raw = self.chan_y.value
                self.x_axis = (x_raw - 32768) / 32768.0
                self.y_axis = (y_raw - 32768) / 32768.0
                self.x_axis = max(-1.0, min(1.0, self.x_axis))
                self.y_axis = max(-1.0, min(1.0, self.y_axis))
                if abs(self.x_axis) < 0.05: self.x_axis = 0.0
                if abs(self.y_axis) < 0.05: self.y_axis = 0.0
            except:
                pass
        
        return {'x': self.x_axis, 'y': self.y_axis, 'buttons': self.buttons}
    
    