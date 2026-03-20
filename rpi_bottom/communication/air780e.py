"""Air780E SMS Module"""
import serial
import time

class Air780ESMS:
    """Air780E LTE module for SMS alerts"""
    
    def __init__(self, port, phone, baud=115200):
        self.port = port
        self.phone = phone
        self.enabled = True
        self.last_alert_time = {}
        self.cooldown = 300  # 5 minutes
        
        try:
            self.ser = serial.Serial(port, baud, timeout=5)
            time.sleep(1)
            self.ser.write(b'AT\r\n')
            time.sleep(0.5)
            resp = self.ser.read_all().decode('utf-8', errors='ignore')
            if 'OK' in resp:
                print(f"✓ Air780E on {port}")
            else:
                print(f"⚠️  Air780E no response")
        except:
            print(f"⚠️  Air780E not available")
            self.enabled = False
    
    def send_alert(self, alert_type, message):
        """Send SMS alert with cooldown"""
        if not self.enabled:
            return False
        
        # Check cooldown
        current_time = time.time()
        if alert_type in self.last_alert_time:
            if (current_time - self.last_alert_time[alert_type]) < self.cooldown:
                return False
        
        try:
            # Set text mode
            self.ser.write(b'AT+CMGF=1\r\n')
            time.sleep(0.5)
            self.ser.read_all()
            
            # Set recipient
            self.ser.write(f'AT+CMGS="{self.phone}"\r\n'.encode())
            time.sleep(1.0)
            
            # Send message
            self.ser.write(f'{alert_type}: {message}\x1A'.encode())
            time.sleep(3.0)
            
            self.last_alert_time[alert_type] = current_time
            print(f"✅ SMS sent: {alert_type}")
            return True
        except:
            return False
    
    def close(self):
        if self.enabled:
            self.ser.close()
