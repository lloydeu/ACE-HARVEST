#!/usr/bin/env python3
"""
RPi4 Top - Pico Controller
Bidirectional communication with Pico for robot control
- Read sensor data
- Control motors and servos
- Receive alerts
"""

import serial
import json
import time
import threading
from queue import Queue
from typing import Optional, Dict, Callable

class PicoController:
    """
    Controller for Pico from RPi4 Top
    Handles bidirectional communication with the Pico assistant
    """
    
    def __init__(self, port='/dev/ttyACM0', baudrate=115200, alert_callback=None):
        """
        Initialize connection to Pico
        
        Args:
            port: Serial port (usually /dev/ttyACM0)
            baudrate: Serial baudrate (115200 default)
            alert_callback: Optional function to call when alerts received
                            Function signature: callback(alert_type, message, severity)
        """
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.alert_callback = alert_callback
        self.alert_queue = Queue()
        self.listener_thread = None
        self.listening = False
        
        # Connect to Pico
        self.connect()
        
        # Start background listener for unsolicited alerts
        if alert_callback:
            self.start_alert_listener()
    
    def connect(self):
        """Establish serial connection to Pico"""
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=2)
            time.sleep(2)  # Wait for connection to stabilize
            self.ser.reset_input_buffer()
            print(f"✓ Connected to Pico on {self.port}")
        except serial.SerialException as e:
            print(f"✗ Failed to connect to Pico: {e}")
            raise
    
    def send_command(self, command: str, timeout: float = 2.0) -> Optional[Dict]:
        """
        Send command and wait for response
        
        Args:
            command: Command string to send
            timeout: Response timeout in seconds
        
        Returns:
            Parsed JSON response or None if timeout
        """
        if not self.ser or not self.ser.is_open:
            print("⚠️  Serial port not open")
            return None
        
        # Clear any stale data
        self.ser.reset_input_buffer()
        
        # Send command
        self.ser.write(f"{command}\n".encode('utf-8'))
        self.ser.flush()
        
        # Wait for response
        start_time = time.time()
        while (time.time() - start_time) < timeout:
            if self.ser.in_waiting > 0:
                try:
                    line = self.ser.readline().decode('utf-8').strip()
                    if line:
                        data = json.loads(line)
                        
                        # Check if it's an alert (handle separately)
                        if data.get('type') == 'alert':
                            self._handle_alert(data)
                            continue  # Keep waiting for actual response
                        
                        return data
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    continue
            time.sleep(0.01)
        
        print(f"⚠️  Timeout waiting for response to: {command}")
        return None
    
    # ========== SENSOR READING METHODS ==========
    
    def get_state(self) -> Optional[Dict]:
        """Get full system state (sensors + actuators)"""
        return self.send_command("GET_STATE")
    
    def get_sensors(self) -> Optional[Dict]:
        """Get all sensor readings"""
        return self.send_command("GET_SENSORS")
    
    def get_pressure(self) -> Optional[float]:
        """Get pressure reading in kPa"""
        resp = self.send_command("GET_PRESSURE")
        return resp.get('pressure_kpa') if resp else None
    
    def get_current(self) -> Optional[tuple]:
        """Get current readings (amps_1, amps_2)"""
        resp = self.send_command("GET_CURRENT")
        if resp:
            return (resp.get('current_amps_1'), resp.get('current_amps_2'))
        return None
    
    def get_ph(self) -> Optional[float]:
        """Get pH level"""
        resp = self.send_command("GET_PH")
        return resp.get('ph_level') if resp else None
    
    # ========== MOTOR CONTROL METHODS ==========
    
    def set_motor(self, motor_id: str, speed: int) -> bool:
        """
        Set motor speed
        
        Args:
            motor_id: Motor identifier (linear_actuator, worm_gear_arm, etc.)
            speed: Speed -100 to 100 (negative = reverse)
        
        Returns:
            True if successful
        """
        speed = max(-100, min(100, speed))  # Clamp
        resp = self.send_command(f"SET_MOTOR {motor_id} {speed}")
        return resp and resp.get('status') == 'ok'
    
    def stop_motor(self, motor_id: str) -> bool:
        """Stop a specific motor"""
        return self.set_motor(motor_id, 0)
    
    def stop_all_motors(self) -> bool:
        """Emergency stop - kill all motors"""
        resp = self.send_command("STOP_ALL")
        return resp and resp.get('status') == 'ok'
    
    # ========== SERVO CONTROL METHODS ==========
    
    def set_servo(self, servo_id: str, angle: int) -> bool:
        """
        Set servo angle
        
        Args:
            servo_id: Servo identifier (mg996_1, sg90, etc.)
            angle: Angle 0-180 degrees
        
        Returns:
            True if successful
        """
        angle = max(0, min(180, angle))  # Clamp
        resp = self.send_command(f"SET_SERVO {servo_id} {angle}")
        return resp and resp.get('status') == 'ok'
    
    # ========== LIGHT CONTROL METHODS ==========
    
    def set_light(self, light_side: str, state: bool) -> bool:
        """
        Set light state
        
        Args:
            light_side: "left" or "right"
            state: True = ON, False = OFF
        
        Returns:
            True if successful
        """
        state_val = 'on' if state else 'off'
        resp = self.send_command(f"SET_LIGHT {light_side} {state_val}")
        return resp and resp.get('status') == 'ok'
    
    def set_left_light(self, state: bool) -> bool:
        """Turn left light ON/OFF"""
        return self.set_light("left", state)
    
    def set_right_light(self, state: bool) -> bool:
        """Turn right light ON/OFF"""
        return self.set_light("right", state)
    
    # ========== SYSTEM METHODS ==========
    
    def ping(self) -> Optional[Dict]:
        """Check if Pico is alive"""
        return self.send_command("PING")
    
    def get_status(self) -> Optional[Dict]:
        """Get quick system health status"""
        return self.send_command("GET_STATUS")
    
    def reset_error(self) -> bool:
        """Clear system error flag"""
        resp = self.send_command("RESET_ERROR")
        return resp and resp.get('status') == 'ok'
    
    # ========== ALERT HANDLING ==========
    
    def _handle_alert(self, alert_data: Dict):
        """Internal: Handle incoming alert"""
        alert_type = alert_data.get('alert_type', 'UNKNOWN')
        message = alert_data.get('message', '')
        severity = alert_data.get('severity', 'info')
        
        # Put in queue for background processing
        self.alert_queue.put(alert_data)
        
        # Call user callback if provided
        if self.alert_callback:
            self.alert_callback(alert_type, message, severity)
    
    def start_alert_listener(self):
        """Start background thread to listen for unsolicited alerts"""
        if self.listening:
            return
        
        self.listening = True
        self.listener_thread = threading.Thread(target=self._alert_listener_loop, daemon=True)
        self.listener_thread.start()
    
    def _alert_listener_loop(self):
        """Background loop for receiving alerts"""
        while self.listening:
            try:
                if self.ser.in_waiting > 0:
                    line = self.ser.readline().decode('utf-8').strip()
                    if line:
                        data = json.loads(line)
                        if data.get('type') == 'alert':
                            self._handle_alert(data)
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
            except Exception as e:
                print(f"Alert listener error: {e}")
            
            time.sleep(0.05)  # Check every 50ms
    
    def stop_alert_listener(self):
        """Stop background alert listener"""
        self.listening = False
        if self.listener_thread:
            self.listener_thread.join(timeout=1.0)
    
    # ========== CLEANUP ==========
    
    def close(self):
        """Close connection and cleanup"""
        self.stop_alert_listener()
        
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("✓ Pico connection closed")


