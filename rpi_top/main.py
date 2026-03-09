#!/usr/bin/env python3
"""
RPi4 TOP - Main Control System
Orchestrates:
- PiCam Module 3 video streaming (GStreamer)
- Pico sensor/motor control
- Communication with RPi4 Bottom (user interface)

Hardware:
- Motors: worm_gear_arm, worm_gear_clamp, linear_actuator, vacuum_pump
- Lights: relay_left_light, relay_right_light
- Servos: mg996_1 through mg996_6, sg90
"""

import socket
import json
import time
import threading
from queue import Queue
from controller import PicoController
from camera_handler import GStreamerCamera, GStreamerCameraMonitor

# ========================================
# CONFIGURATION
# ========================================
RPI_BOTTOM_IP = "192.168.1.100"  # IP of RPi4 Bottom
RPI_BOTTOM_PORT = 5000           # Control/telemetry port
VIDEO_STREAM_PORT = 5001         # Video stream port
PICO_PORT = "/dev/ttyACM0"

# Camera settings
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
CAMERA_FPS = 30

# ========================================
# NETWORK CLIENT FOR RPi4 BOTTOM
# ========================================
class BottomClient:
    """
    Communicates with RPi4 Bottom (user interface)
    Sends: sensor telemetry, alerts
    Receives: joystick commands, user inputs
    """
    
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = None
        self.connected = False
        self.command_callback = None
    
    def connect(self):
        """Connect to RPi4 Bottom"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            self.sock.settimeout(1.0)
            self.connected = True
            print(f"✓ Connected to RPi4 Bottom at {self.host}:{self.port}")
        except Exception as e:
            print(f"✗ Failed to connect to RPi4 Bottom: {e}")
            self.connected = False
    
    def send_telemetry(self, data):
        """Send sensor/camera data to RPi4 Bottom"""
        if not self.connected:
            return False
        
        try:
            msg = json.dumps({"type": "telemetry", "data": data})
            self.sock.sendall(f"{msg}\n".encode('utf-8'))
            return True
        except Exception as e:
            print(f"⚠️  Failed to send telemetry: {e}")
            self.connected = False
            return False
    
    def send_alert(self, alert_type, message, severity="warning"):
        """Forward alerts to RPi4 Bottom for user notification"""
        if not self.connected:
            return False
        
        try:
            msg = json.dumps({
                "type": "alert",
                "alert_type": alert_type,
                "message": message,
                "severity": severity
            })
            self.sock.sendall(f"{msg}\n".encode('utf-8'))
            return True
        except Exception as e:
            print(f"⚠️  Failed to send alert: {e}")
            return False
    
    def receive_commands(self):
        """
        Receive commands from RPi4 Bottom (blocking)
        Returns: Command dict or None
        """
        if not self.connected:
            return None
        
        try:
            data = self.sock.recv(4096).decode('utf-8').strip()
            if data:
                return json.loads(data)
        except socket.timeout:
            return None
        except Exception as e:
            print(f"⚠️  Receive error: {e}")
            self.connected = False
            return None
    
    def close(self):
        """Close connection"""
        if self.sock:
            self.sock.close()
            self.connected = False

# ========================================
# MAIN CONTROL ORCHESTRATOR
# ========================================
class TopController:
    """
    Main controller for RPi4 Top
    Orchestrates camera streaming, Pico, and network communication
    """
    
    def __init__(self):
        # Initialize Pico controller with alert forwarding
        self.pico = PicoController(
            port=PICO_PORT,
            alert_callback=self.handle_pico_alert
        )
        
        # Initialize camera streaming
        self.camera = GStreamerCamera(
            bottom_ip=RPI_BOTTOM_IP,
            stream_port=VIDEO_STREAM_PORT,
            width=CAMERA_WIDTH,
            height=CAMERA_HEIGHT,
            framerate=CAMERA_FPS
        )
        
        # Camera monitor (auto-restart on failure)
        self.camera_monitor = GStreamerCameraMonitor(self.camera)
        
        # Initialize network client to RPi4 Bottom
        self.bottom = BottomClient(RPI_BOTTOM_IP, RPI_BOTTOM_PORT)
        self.bottom.connect()
        
        # Control state
        self.running = False
        self.telemetry_thread = None
        self.command_thread = None
    
    def handle_pico_alert(self, alert_type, message, severity):
        """
        Callback when Pico sends an alert
        Forward to RPi4 Bottom for user notification
        """
        print(f"🚨 Pico Alert: [{alert_type}] {message}")
        
        # Forward to RPi4 Bottom
        self.bottom.send_alert(alert_type, message, severity)
        
        # Take action based on alert type
        if alert_type == "STALL":
            print("   → Motor stall detected, stopping all motors")
            self.pico.stop_all_motors()
        
        elif alert_type == "CONFLICT":
            print("   → Motor conflict, emergency stop")
            self.pico.stop_all_motors()
    
    def handle_bottom_command(self, command):
        """
        Process commands from RPi4 Bottom (joystick, user inputs)
        
        Supported motors:
        - worm_gear_arm
        - worm_gear_clamp
        - linear_actuator
        - vacuum_pump
        
        Supported lights:
        - left (relay_left_light)
        - right (relay_right_light)
        """
        if not command:
            return
        
        cmd_type = command.get("type")
        
        if cmd_type == "motor_control":
            motor_id = command.get("motor_id")
            speed = command.get("speed", 0)
            self.pico.set_motor(motor_id, speed)
            print(f"   Motor {motor_id} → {speed}%")
        
        elif cmd_type == "servo_control":
            servo_id = command.get("servo_id")
            angle = command.get("angle", 90)
            self.pico.set_servo(servo_id, angle)
            print(f"   Servo {servo_id} → {angle}°")
        
        elif cmd_type == "light_control":
            light_side = command.get("light", "left")  # "left" or "right"
            state = command.get("state", False)
            self.pico.set_light(light_side, state)
            print(f"   {light_side.capitalize()} light → {'ON' if state else 'OFF'}")
        
        elif cmd_type == "emergency_stop":
            self.pico.stop_all_motors()
            print("   🛑 EMERGENCY STOP")
        
        elif cmd_type == "joystick":
            # Example: joystick controls linear actuator speed
            x_axis = command.get("x", 0)  # -1.0 to 1.0
            y_axis = command.get("y", 0)
            
            # Map joystick Y-axis to motor speed
            speed = int(y_axis * 100)
            self.pico.set_motor("linear_actuator", speed)
    
    def telemetry_loop(self):
        """
        Background thread: Send telemetry to RPi4 Bottom periodically
        """
        while self.running:
            try:
                # Get sensor data from Pico
                sensors = self.pico.get_sensors()
                
                # Get camera stream info
                camera_info = self.camera.get_stream_info()
                
                # Combine telemetry
                telemetry = {
                    "sensors": sensors,
                    "camera": camera_info,
                    "timestamp": time.time()
                }
                
                # Send to RPi4 Bottom
                self.bottom.send_telemetry(telemetry)
                
            except Exception as e:
                print(f"Telemetry error: {e}")
            
            time.sleep(0.1)  # 10Hz telemetry rate
    
    def command_loop(self):
        """
        Background thread: Receive commands from RPi4 Bottom
        """
        while self.running:
            try:
                command = self.bottom.receive_commands()
                if command:
                    self.handle_bottom_command(command)
            except Exception as e:
                print(f"Command receive error: {e}")
            
            time.sleep(0.01)  # Fast polling for responsive controls
    
    def start(self):
        """Start the control system"""
        print("\n" + "="*60)
        print("RPi4 TOP - Starting Control System")
        print("="*60)
        
        # Start camera streaming
        print("\n1. Starting camera stream...")
        self.camera.start_streaming()
        self.camera_monitor.start_monitoring()
        
        # Start background threads
        print("\n2. Starting telemetry and command loops...")
        self.running = True
        
        self.telemetry_thread = threading.Thread(target=self.telemetry_loop, daemon=True)
        self.command_thread = threading.Thread(target=self.command_loop, daemon=True)
        
        self.telemetry_thread.start()
        self.command_thread.start()
        
        print("\n" + "="*60)
        print("✓ RPi4 Top control system READY")
        print("="*60)
        print(f"  • Pico: Connected ({PICO_PORT})")
        print(f"  • Camera: Streaming to {RPI_BOTTOM_IP}:{VIDEO_STREAM_PORT}")
        print(f"  • Network: {'Connected' if self.bottom.connected else 'Disconnected'}")
        print(f"  • Motors: worm_gear_arm, worm_gear_clamp, linear_actuator, vacuum_pump")
        print(f"  • Lights: left, right")
        print("="*60 + "\n")
    
    def stop(self):
        """Stop the control system"""
        print("\n⏹️  Stopping control system...")
        
        self.running = False
        
        # Stop camera
        self.camera_monitor.stop_monitoring()
        self.camera.stop_streaming()
        
        # Stop all motors
        self.pico.stop_all_motors()
        
        # Wait for threads
        if self.telemetry_thread:
            self.telemetry_thread.join(timeout=1.0)
        if self.command_thread:
            self.command_thread.join(timeout=1.0)
        
        # Cleanup
        self.pico.close()
        self.bottom.close()
        
        print("✓ Cleanup complete")

# ========================================
# STANDALONE MODE (for testing)
# ========================================
def standalone_mode():
    """
    Standalone mode for testing without RPi4 Bottom
    Reads sensors and accepts keyboard commands
    """
    print("\n" + "="*60)
    print("RPi4 TOP - Standalone Mode")
    print("="*60)
    
    pico = PicoController(port=PICO_PORT)
    
    try:
        # Test connection
        print("\n1. Testing Pico connection...")
        ping = pico.ping()
        print(f"   ✓ Pico uptime: {ping.get('uptime_ms')} ms")
        
        # Read sensors
        print("\n2. Reading sensors...")
        sensors = pico.get_sensors()
        if sensors:
            print(f"   Pressure: {sensors['pressure_kpa']:.2f} kPa")
            print(f"   pH: {sensors['ph_level']:.2f}")
            print(f"   Current 1: {sensors['current_amps_1']:.2f} A")
            print(f"   Current 2: {sensors['current_amps_2']:.2f} A")
        
        # Interactive control
        print("\n3. Interactive control (type 'help' for commands)")
        print("   Press Ctrl+C to exit")
        
        while True:
            cmd = input("\n> ").strip().lower()
            
            if cmd == "help":
                print("Commands:")
                print("  motor <id> <speed>        - Set motor speed (-100 to 100)")
                print("    Motors: worm_gear_arm, worm_gear_clamp, linear_actuator, vacuum_pump")
                print("  servo <id> <angle>        - Set servo angle (0-180)")
                print("    Servos: mg996_1 to mg996_6, sg90")
                print("  light <left|right> <on|off> - Control lights")
                print("  sensors                   - Read all sensors")
                print("  stop                      - Stop all motors")
                print("  quit                      - Exit")
            
            elif cmd.startswith("motor "):
                parts = cmd.split()
                if len(parts) == 3:
                    motor_id, speed = parts[1], int(parts[2])
                    pico.set_motor(motor_id, speed)
                    print(f"   ✓ Motor {motor_id} set to {speed}%")
            
            elif cmd.startswith("servo "):
                parts = cmd.split()
                if len(parts) == 3:
                    servo_id, angle = parts[1], int(parts[2])
                    pico.set_servo(servo_id, angle)
                    print(f"   ✓ Servo {servo_id} set to {angle}°")
            
            elif cmd.startswith("light "):
                parts = cmd.split()
                if len(parts) == 3:
                    light_side = parts[1]  # "left" or "right"
                    state = parts[2] == "on"
                    pico.set_light(light_side, state)
                    print(f"   ✓ {light_side.capitalize()} light turned {'ON' if state else 'OFF'}")
            
            elif cmd == "sensors":
                sensors = pico.get_sensors()
                if sensors:
                    print(f"   Pressure: {sensors['pressure_kpa']:.2f} kPa")
                    print(f"   pH: {sensors['ph_level']:.2f}")
                    print(f"   Current 1: {sensors['current_amps_1']:.2f} A")
                    print(f"   Current 2: {sensors['current_amps_2']:.2f} A")
            
            elif cmd == "stop":
                pico.stop_all_motors()
                print("   ✓ All motors stopped")
            
            elif cmd in ["quit", "exit"]:
                break
    
    except KeyboardInterrupt:
        print("\n")
    finally:
        pico.close()

# ========================================
# MAIN ENTRY POINT
# ========================================
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "standalone":
        # Standalone mode for testing
        standalone_mode()
    else:
        # Full system mode with RPi4 Bottom communication
        controller = TopController()
        
        try:
            controller.start()
            
            # Keep running until interrupted
            while True:
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\n")
        finally:
            controller.stop()