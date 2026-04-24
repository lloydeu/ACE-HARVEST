#!/usr/bin/env python3
"""
RPi4 BOTTOM - Main System
Pico connected directly via USB — RPi Top bypassed.
All motor/servo/relay commands go straight to Pico.
Camera stream is still received from RPi Top if video_enabled=True
(Top still runs its GStreamer sender independently).
"""

import time
import threading
from queue import Queue

from inputs import JoystickInput, ButtonInput, LiquidSensorInput, PicoInput
from outputs import DisplayOutput, WinchOutput
from communication import Air780ESMS
from config import config, state


# ── Servo index → Pico servo_id map (mirrors rpi_top handle_servo_command) ──
SERVO_MAP = {
    0: 'sg90',
    1: 'mg996_1',
    2: 'mg996_2',
    3: 'mg996_3',
    4: 'mg996_4',
    5: 'mg996_5',
    6: 'mg996_6',
}

# ── High-level motor command → (motor_id, speed) ────────────────────────────
MOTOR_CMD_MAP = {
    'MOTOR_ARM_UP':          ('worm_gear_arm',    50),
    'MOTOR_ARM_DOWN':        ('worm_gear_arm',   -50),
    'MOTOR_CLAMP_OPEN':      ('worm_gear_clamp',  50),
    'MOTOR_CLAMP_CLOSE':     ('worm_gear_clamp', -50),
    'MOTOR_ACTUATOR_EXTEND': ('linear_actuator',  50),
    'MOTOR_ACTUATOR_RETRACT':('linear_actuator', -50),
    'MOTOR_VACUUM_ON':       ('vacuum_pump',      100),
    'MOTOR_VACUUM_OFF':      ('vacuum_pump',       0),
    # MOTOR_PUMP_TOGGLE handled dynamically
}

# ── High-level relay command → relay_id ─────────────────────────────────────
RELAY_CMD_MAP = {
    'RELAY_LIGHTS_TOGGLE':   'lights',
    'RELAY_SOLENOID_TOGGLE': 'solenoid',
}