# ========== EXAMPLE USAGE ==========

def example_alert_handler(alert_type, message, severity):
    """
    Example callback for handling alerts from Pico
    This runs in background thread when alerts arrive
    """
    icon = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "critical": "🚨"}.get(severity, "•")
    print(f"\n{icon} ALERT from Pico: [{alert_type}] {message}")
    
    # Example: Forward critical alerts to RPi4 Bottom via network
    if severity == "critical":
        # Send to RPi4 Bottom for user notification
        pass


if __name__ == "__main__":
    # Example: Control robot from RPi4 Top
    
    # Initialize with alert callback
    pico = PicoController(port='/dev/ttyACM0', alert_callback=example_alert_handler)
    
    try:
        # 1. Check connection
        print("\n1. Testing connection...")
        response = pico.ping()
        print(f"   Pico uptime: {response.get('uptime_ms')} ms")
        
        # 2. Read sensors
        print("\n2. Reading sensors...")
        sensors = pico.get_sensors()
        if sensors:
            print(f"   Pressure: {sensors['pressure_kpa']:.2f} kPa")
            print(f"   pH: {sensors['ph_level']:.2f}")
            print(f"   Current 1: {sensors['current_amps_1']:.2f} A")
            print(f"   Current 2: {sensors['current_amps_2']:.2f} A")
        
        # 3. Control actuators
        print("\n3. Controlling actuators...")
        
        # Move servo to 90 degrees
        print("   Moving mg996_1 servo to 90°...")
        pico.set_servo('mg996_1', 90)
        time.sleep(1)
        
        # Run motor at 50% speed
        print("   Running linear_actuator at 50% speed...")
        pico.set_motor('linear_actuator', 50)
        time.sleep(2)
        
        # Stop motor
        print("   Stopping motor...")
        pico.stop_motor('linear_actuator')
        
        # 4. Turn on relay
        print("\n4. Controlling relay...")
        pico.set_relay(1, True)
        time.sleep(1)
        pico.set_relay(1, False)
        
        # 5. Monitor in real-time (example loop)
        print("\n5. Monitoring (Ctrl+C to stop)...")
        try:
            while True:
                pressure = pico.get_pressure()
                print(f"   Pressure: {pressure:.2f} kPa", end='\r')
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\n   Stopped monitoring")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        pico.close()