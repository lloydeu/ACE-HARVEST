#!/usr/bin/env python3
"""
RPi4 TOP - Main System 

"""
import time
import threading
from queue import Queue
import json

# Import all handlers
from inputs import PicoInput, CameraInput
from outputs import CameraOutput
from communication import BottomServer
from config import config, state

# ========================================
# MAIN CONTROLLER
# ========================================
class TopController:
    """Main controller - coordinates all subsystems"""
    
    def __init__(self):
        # Initialize inputs
        self.pico = PicoInput(port=config.get('pico_port'))
        self.camera_input = CameraInput()
        
        # Initialize outputs
        self.camera_output = CameraOutput(
            host=config.get('rpi_bottom_ip'),
            port=config.get('video_port')
        )
        
        # Initialize communication
        self.bottom_server = BottomServer(port=config.get('tcp_port'))
        
        # Event queue
        self.event_queue = Queue()
        
        # Control flags
        self.running = False
        
        # Threads
        self.threads = []
    
    def pico_loop(self):
        """Read Pico sensors and handle alerts at 10Hz"""
        while self.running:
            try:
                # Get sensor data
                sensors = self.pico.read_sensors()
                if sensors:
                    state['sensors'] = sensors
                
                # Check for alerts from Pico
                alerts = self.pico.get_alerts()
                for alert in alerts:
                    self.event_queue.put(alert)
                
                time.sleep(0.1)  # 10Hz
                
            except Exception as e:
                print(f"Pico loop error: {e}")
                time.sleep(1)
    
    def camera_loop(self):
        """Process camera frames and handle vision tasks"""
        while self.running:
            try:
                # Capture frame
                frame_data = self.camera_input.capture()
                if frame_data:
                    state['camera'] = frame_data
                
                time.sleep(1/30)  # 30 FPS
                
            except Exception as e:
                print(f"Camera loop error: {e}")
                time.sleep(1)
    
    def decision_loop(self):
        """Decision logic - robot control based on sensors/camera"""
        while self.running:
            try:
                # This is where autonomous logic would go
                # For now, just pass through commands from Bottom
                
                time.sleep(0.1)
                
            except Exception as e:
                print(f"Decision loop error: {e}")
    
    def event_handler_loop(self):
        """Process events from queue"""
        while self.running:
            try:
                event = self.event_queue.get(timeout=0.1)
                
                event_type = event.get('type')
                
                # Pico alerts
                if event_type == 'alert':
                    alert_type = event.get('alert_type')
                    message = event.get('message')
                    severity = event.get('severity')
                    
                    print(f"🚨 Pico Alert: [{alert_type}] {message}")
                    
                    # Forward to Bottom
                    self.bottom_server.send_alert(event)
                
                # Commands from Bottom
                elif event_type == 'motor_control':
                    motor_id = event.get('motor_id')
                    speed = event.get('speed')
                    self.pico.set_motor(motor_id, speed)
                
                # Easy motor commands from Bottom
                elif event_type == 'motor_cmd':
                    cmd = event.get('cmd')
                    self.handle_motor_command(cmd)
                
                # Servo commands from Bottom
                elif event_type == 'servo_control':
                    servo_id = event.get('servo_id')
                    angle = event.get('angle')
                    self.pico.set_servo(servo_id, angle)
                
                # Easy servo commands from Bottom
                elif event_type == 'servo_cmd':
                    servo_idx = event.get('servo_idx')
                    angle = event.get('angle')
                    self.handle_servo_command(servo_idx, angle)
                
                # Relay commands from Bottom
                elif event_type == 'relay_control':
                    relay_id = event.get('relay_id')
                    state_on = event.get('state')
                    self.pico.set_relay(relay_id, state_on)
                
                # Easy relay commands from Bottom
                elif event_type == 'relay_cmd':
                    cmd = event.get('cmd')
                    state = event.get('state')
                    self.handle_relay_command(cmd, state)
                
                elif event_type == 'emergency_stop':
                    print("🚨 EMERGENCY STOP from Bottom")
                    self.pico.stop_all()
                    state['emergency_stop'] = True
                
                elif event_type == 'joystick':
                    # Handle joystick input from Bottom
                    x = event.get('x')
                    y = event.get('y')
                    # Process joystick (convert to motor commands, etc.)
                    pass
                
            except:
                pass  # Queue timeout - normal
    
    def telemetry_loop(self):
        """Send telemetry to Bottom at 5Hz"""
        while self.running:
            try:
                telemetry = {
                    'type': 'telemetry',
                    'data': {
                        'sensors': state.get('sensors', {}),
                        'camera': state.get('camera', {}),
                        'timestamp': time.time()
                    }
                }
                
                self.bottom_server.send_telemetry(telemetry)
                
                time.sleep(0.2)  # 5Hz
                
            except Exception as e:
                pass
    
    def bottom_command_loop(self):
        """Receive commands from Bottom"""
        while self.running:
            try:
                command = self.bottom_server.receive()
                
                if command:
                    # Put command in event queue
                    self.event_queue.put(command)
                
                time.sleep(0.01)
                
            except Exception as e:
                pass
    
    def handle_motor_command(self, cmd):
        """Translate easy motor commands to Pico commands"""
        motor_map = {
            'MOTOR_ARM_UP': ('worm_gear_arm', 50),
            'MOTOR_ARM_DOWN': ('worm_gear_arm', -50),
            'MOTOR_CLAMP_OPEN': ('worm_gear_clamp', 50),
            'MOTOR_CLAMP_CLOSE': ('worm_gear_clamp', -50),
            'MOTOR_ACTUATOR_EXTEND': ('linear_actuator', 50),
            'MOTOR_ACTUATOR_RETRACT': ('linear_actuator', -50),
            'MOTOR_PUMP_TOGGLE': ('vacuum_pump', 100 if not state.get('pump_on', False) else 0),
        }
        
        if cmd in motor_map:
            motor_id, speed = motor_map[cmd]
            self.pico.set_motor(motor_id, speed)
            
            # Track pump state
            if cmd == 'MOTOR_PUMP_TOGGLE':
                state['pump_on'] = not state.get('pump_on', False)
    
    def handle_servo_command(self, servo_idx, angle):
        """Translate servo index to servo ID"""
        servo_map = {
            0: 'sg90',
            1: 'mg996_1',
            2: 'mg996_2',
            3: 'mg996_3',
            4: 'mg996_4',
            5: 'mg996_5',
            6: 'mg996_6',
        }
        
        if servo_idx in servo_map:
            servo_id = servo_map[servo_idx]
            self.pico.set_servo(servo_id, angle)
    
    def handle_relay_command(self, cmd, state_on):
        """Translate relay commands to Pico commands"""
        relay_map = {
            'RELAY_LIGHTS_TOGGLE': 'lights',
            'RELAY_SOLENOID_TOGGLE': 'solenoid',
        }
        
        if cmd in relay_map:
            relay_id = relay_map[cmd]
            self.pico.set_relay(relay_id, state_on)
    
    def start(self):
        """Start all subsystems"""
        print("\n" + "="*70)
        print("RPi4 TOP - Starting System")
        print("="*70)
        
        # Connect to Pico
        if self.pico.connect():
            state['pico_connected'] = True
            print("✓ Connected to Pico")
        else:
            print("⚠️  Pico connection failed")
        
        # Start camera streaming
        if self.camera_output.start():
            state['camera_streaming'] = True
            print("✓ Camera streaming started")
        else:
            print("⚠️  Camera streaming failed")
        
        # Start Bottom server
        if self.bottom_server.start():
            state['bottom_server_running'] = True
            print("✓ Bottom server started")
        else:
            print("⚠️  Bottom server failed")
        
        # Set running flag
        self.running = True
        
        # Create and start threads
        self.threads = [
            threading.Thread(target=self.pico_loop, daemon=True, name="Pico"),
            threading.Thread(target=self.camera_loop, daemon=True, name="Camera"),
            threading.Thread(target=self.decision_loop, daemon=True, name="Decision"),
            threading.Thread(target=self.event_handler_loop, daemon=True, name="Events"),
            threading.Thread(target=self.telemetry_loop, daemon=True, name="Telemetry"),
            threading.Thread(target=self.bottom_command_loop, daemon=True, name="BottomCmd"),
        ]
        
        for thread in self.threads:
            thread.start()
            print(f"✓ {thread.name} thread started")
        
        print("\n✓ RPi4 Top READY")
        print("="*70 + "\n")
    
    def stop(self):
        """Stop all subsystems"""
        print("\n⏹️  Stopping system...")
        
        self.running = False
        
        # Wait for threads
        for thread in self.threads:
            thread.join(timeout=1.0)
        
        # Cleanup
        self.pico.close()
        self.camera_output.stop()
        self.bottom_server.stop()
        
        print("✓ Cleanup complete")

# ========================================
# MAIN ENTRY POINT
# ========================================
if __name__ == "__main__":
    controller = TopController()
    
    try:
        controller.start()
        
        # Keep main thread alive
        while True:
            time.sleep(1)
    
    except KeyboardInterrupt:
        print("\n")
    finally:
        controller.stop()
