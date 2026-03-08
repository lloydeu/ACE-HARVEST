# usb_serial_bidirectional.py
"""
Bidirectional USB Serial Communication
- RPi4 Top can READ sensor data
- RPi4 Top can WRITE motor/servo/relay commands
- Pico executes commands and reports status
"""

import sys
import ujson
import uasyncio as asyncio
import uselect

class USBBidirectional:
    def __init__(self):
        """Initialize bidirectional USB serial communication"""
        self.enabled = True
        self.poll = uselect.poll()
        self.poll.register(sys.stdin, uselect.POLLIN)
        self.command_queue = []
    
    def send_response(self, data):
        """Send JSON response to RPi4 Top"""
        if not self.enabled:
            return
        
        try:
            json_str = ujson.dumps(data)
            print(json_str)
            sys.stdout.flush()
        except Exception as e:
            pass
    
    def check_command(self):
        """
        Non-blocking check for incoming command from RPi4
        Returns: Command string or None
        """
        if self.poll.poll(0):  # Non-blocking
            try:
                line = sys.stdin.readline().strip()
                return line
            except:
                return None
        return None
    
    def send_alert(self, alert_type, message, severity="warning"):
        """Send unsolicited alert to RPi4 (e.g., stall detection)"""
        alert_data = {
            "type": "alert",
            "alert_type": alert_type,
            "message": message,
            "severity": severity
        }
        self.send_response(alert_data)
    
    def process_command(self, cmd_line, state):
        """
        Process command from RPi4 Top and execute/respond
        
        READ COMMANDS (Sensor Data):
        - GET_STATE: Full system state
        - GET_SENSORS: All sensor readings
        - GET_PRESSURE: Pressure only
        - GET_CURRENT: Current readings
        - GET_PH: pH reading
        
        WRITE COMMANDS (Actuator Control):
        - SET_MOTOR motor_id speed: Set motor speed (-100 to 100)
        - SET_SERVO servo_id angle: Set servo angle (0-180)
        - SET_LIGHT left|right on|off: Control lights
        - STOP_ALL: Emergency stop all motors
        - RESET_ERROR: Clear system error
        
        SYSTEM COMMANDS:
        - PING: Alive check
        - GET_STATUS: Quick health check
        """
        try:
            parts = cmd_line.split()
            if not parts:
                return
            
            cmd = parts[0].upper()
            
            # ==================== READ COMMANDS ====================
            if cmd == "GET_STATE":
                self.send_response({
                    "cmd": "STATE",
                    "sensors": {
                        "pressure_kpa": state["pressure_kpa"],
                        "current_amps_1": state["current_amps_1"],
                        "current_amps_2": state["current_amps_2"],
                        "ph_level": state["ph_level"]
                    },
                    "actuators": {
                        "servos": {
                            "sg90": state["servo_sg90_deg"],
                            "mg996_1": state["servo_mg996_1_deg"],
                            "mg996_2": state["servo_mg996_2_deg"],
                            "mg996_3": state["servo_mg996_3_deg"],
                            "mg996_4": state["servo_mg996_4_deg"],
                            "mg996_5": state["servo_mg996_5_deg"],
                            "mg996_6": state["servo_mg996_6_deg"],
                        },
                        "motors": state["motor_speeds"],
                        "lights": {
                            "left": state["relay_left_light"],
                            "right": state["relay_right_light"]
                        }
                    },
                    "system": {
                        "error": state["system_error"],
                        "calibrating": state["is_calibrating"]
                    }
                })
            
            elif cmd == "GET_SENSORS":
                self.send_response({
                    "cmd": "SENSORS",
                    "pressure_kpa": state["pressure_kpa"],
                    "current_amps_1": state["current_amps_1"],
                    "current_amps_2": state["current_amps_2"],
                    "ph_level": state["ph_level"]
                })
            
            elif cmd == "GET_PRESSURE":
                self.send_response({
                    "cmd": "PRESSURE",
                    "pressure_kpa": state["pressure_kpa"]
                })
            
            elif cmd == "GET_CURRENT":
                self.send_response({
                    "cmd": "CURRENT",
                    "current_amps_1": state["current_amps_1"],
                    "current_amps_2": state["current_amps_2"]
                })
            
            elif cmd == "GET_PH":
                self.send_response({
                    "cmd": "PH",
                    "ph_level": state["ph_level"]
                })
            
            # ==================== WRITE COMMANDS ====================
            elif cmd == "SET_MOTOR":
                # SET_MOTOR worm_gear_arm 50
                if len(parts) < 3:
                    self.send_response({"cmd": "ERROR", "message": "Usage: SET_MOTOR motor_id speed"})
                    return
                
                motor_id = parts[1]
                try:
                    speed = int(parts[2])
                    speed = max(-100, min(100, speed))  # Clamp to -100..100
                except ValueError:
                    self.send_response({"cmd": "ERROR", "message": "Invalid speed value"})
                    return
                
                if motor_id in state["motor_speeds"]:
                    state["motor_speeds"][motor_id] = speed
                    self.send_response({
                        "cmd": "MOTOR_SET",
                        "motor_id": motor_id,
                        "speed": speed,
                        "status": "ok"
                    })
                else:
                    self.send_response({"cmd": "ERROR", "message": f"Unknown motor: {motor_id}"})
            
            elif cmd == "SET_SERVO":
                # SET_SERVO mg996_1 90
                if len(parts) < 3:
                    self.send_response({"cmd": "ERROR", "message": "Usage: SET_SERVO servo_id angle"})
                    return
                
                servo_id = parts[1]
                try:
                    angle = int(parts[2])
                    angle = max(0, min(180, angle))  # Clamp to 0..180
                except ValueError:
                    self.send_response({"cmd": "ERROR", "message": "Invalid angle value"})
                    return
                
                state_key = f"servo_{servo_id}_deg"
                if state_key in state:
                    state[state_key] = angle
                    self.send_response({
                        "cmd": "SERVO_SET",
                        "servo_id": servo_id,
                        "angle": angle,
                        "status": "ok"
                    })
                else:
                    self.send_response({"cmd": "ERROR", "message": f"Unknown servo: {servo_id}"})
            
            elif cmd == "SET_LIGHT":
                # SET_LIGHT left on
                # SET_LIGHT right off
                if len(parts) < 3:
                    self.send_response({"cmd": "ERROR", "message": "Usage: SET_LIGHT left|right on|off"})
                    return
                
                light_side = parts[1].lower()
                light_state = parts[2].lower() in ['1', 'true', 'on']
                
                if light_side == "left":
                    state["relay_left_light"] = light_state
                    self.send_response({
                        "cmd": "LIGHT_SET",
                        "light": "left",
                        "state": light_state,
                        "status": "ok"
                    })
                elif light_side == "right":
                    state["relay_right_light"] = light_state
                    self.send_response({
                        "cmd": "LIGHT_SET",
                        "light": "right",
                        "state": light_state,
                        "status": "ok"
                    })
                else:
                    self.send_response({"cmd": "ERROR", "message": "Invalid light (use 'left' or 'right')"})
            
            elif cmd == "STOP_ALL":
                # Emergency stop - kill all motors
                for motor_id in state["motor_speeds"]:
                    state["motor_speeds"][motor_id] = 0
                self.send_response({
                    "cmd": "STOP_ALL",
                    "status": "ok",
                    "message": "All motors stopped"
                })
            
            elif cmd == "RESET_ERROR":
                state["system_error"] = None
                self.send_response({
                    "cmd": "RESET_ERROR",
                    "status": "ok"
                })
            
            # ==================== SYSTEM COMMANDS ====================
            elif cmd == "PING":
                import utime
                self.send_response({
                    "cmd": "PONG",
                    "uptime_ms": utime.ticks_ms()
                })
            
            elif cmd == "GET_STATUS":
                # Quick health check
                self.send_response({
                    "cmd": "STATUS",
                    "system_error": state["system_error"],
                    "motors_active": sum(1 for s in state["motor_speeds"].values() if s != 0),
                    "calibrating": state["is_calibrating"]
                })
            
            else:
                self.send_response({
                    "cmd": "ERROR",
                    "message": f"Unknown command: {cmd}"
                })
        
        except Exception as e:
            self.send_response({
                "cmd": "ERROR",
                "message": f"Command processing error: {str(e)}"
            })

async def usb_bidirectional_task(usb_handler, state):
    """
    Async task for bidirectional communication
    Processes commands from RPi4 Top and sends responses
    """
    while True:
        cmd = usb_handler.check_command()
        if cmd:
            usb_handler.process_command(cmd, state)
        
        await asyncio.sleep_ms(10)  # Check every 10ms for responsive control