class BottomController:
    """Main controller — coordinates all subsystems."""

    def __init__(self):
        # Inputs
        self.joystick     = JoystickInput(mode=config.get('joystick_mode'))
        self.buttons      = ButtonInput()
        self.liquid_sensor= LiquidSensorInput()
        self.pico         = PicoInput(
                                port=config.get('pico_port'),
                                baud=config.get('pico_baud'))

        # Outputs
        self.display = DisplayOutput(
            width=config.get('display_width'),
            height=config.get('display_height'))
        self.winch = WinchOutput()

        # Communication
        self.sms = Air780ESMS(
            port=config.get('air780e_port'),
            phone=config.get('alert_phone'))

        self.event_queue = Queue()
        self.running     = False
        self.threads     = []

    # ── Helper: translate high-level motor cmd ───────────────────────────────

    def _handle_motor_cmd(self, cmd):
        if cmd == 'MOTOR_PUMP_TOGGLE':
            on = not state.get('pump_on', False)
            state['pump_on'] = on
            self.pico.set_motor('vacuum_pump', 100 if on else 0)
            print(f"Motor: PUMP_TOGGLE → {'ON' if on else 'OFF'}")
        elif cmd in MOTOR_CMD_MAP:
            motor_id, speed = MOTOR_CMD_MAP[cmd]
            self.pico.set_motor(motor_id, speed)
            print(f"Motor: {cmd} → {motor_id} @ {speed}")
        else:
            print(f"⚠️  Unknown motor_cmd: {cmd}")

    def _handle_relay_cmd(self, cmd, relay_on):
        if cmd in RELAY_CMD_MAP:
            relay_id = RELAY_CMD_MAP[cmd]
            self.pico.set_relay(relay_id, relay_on)
            # Mirror into state so display stays in sync
            if relay_id == 'lights':
                state['relay_lights'] = relay_on
            elif relay_id == 'solenoid':
                state['relay_valve'] = relay_on
            print(f"Relay: {cmd} → {relay_id} = {relay_on}")
        else:
            print(f"⚠️  Unknown relay_cmd: {cmd}")

    # ── Threads ──────────────────────────────────────────────────────────────

    def input_loop(self):
        """Read physical inputs at 20 Hz."""
        while self.running:
            try:
                js = self.joystick.read()
                if abs(js['x']) > 0.1 or abs(js['y']) > 0.1:
                    state['joystick_x'] = js['x']
                    state['joystick_y'] = js['y']
                    # Joystick drives the arm motor directly
                    # Map Y axis → worm_gear_arm speed
                    arm_speed = int(js['y'] * 100)
                    self.pico.set_motor('worm_gear_arm', arm_speed)

                for event in self.buttons.read():
                    self.event_queue.put(event)

                liquid = self.liquid_sensor.read()
                if liquid != state['liquid_detected']:
                    state['liquid_detected'] = liquid
                    if liquid:
                        self.event_queue.put({'type': 'liquid_detected'})

                time.sleep(0.05)

            except Exception as e:
                print(f"Input loop error: {e}")

    def pico_loop(self):
        """Poll Pico sensors & unsolicited alerts at 10 Hz."""
        while self.running:
            try:
                sensors = self.pico.read_sensors()
                if sensors:
                    state['telemetry'] = {'sensors': sensors}

                for alert in self.pico.get_alerts():
                    print(f"Pico alert: {alert}")
                    atype = alert.get('alert_type', 'PICO_ALERT')
                    msg   = alert.get('message', '')
                    sev   = alert.get('severity', 'warning')
                    if sev == 'critical':
                        self.sms.send_alert(atype, msg)
                    self.event_queue.put(alert)

                time.sleep(0.1)

            except Exception as e:
                print(f"Pico loop error: {e}")
                time.sleep(1)

    def event_handler_loop(self):
        """Process events from queue."""
        while self.running:
            try:
                event = self.event_queue.get(timeout=0.1)
                etype = event.get('type')

                # ── Physical buttons ─────────────────────────────────────
                if etype == 'emergency_stop':
                    print("EMERGENCY STOP")
                    state['emergency_stop'] = True
                    state['running']        = False
                    self.winch.stop()
                    self.pico.stop_all()
                    self.sms.send_alert('EMERGENCY_STOP', 'Emergency stop activated!')

                elif etype == 'button_start':
                    state['running'] = True

                elif etype == 'button_stop':
                    state['running'] = False
                    self.winch.stop()

                elif etype == 'winch_up':
                    self.winch.forward()
                    state['winch_direction'] = 'forward'

                elif etype == 'winch_down':
                    self.winch.reverse()
                    state['winch_direction'] = 'reverse'

                elif etype == 'winch_stop':
                    self.winch.stop()
                    state['winch_direction'] = 'stop'

                # ── Sensor / system alerts ───────────────────────────────
                elif etype == 'liquid_detected':
                    print("Liquid detected!")
                    self.sms.send_alert('LIQUID_DETECTED', 'Liquid level sensor triggered')

                elif etype == 'alert':
                    # Pico stall / conflict alerts already handled in pico_loop
                    pass

                # ── Display UI events ────────────────────────────────────
                elif etype == 'toggle_camera':
                    current = config.get('video_enabled')
                    config.set('video_enabled', not current)
                    if config.get('video_enabled'):
                        self.display.start_camera()
                    else:
                        self.display.stop_camera()

                elif etype == 'toggle_overlay':
                    config.set('display_overlay', not config.get('display_overlay'))

                # ── Motor commands (high-level) ──────────────────────────
                elif etype == 'motor_cmd':
                    self._handle_motor_cmd(event.get('cmd'))

                # ── Motor commands (low-level direct speed) ──────────────
                elif etype == 'motor_control':
                    motor_id = event.get('motor_id')
                    speed    = event.get('speed')
                    print(f"Motor direct: {motor_id}={speed}")
                    self.pico.set_motor(motor_id, speed)

                # ── Servo commands (high-level index) ────────────────────
                elif etype == 'servo_control':
                    idx   = event.get('servo_idx')
                    angle = event.get('angle')
                    servo_id = SERVO_MAP.get(idx)
                    if servo_id:
                        self.pico.set_servo(servo_id, angle)
                        print(f"Servo {idx} → {servo_id} @ {angle}°")
                    else:
                        print(f"⚠️  Unknown servo_idx: {idx}")

                # ── Relay commands (high-level) ───────────────────────────
                elif etype == 'relay_cmd':
                    self._handle_relay_cmd(event.get('cmd'), event.get('state'))

                # ── Relay commands (low-level direct) ────────────────────
                elif etype == 'relay_control':
                    relay_id = event.get('relay_id')
                    relay_on = event.get('state')
                    print(f"Relay direct: {relay_id}={relay_on}")
                    self.pico.set_relay(relay_id, relay_on)

            except Exception:
                pass  # Queue timeout — normal

    def display_update_loop(self):
        """Push state to display and collect UI events at 30 Hz."""
        while self.running:
            try:
                self.display.update(state)
                for event in self.display.handle_events():
                    self.event_queue.put(event)
                time.sleep(1 / 30)
            except Exception as e:
                print(f"Display update error: {e}")

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self):
        print("\n" + "=" * 70)
        print("RPi4 BOTTOM — Direct Pico Mode (RPi Top bypassed)")
        print("=" * 70)

        # Connect to Pico
        if self.pico.connect():
            state['pico_connected'] = True
        else:
            print("⚠️  Pico not available — hardware commands disabled")

        # Start camera receiver if enabled
        if config.get('video_enabled'):
            self.display.start_camera()

        self.running = True

        self.threads = [
            threading.Thread(target=self.input_loop,        daemon=True, name="Input"),
            threading.Thread(target=self.pico_loop,         daemon=True, name="Pico"),
            threading.Thread(target=self.event_handler_loop,daemon=True, name="Events"),
            threading.Thread(target=self.display_update_loop,daemon=True, name="DisplayUpdate"),
        ]

        for t in self.threads:
            t.start()
            print(f"✓ {t.name} thread started")

        print("\n✓ RPi4 Bottom READY")
        print("=" * 70 + "\n")

        # Display runs in main thread (blocks)
        self.display.run()

    def stop(self):
        print("\nStopping system...")
        self.running = False

        for t in self.threads:
            t.join(timeout=1.0)

        self.pico.stop_all()
        self.pico.close()
        self.winch.cleanup()
        self.buttons.cleanup()
        self.display.cleanup()
        self.sms.close()

        print("Cleanup complete")


if __name__ == "__main__":
    controller = BottomController()
    try:
        controller.start()
    except KeyboardInterrupt:
        print("\n")
    finally:
        controller.stop()