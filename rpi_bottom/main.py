#!/usr/bin/env python3
"""
RPi4 BOTTOM - Main System (Fixed for Tkinter)
"""

import time
import threading
from queue import Queue
import json
import os

# Import all handlers
from inputs import JoystickInput, ButtonInput, LiquidSensorInput
from outputs import DisplayOutput, WinchOutput
from communication import TopClient, Air780ESMS
from config import config, state

# ========================================
# MAIN CONTROLLER
# ========================================
class BottomController:
    """Main controller - coordinates all subsystems"""
    
    def __init__(self):
        # Initialize all inputs
        self.joystick = JoystickInput(mode=config.get('joystick_mode'))
        self.buttons = ButtonInput()
        self.liquid_sensor = LiquidSensorInput()
        
        # Initialize all outputs
        self.display = DisplayOutput(
            width=config.get('display_width'),
            height=config.get('display_height')
        )
        self.winch = WinchOutput()
        
        # Initialize communication
        self.top_client = TopClient(
            host=config.get('rpi_top_ip'),
            port=config.get('rpi_top_port')
        )
        self.sms = Air780ESMS(
            port=config.get('air780e_port'),
            phone=config.get('alert_phone')
        )
        
        # Event queue for inter-thread communication
        self.event_queue = Queue()
        
        # Control flags
        self.running = False
        
        # Threads
        self.threads = []
    
    def input_loop(self):
        """Read all inputs at 20Hz"""
        while self.running:
            try:
                # Read joystick
                js_state = self.joystick.read()
                if abs(js_state['x']) > 0.1 or abs(js_state['y']) > 0.1:
                    state['joystick_x'] = js_state['x']
                    state['joystick_y'] = js_state['y']
                    # Send to Top
                    self.event_queue.put({
                        'type': 'joystick',
                        'x': js_state['x'],
                        'y': js_state['y']
                    })
                
                # Read buttons
                button_events = self.buttons.read()
                for event in button_events:
                    self.event_queue.put(event)
                
                # Read liquid sensor
                liquid_detected = self.liquid_sensor.read()
                if liquid_detected != state['liquid_detected']:
                    state['liquid_detected'] = liquid_detected
                    if liquid_detected:
                        self.event_queue.put({
                            'type': 'liquid_detected',
                            'level': True
                        })
                
                time.sleep(0.05)  # 20Hz
                
            except Exception as e:
                print(f"Input loop error: {e}")
    
    def event_handler_loop(self):
        """Process events from queue"""
        while self.running:
            try:
                # Get event (blocking with timeout)
                event = self.event_queue.get(timeout=0.1)
                
                event_type = event.get('type')
                
                # Emergency stop
                if event_type == 'emergency_stop':
                    print("EMERGENCY STOP")
                    state['emergency_stop'] = True
                    state['running'] = False
                    self.winch.stop()
                    # Send to Top
                    self.top_client.send_command({'type': 'emergency_stop'})
                    # Send SMS
                    self.sms.send_alert('EMERGENCY_STOP', 'Emergency stop activated!')
                
                # Start button
                elif event_type == 'button_start':
                    print("Start")
                    state['running'] = True
                
                # Stop button
                elif event_type == 'button_stop':
                    print("Stop")
                    state['running'] = False
                    self.winch.stop()
                
                # Winch controls
                elif event_type == 'winch_up':
                    print("Winch UP")
                    self.winch.forward()
                    state['winch_direction'] = 'forward'
                
                elif event_type == 'winch_down':
                    print("Winch DOWN")
                    self.winch.reverse()
                    state['winch_direction'] = 'reverse'
                
                elif event_type == 'winch_stop':
                    self.winch.stop()
                    state['winch_direction'] = 'stop'
                
                # Joystick
                elif event_type == 'joystick':
                    self.top_client.send_command(event)
                
                # Liquid detection
                elif event_type == 'liquid_detected':
                    print("Liquid detected!")
                    self.sms.send_alert('LIQUID_DETECTED', 'Liquid level sensor triggered')
                
                # Toggle camera
                elif event_type == 'toggle_camera':
                    current = config.get('video_enabled')
                    config.set('video_enabled', not current)
                    if config.get('video_enabled'):
                        self.display.start_camera()
                    else:
                        self.display.stop_camera()
                
                # Toggle overlay
                elif event_type == 'toggle_overlay':
                    current = config.get('display_overlay')
                    config.set('display_overlay', not current)
                
                # Motor controls
                elif event_type == 'motor_control':
                    cmd = event.get('cmd')
                    print(f"Motor: {cmd}")
                    self.top_client.send_command({'type': 'motor_cmd', 'cmd': cmd})
                
                # Servo controls
                elif event_type == 'servo_control':
                    servo_idx = event.get('servo_idx')
                    angle = event.get('angle')
                    print(f"Servo {servo_idx}: {angle} deg")
                    self.top_client.send_command({
                        'type': 'servo_cmd',
                        'servo_idx': servo_idx,
                        'angle': angle
                    })
                
                # Relay controls
                elif event_type == 'relay_control':
                    cmd = event.get('cmd')
                    relay_state = event.get('state')
                    print(f"Relay: {cmd} = {relay_state}")
                    self.top_client.send_command({
                        'type': 'relay_cmd',
                        'cmd': cmd,
                        'state': relay_state
                    })
                
            except:
                pass  # Queue timeout - normal
    
    def telemetry_loop(self):
        """Receive telemetry from RPi Top"""
        while self.running:
            try:
                data = self.top_client.receive()
                
                if data:
                    data_type = data.get('type')
                    
                    if data_type == 'telemetry':
                        state['telemetry'] = data.get('data', {})
                    
                    elif data_type == 'alert':
                        alert_type = data.get('alert_type')
                        message = data.get('message')
                        severity = data.get('severity')
                        
                        print(f"Alert: [{alert_type}] {message}")
                        
                        # Forward critical alerts via SMS
                        if severity == 'critical':
                            self.sms.send_alert(alert_type, message)
                
                time.sleep(0.01)
                
            except Exception as e:
                pass
    
    def update_display_from_thread(self):
        """Update display state from background thread"""
        while self.running:
            try:
                # Update display state (this is thread-safe)
                self.display.update(state)
                
                # Check for UI button events
                ui_events = self.display.handle_events()
                for event in ui_events:
                    self.event_queue.put(event)
                
                time.sleep(1/30)  # 30 FPS
            except Exception as e:
                print(f"Display update error: {e}")
    
    def start(self):
        """Start all subsystems"""
        print("\n" + "="*70)
        print("RPi4 BOTTOM - Starting System")
        print("="*70)
        
        # Connect to Top
        if self.top_client.connect():
            state['top_connected'] = True
            print("Connected to RPi Top")
        else:
            print("RPi Top connection failed")
        
        # Start camera if enabled
        if config.get('video_enabled'):
            self.display.start_camera()
        
        # Set running flag
        self.running = True
        
        # Create and start background threads (ALL EXCEPT DISPLAY)
        self.threads = [
            threading.Thread(target=self.input_loop, daemon=True, name="Input"),
            threading.Thread(target=self.event_handler_loop, daemon=True, name="Events"),
            threading.Thread(target=self.telemetry_loop, daemon=True, name="Telemetry"),
            threading.Thread(target=self.update_display_from_thread, daemon=True, name="DisplayUpdate"),
        ]
        
        for thread in self.threads:
            thread.start()
            print(f"{thread.name} thread started")
        
        print("\nRPi4 Bottom READY")
        print("="*70 + "\n")
        
        # Run display in MAIN THREAD (this blocks)
        self.display.run()
    
    def stop(self):
        """Stop all subsystems"""
        print("\nStopping system...")
        
        self.running = False
        
        # Wait for threads
        for thread in self.threads:
            thread.join(timeout=1.0)
        
        # Cleanup hardware
        self.winch.cleanup()
        self.buttons.cleanup()
        self.display.cleanup()
        self.top_client.close()
        self.sms.close()
        
        print("Cleanup complete")

# ========================================
# MAIN ENTRY POINT
# ========================================
if __name__ == "__main__":
    controller = BottomController()
    
    try:
        controller.start()
    except KeyboardInterrupt:
        print("\n")
    finally:
        controller.stop()
