"""Pico USB Serial Input"""
import serial
import json
import time

class PicoInput:
    """Handle USB serial communication with Pico"""
    
    def __init__(self, port='/dev/ttyACM0', baud=115200):
        self.port = port
        self.baud = baud
        self.ser = None
        self.connected = False
    
    def connect(self):
        """Connect to Pico"""
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=1)
            time.sleep(2)
            # Test connection
            self.ser.write(b'PING\n')
            time.sleep(0.1)
            resp = self.ser.read_all().decode('utf-8', errors='ignore')
            if 'PONG' in resp:
                self.connected = True
                return True
        except Exception as e:
            print(f"Pico connection failed: {e}")
        return False
    
    def read_sensors(self):
        """Read all sensors from Pico"""
        if not self.connected:
            return None
        try:
            self.ser.write(b'GET_SENSORS\n')
            time.sleep(0.05)
            resp = self.ser.read_all().decode('utf-8', errors='ignore').strip()
            if resp:
                return json.loads(resp)
        except:
            pass
        return None
    
    def get_alerts(self):
        """Check for unsolicited alerts from Pico"""
        alerts = []
        if not self.connected:
            return alerts
        try:
            if self.ser.in_waiting > 0:
                lines = self.ser.read_all().decode('utf-8', errors='ignore').split('\n')
                for line in lines:
                    line = line.strip()
                    if line.startswith('{') and '"type":"alert"' in line:
                        alerts.append(json.loads(line))
        except:
            pass
        return alerts
    
    def set_motor(self, motor_id, speed):
        """Set motor speed"""
        if not self.connected:
            return False
        try:
            cmd = f'SET_MOTOR {motor_id} {speed}\n'
            self.ser.write(cmd.encode())
            return True
        except:
            return False
    
    def set_servo(self, servo_id, angle):
        """Set servo angle"""
        if not self.connected:
            return False
        try:
            cmd = f'SET_SERVO {servo_id} {angle}\n'
            self.ser.write(cmd.encode())
            return True
        except:
            return False
    
    def set_relay(self, relay_id, state):
        """Set relay state"""
        if not self.connected:
            return False
        try:
            state_str = 'on' if state else 'off'
            cmd = f'SET_RELAY {relay_id} {state_str}\n'
            self.ser.write(cmd.encode())
            return True
        except:
            return False
    
    def stop_all(self):
        """Emergency stop"""
        if not self.connected:
            return False
        try:
            self.ser.write(b'STOP_ALL\n')
            return True
        except:
            return False
    
    def close(self):
        """Close connection"""
        if self.ser:
            self.ser.close()
            self.connected = False
