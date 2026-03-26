import tkinter as tk
from tkinter import font as tkfont
import threading
import time
 
try:
    from config import config, state
except ImportError:
    config = {'video_enabled': False, 'display_overlay': True, 'video_port': 5001}
    state  = {}
 
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("Warning: PIL not installed - camera disabled")
 
try:
    import gi
    gi.require_version('Gst',    '1.0')
    gi.require_version('GstApp', '1.0')
    from gi.repository import Gst, GstApp, GLib
    Gst.init(None)
    GST_AVAILABLE = True
except Exception as e:
    GST_AVAILABLE = False
    print(f"Warning: GStreamer PyGObject unavailable ({e})")
 
 
# ─────────────────────────── Design tokens ────────────────────────────────
C = {
    'base':   '#0d0d0d',
    'panel':  '#141414',
    'card':   '#1c1c1c',
    'btn':    '#222222',
    'btn_hl': '#2a2a2a',
    'accent': '#00c8ff',
    'green':  '#22c55e',
    'red':    '#ef4444',
    'amber':  '#f59e0b',
    'pri':    '#e2e2e2',
    'muted':  '#4a4a4a',
    'border': '#272727',
}
 
SCREEN_W  = 1024
SCREEN_H  = 600
PANEL_W   = 220
TOPBAR_H  = 44
CONTENT_H = SCREEN_H - TOPBAR_H        # 556
CAMERA_W  = SCREEN_W - PANEL_W         # 804
CAMERA_H  = int(CAMERA_W * 9 / 16)    # 452
 
 
def _btn(parent, text, cmd, bg=None, fg=None, font=None, **kw):
    """Flat dark button — no border relief."""
    return tk.Button(
        parent, text=text, command=cmd,
        bg=bg or C['btn'], fg=fg or C['pri'],
        font=font, relief='flat', bd=0,
        cursor='hand2',
        activebackground=C['btn_hl'],
        activeforeground=C['pri'],
        **kw)
 
 
def _sep(parent):
    tk.Frame(parent, bg=C['border'], height=1).pack(fill=tk.X, padx=4, pady=4)
 
 
def _section_lbl(parent, text):
    tk.Label(parent, text=text, bg=C['panel'],
             fg=C['muted'], font=('Arial', 8, 'bold'),
             anchor='w').pack(fill=tk.X, padx=10, pady=(6, 1))
 
 
# ══════════════════════════════════════════════════════════════════════════
class DisplayOutput:
 
    RECV_W = 640
    RECV_H = 480
 
    # ── init ──────────────────────────────────────────────────────────────
    def __init__(self, width=SCREEN_W, height=SCREEN_H):
        try:
            self.root = tk.Tk()
            self.root.title("RPi4 Bottom")
            self.root.overrideredirect(True)          # remove WM titlebar/chrome
            self.root.attributes('-fullscreen', True)  # true fullscreen on Wayland
            self.root.configure(bg=C['base'])
            self.root.attributes('-topmost', True)
            self.root.focus_force()
 
            # Read actual screen size after fullscreen is applied
            self.root.update_idletasks()
            self.width  = self.root.winfo_screenwidth()
            self.height = self.root.winfo_screenheight()
 
            # fonts
            self.f_title  = tkfont.Font(family='Arial',   size=12, weight='bold')
            self.f_body   = tkfont.Font(family='Arial',   size=10)
            self.f_small  = tkfont.Font(family='Arial',   size=8)
            self.f_mono_s = tkfont.Font(family='Courier', size=8)
            self.f_btn    = tkfont.Font(family='Arial',   size=9,  weight='bold')
 
            # camera
            self.video_port     = config.get('video_port', 5001)
            self.camera_running = False
            self.gst_pipeline   = None
            self.camera_photo   = None
            self.camera_pil     = None
            self.frame_lock     = threading.Lock()
            self.frame_pending  = False
 
            # tk vars
            self.video_enabled   = tk.BooleanVar(value=config.get('video_enabled',   False))
            self.overlay_enabled = tk.BooleanVar(value=config.get('display_overlay', True))
 
            # local relay/pump visual state
            self._lights_on = False
            self._valve_on  = False
            self._pump_on   = False
 
            # shared state
            self.current_state = {}
            self.event_queue   = []
            self.event_lock    = threading.Lock()
            self.running       = True
 
            self._build_ui()
            self._tick()
 
            self.enabled = True
            print("Display ready - 1024x600 dark industrial")
 
        except Exception as e:
            print(f"Display init failed: {e}")
            self.enabled = False
 
    # ── UI construction ────────────────────────────────────────────────────
 
    def _build_ui(self):
        self._build_topbar()
        tk.Frame(self.root, bg=C['border'], height=1).pack(fill=tk.X)
        self._build_body()
 
    def _build_topbar(self):
        bar = tk.Frame(self.root, bg=C['panel'], height=TOPBAR_H)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)
 
        self.status_badge = tk.Label(
            bar, text="[*] IDLE", bg=C['panel'],
            fg=C['amber'], font=self.f_title, anchor='w')
        self.status_badge.pack(side=tk.LEFT, padx=14)
 
        self.liquid_badge = tk.Label(
            bar, text="[!] LIQUID DETECTED", bg=C['panel'],
            fg=C['red'], font=self.f_body)
        # shown only when triggered
 
        # Exit button — two-tap confirm to prevent accidental exit
        self._exit_armed = False
        self._exit_timer = None
        self.exit_btn = tk.Button(
            bar, text="X", command=self._exit_tap,
            bg=C['panel'], fg=C['muted'],
            font=self.f_title, relief='flat', bd=0,
            cursor='hand2', padx=10,
            activebackground=C['red'], activeforeground='white')
        self.exit_btn.pack(side=tk.RIGHT, fill=tk.Y)
 
        tk.Frame(bar, bg=C['border'], width=1).pack(side=tk.RIGHT, fill=tk.Y)
 
        self.winch_badge = tk.Label(
            bar, text="WINCH --", bg=C['panel'],
            fg=C['muted'], font=self.f_small)
        self.winch_badge.pack(side=tk.RIGHT, padx=(0, 14))
 
        self.clock_lbl = tk.Label(
            bar, text="", bg=C['panel'],
            fg=C['muted'], font=self.f_mono_s)
        self.clock_lbl.pack(side=tk.RIGHT, padx=(0, 16))
 
    def _build_body(self):
        body = tk.Frame(self.root, bg=C['base'])
        body.pack(fill=tk.BOTH, expand=True)
 
        # IMPORTANT: pack RIGHT-side widgets BEFORE LEFT-side widgets.
        # Tk's pack algorithm allocates space in pack order — if cam_frame
        # (LEFT, fixed width) is packed first it consumes all horizontal space
        # and the panel gets zero width and renders invisible.
        # Pack panel RIGHT first, then cam_frame fills the remaining space.
 
        # right panel (packed first so Tk reserves PANEL_W from the right)
        self._build_panel(body)
 
        # divider
        tk.Frame(body, bg=C['border'], width=1).pack(side=tk.RIGHT, fill=tk.Y)
 
        # camera area (fills all remaining space to the left)
        self.cam_frame = tk.Frame(body, bg='#090909')
        self.cam_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
 
        self.cam_label = tk.Label(
            self.cam_frame, text="NO SIGNAL",
            bg='#090909', fg=C['muted'], font=self.f_title)
        self.cam_label.place(x=0, y=0, relwidth=1.0, relheight=1.0)
 
        self._build_overlay()
 
    def _build_overlay(self):
        """Telemetry overlay — bottom-left of camera, relative positioned."""
        OW, OH = 228, 110
        self.overlay_frame = tk.Frame(
            self.cam_frame, bg='#0a0a0a',
            highlightbackground=C['border'], highlightthickness=1)
        # relx/rely positions relative to cam_frame size — stays bottom-left
        # regardless of actual screen resolution
        self.overlay_frame.place(relx=0.0, rely=1.0, x=8, y=-OH-8,
                                  width=OW, height=OH)
 
        self.overlay_values = {}
        rows = [
            ('PRESSURE', 'pressure_kpa',   '{:.1f} kPa'),
            ('pH',       'ph_level',       '{:.2f}'),
            ('CURRENT1', 'current_amps_1', '{:.2f} A'),
            ('CURRENT2', 'current_amps_2', '{:.2f} A'),
        ]
        for label, key, fmt in rows:
            row = tk.Frame(self.overlay_frame, bg='#0a0a0a')
            row.pack(fill=tk.X, padx=8, pady=1)
            tk.Label(row, text=label, bg='#0a0a0a', fg=C['muted'],
                     font=self.f_small, width=8, anchor='w').pack(side=tk.LEFT)
            val = tk.Label(row, text="-", bg='#0a0a0a',
                           fg=C['accent'], font=self.f_mono_s, anchor='e')
            val.pack(side=tk.RIGHT)
            self.overlay_values[key] = (val, fmt)
 
    def _build_panel(self, parent):
        """Two-tab right panel — Tab A: Controls, Tab B: Servos.
        Replaces the Canvas/scroll approach which clipped content silently."""
        outer = tk.Frame(parent, bg=C['panel'], width=PANEL_W)
        outer.pack(side=tk.RIGHT, fill=tk.Y)
        outer.pack_propagate(False)
 
        # ── Tab bar ──────────────────────────────────────────────────────
        tab_bar = tk.Frame(outer, bg=C['base'], height=36)
        tab_bar.pack(fill=tk.X)
        tab_bar.pack_propagate(False)
 
        self._tab_pages = {}
 
        def _show_tab(name):
            for n, (page, btn) in self._tab_pages.items():
                if n == name:
                    page.pack(fill=tk.BOTH, expand=True)
                    btn.configure(bg=C['card'], fg=C['pri'])
                else:
                    page.pack_forget()
                    btn.configure(bg=C['base'], fg=C['muted'])
 
        for label, key in [("CONTROLS", 'controls'), ("SERVOS", 'servos')]:
            b = tk.Button(
                tab_bar, text=label,
                bg=C['card'] if key == 'controls' else C['base'],
                fg=C['pri']  if key == 'controls' else C['muted'],
                font=self.f_small, relief='flat', bd=0,
                cursor='hand2',
                activebackground=C['btn_hl'], activeforeground=C['pri'],
                command=lambda k=key: _show_tab(k))
            b.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6)
 
            page = tk.Frame(outer, bg=C['panel'])
            self._tab_pages[key] = (page, b)
 
        tk.Frame(outer, bg=C['border'], height=1).pack(fill=tk.X)
 
        # show first tab
        self._tab_pages['controls'][0].pack(fill=tk.BOTH, expand=True)
        self._fill_controls(self._tab_pages['controls'][0])
        self._fill_servos(self._tab_pages['servos'][0])
 
    def _fill_controls(self, p):
        """Tab A: View / Winch / Motors / Relays — all fits in 556px."""
        PAD = 6
 
        # ── View ─────────────────────────────────────────────────────────
        _section_lbl(p, "VIEW")
        vrow = tk.Frame(p, bg=C['panel'])
        vrow.pack(fill=tk.X, padx=PAD, pady=2)
 
        self.cam_btn = _btn(
            vrow, "[O] CAM", self.toggle_camera,
            bg=C['green'] if self.video_enabled.get() else C['btn'],
            fg=C['base']  if self.video_enabled.get() else C['pri'],
            font=self.f_btn)
        self.cam_btn.pack(side=tk.LEFT, fill=tk.X, expand=True,
                          ipady=7, padx=(0, 2))
 
        self.ovrl_btn = _btn(
            vrow, "[+] OVRL", self.toggle_overlay,
            bg=C['green'] if self.overlay_enabled.get() else C['btn'],
            fg=C['base']  if self.overlay_enabled.get() else C['pri'],
            font=self.f_btn)
        self.ovrl_btn.pack(side=tk.LEFT, fill=tk.X, expand=True,
                           ipady=7, padx=(2, 0))
 
        _sep(p)
 
        # ── Winch ─────────────────────────────────────────────────────────
        _section_lbl(p, "WINCH")
        wr = tk.Frame(p, bg=C['panel'])
        wr.pack(fill=tk.X, padx=PAD, pady=2)
        _btn(wr, "/\\ UP",   lambda: self._emit('winch_up'),
             font=self.f_btn).pack(
             side=tk.LEFT, fill=tk.X, expand=True, ipady=9, padx=(0, 2))
        _btn(wr, "\\/ DOWN", lambda: self._emit('winch_down'),
             font=self.f_btn).pack(
             side=tk.LEFT, fill=tk.X, expand=True, ipady=9, padx=(2, 0))
 
        _sep(p)
 
        # ── Motors ────────────────────────────────────────────────────────
        _section_lbl(p, "MOTORS")
        for la, lb, ca, cb in [
            ("/\\ ARM",   "\\/ ARM",   "MOTOR_ARM_UP",          "MOTOR_ARM_DOWN"),
            ("/\\ CLAMP", "\\/ CLAMP", "MOTOR_CLAMP_OPEN",      "MOTOR_CLAMP_CLOSE"),
            ("/\\ ACT",   "\\/ ACT",   "MOTOR_ACTUATOR_EXTEND", "MOTOR_ACTUATOR_RETRACT"),
        ]:
            r = tk.Frame(p, bg=C['panel'])
            r.pack(fill=tk.X, padx=PAD, pady=2)
            _btn(r, la, lambda c=ca: self._motor(c),
                 font=self.f_btn).pack(
                 side=tk.LEFT, fill=tk.X, expand=True, ipady=7, padx=(0, 2))
            _btn(r, lb, lambda c=cb: self._motor(c),
                 font=self.f_btn).pack(
                 side=tk.LEFT, fill=tk.X, expand=True, ipady=7, padx=(2, 0))
 
        self.pump_btn = _btn(p, "[*] PUMP OFF", self._toggle_pump,
                             font=self.f_btn)
        self.pump_btn.pack(fill=tk.X, padx=PAD, pady=2, ipady=7)
 
        _sep(p)
 
        # ── Relays ────────────────────────────────────────────────────────
        _section_lbl(p, "RELAYS")
        rr = tk.Frame(p, bg=C['panel'])
        rr.pack(fill=tk.X, padx=PAD, pady=2)
 
        self.lights_btn = _btn(rr, "[L] LIGHTS", self._toggle_lights,
                               font=self.f_btn)
        self.lights_btn.pack(side=tk.LEFT, fill=tk.X, expand=True,
                             ipady=9, padx=(0, 2))
 
        self.valve_btn = _btn(rr, "[V] VALVE", self._toggle_valve,
                              font=self.f_btn)
        self.valve_btn.pack(side=tk.LEFT, fill=tk.X, expand=True,
                            ipady=9, padx=(2, 0))
 
    def _fill_servos(self, p):
        """Tab B: Servo angle presets for all 7 servos."""
        PAD = 6
        _section_lbl(p, "SERVOS")
        for name, idx in [
            ("SG90",    0),
            ("MG996-1", 1), ("MG996-2", 2), ("MG996-3", 3),
            ("MG996-4", 4), ("MG996-5", 5), ("MG996-6", 6),
        ]:
            r = tk.Frame(p, bg=C['panel'])
            r.pack(fill=tk.X, padx=PAD, pady=3)
            tk.Label(r, text=name, bg=C['panel'], fg=C['pri'],
                     font=self.f_small, width=7, anchor='w').pack(side=tk.LEFT)
            for angle, lbl in [(0,"0"),(45,"45"),(90,"90"),(135,"135"),(180,"180")]:
                _btn(r, lbl,
                     lambda i=idx, a=angle: self._servo(i, a),
                     font=self.f_small).pack(
                     side=tk.LEFT, fill=tk.X, expand=True, ipady=5, padx=1)
 
    # ── Button callbacks ──────────────────────────────────────────────────
 
    def _emit(self, t, **kw):
        self.add_event({'type': t, **kw})
 
    def _motor(self, cmd):
        self._emit('motor_cmd', cmd=cmd)
 
    def _servo(self, idx, angle):
        self._emit('servo_control', servo_idx=idx, angle=angle)
 
    def _toggle_pump(self):
        self._pump_on = not self._pump_on
        if self._pump_on:
            self.pump_btn.configure(text="[*] PUMP ON",
                                    bg=C['green'], fg=C['base'])
        else:
            self.pump_btn.configure(text="[*] PUMP OFF",
                                    bg=C['btn'], fg=C['pri'])
        self._emit('motor_cmd', cmd='MOTOR_PUMP_TOGGLE')
 
    def _toggle_lights(self):
        self._lights_on = not self._lights_on
        self.lights_btn.configure(
            bg=C['amber'] if self._lights_on else C['btn'],
            fg=C['base']  if self._lights_on else C['pri'])
        self._emit('relay_cmd', cmd='RELAY_LIGHTS_TOGGLE', state=self._lights_on)
 
    def _toggle_valve(self):
        self._valve_on = not self._valve_on
        self.valve_btn.configure(
            bg=C['accent'] if self._valve_on else C['btn'],
            fg=C['base']   if self._valve_on else C['pri'])
        self._emit('relay_cmd', cmd='RELAY_SOLENOID_TOGGLE', state=self._valve_on)
 
    def toggle_camera(self):
        current = not self.video_enabled.get()
        self.video_enabled.set(current)
        self.cam_btn.configure(
            bg=C['green'] if current else C['btn'],
            fg=C['base']  if current else C['pri'])
        self._emit('toggle_camera')
        if current:
            self.start_camera()
        else:
            self.stop_camera()
 
    def toggle_overlay(self):
        current = not self.overlay_enabled.get()
        self.overlay_enabled.set(current)
        self.ovrl_btn.configure(
            bg=C['green'] if current else C['btn'],
            fg=C['base']  if current else C['pri'])
        if current:
            self.overlay_frame.lift()
        else:
            self.overlay_frame.lower()
        self._emit('toggle_overlay')
 
    # ── GStreamer appsink ─────────────────────────────────────────────────
 
    def start_camera(self):
        if self.camera_running:
            return
        if not GST_AVAILABLE:
            self.cam_label.configure(text="GSTREAMER NOT INSTALLED")
            return
        if not PIL_AVAILABLE:
            self.cam_label.configure(text="PIL NOT INSTALLED")
            return
 
        port = self.video_port
        w, h = self.RECV_W, self.RECV_H
 
        ps = (
            f'udpsrc port={port} '
            f'caps="application/x-rtp,media=video,clock-rate=90000,'
            f'encoding-name=H264,payload=96" '
            f'! rtph264depay '
            f'! queue max-size-buffers=2 leaky=downstream '
            f'! avdec_h264 '
            f'! videoscale ! videoconvert '
            f'! video/x-raw,format=RGB,width={w},height={h} '
            f'! appsink name=sink emit-signals=true drop=true max-buffers=1 sync=false'
        )
 
        try:
            self.gst_pipeline = Gst.parse_launch(ps)
        except Exception as e:
            print(f"GStreamer parse error: {e}")
            self.cam_label.configure(text="PIPELINE ERROR")
            return
 
        sink = self.gst_pipeline.get_by_name('sink')
        sink.connect('new-sample', self._on_new_sample)
 
        bus = self.gst_pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect('message::error', self._on_gst_error)
        bus.connect('message::eos',   self._on_gst_eos)
 
        if self.gst_pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            print("GStreamer: failed to reach PLAYING state")
            self.cam_label.configure(text="PIPELINE FAILED")
            self.gst_pipeline = None
            return
 
        self.camera_running = True
        self.cam_label.configure(image='', text="WAITING FOR STREAM...")
        print("Camera receiver started (appsink)")
 
    def _on_new_sample(self, sink):
        # FIX #2 (cont): bail out immediately if stop_camera() has been called
        if not self.camera_running:
            return Gst.FlowReturn.EOS
        sample = sink.emit('pull-sample')
        if not sample:
            return Gst.FlowReturn.ERROR
        buf  = sample.get_buffer()
        s    = sample.get_caps().get_structure(0)
        w, h = s.get_value('width'), s.get_value('height')
        ok, mi = buf.map(Gst.MapFlags.READ)
        if not ok:
            return Gst.FlowReturn.ERROR
        try:
            img = Image.frombytes('RGB', (w, h), bytes(mi.data))
            # FIX #3: resize to CAMERA_H (452, 16:9) not CONTENT_H (556, wrong AR)
            if (w, h) != (CAMERA_W, CAMERA_H):
                img = img.resize((CAMERA_W, CAMERA_H), Image.Resampling.LANCZOS)
            with self.frame_lock:
                self.camera_pil = img
                # FIX #1: only schedule _show_frame if one isn't already queued.
                # Previously scheduled on every frame — at 30fps this flooded
                # the Tk event queue when the main thread was briefly busy.
                if not self.frame_pending:
                    self.frame_pending = True
                    self.root.after(0, self._show_frame)
        finally:
            buf.unmap(mi)
        return Gst.FlowReturn.OK
 
    def _show_frame(self):
        with self.frame_lock:
            if not self.frame_pending or self.camera_pil is None:
                return
            img = self.camera_pil
            self.frame_pending = False
        try:
            photo = ImageTk.PhotoImage(img)
            self.cam_label.configure(image=photo, text="")
            self.cam_label.image = photo
            self.camera_photo    = photo
        except Exception as e:
            print(f"Frame display error: {e}")
 
    def _on_gst_error(self, bus, msg):
        err, dbg = msg.parse_error()
        print(f"GStreamer error: {err.message} | {dbg}")
        self.cam_label.configure(image='', text="STREAM ERROR")
 
    def _on_gst_eos(self, bus, msg):
        self.cam_label.configure(image='', text="STREAM ENDED")
 
    def stop_camera(self):
        # FIX #2: set camera_running False BEFORE set_state(NULL).
        # _on_new_sample fires from GStreamer's streaming thread and checks nothing —
        # it can call self.root.after() after the pipeline is torn down.
        # Clearing the flag first means any in-flight callback sees it and bails out.
        self.camera_running = False
        if self.gst_pipeline:
            self.gst_pipeline.set_state(Gst.State.NULL)
            self.gst_pipeline = None
        self.cam_label.configure(image='', text="NO SIGNAL")
        self.camera_photo = None
 
    # ── Periodic tick (100 ms) ────────────────────────────────────────────
 
    def _tick(self):
        if not self.running:
            return
        try:
            self.clock_lbl.configure(text=time.strftime("%H:%M:%S"))
 
            # Status badge
            if self.current_state.get('emergency_stop'):
                self.status_badge.configure(text="[!!] E-STOP", fg=C['red'])
            elif self.current_state.get('running'):
                self.status_badge.configure(text="[*] ACTIVE",  fg=C['green'])
            else:
                self.status_badge.configure(text="[*] IDLE",    fg=C['amber'])
 
            # Winch badge
            wmap = {'forward': ("WINCH /\\", C['accent']),
                    'reverse': ("WINCH \\/", C['accent']),
                    'stop':    ("WINCH --", C['muted'])}
            wt, wc = wmap.get(
                self.current_state.get('winch_direction', 'stop'),
                ("WINCH --", C['muted']))
            self.winch_badge.configure(text=wt, fg=wc)
 
            # Liquid alert badge
            if self.current_state.get('liquid_detected'):
                self.liquid_badge.pack(side=tk.LEFT, padx=10)
            else:
                self.liquid_badge.pack_forget()
 
            # Telemetry overlay
            sensors = self.current_state.get('telemetry', {}).get('sensors', {})
            defaults = {
                'pressure_kpa':   0.0,
                'ph_level':       7.0,
                'current_amps_1': 0.0,
                'current_amps_2': 0.0,
            }
            for key, (lbl, fmt) in self.overlay_values.items():
                lbl.configure(text=fmt.format(sensors.get(key, defaults[key])))
 
            # Sync relay button colours from incoming telemetry state
            tele = self.current_state
            if 'relay_lights' in tele and tele['relay_lights'] != self._lights_on:
                self._lights_on = tele['relay_lights']
                self.lights_btn.configure(
                    bg=C['amber'] if self._lights_on else C['btn'],
                    fg=C['base']  if self._lights_on else C['pri'])
            if 'relay_valve' in tele and tele['relay_valve'] != self._valve_on:
                self._valve_on = tele['relay_valve']
                self.valve_btn.configure(
                    bg=C['accent'] if self._valve_on else C['btn'],
                    fg=C['base']   if self._valve_on else C['pri'])
 
        except Exception as e:
            print(f"Tick error: {e}")
 
        self.root.after(100, self._tick)
 
    # ── Public interface ──────────────────────────────────────────────────
 
    def update(self, new_state):
        """Called from background thread — atomic dict swap, thread-safe."""
        self.current_state = new_state.copy()
 
    def add_event(self, event):
        with self.event_lock:
            self.event_queue.append(event)
 
    def handle_events(self):
        with self.event_lock:
            events = self.event_queue.copy()
            self.event_queue.clear()
        return events
 
    def _exit_tap(self):
        """Two-tap exit: first tap arms (button turns red + shows CONFIRM),
        second tap within 3 seconds exits. Resets if no second tap."""
        if self._exit_armed:
            # Second tap — confirmed, exit
            self.on_close()
        else:
            # First tap — arm it
            self._exit_armed = True
            self.exit_btn.configure(text="EXIT?", bg=C['red'], fg='white')
            # Auto-disarm after 3 seconds
            if self._exit_timer:
                self.root.after_cancel(self._exit_timer)
            self._exit_timer = self.root.after(3000, self._exit_disarm)
 
    def _exit_disarm(self):
        """Reset exit button back to idle state."""
        self._exit_armed = False
        self._exit_timer = None
        self.exit_btn.configure(text="X", bg=C['panel'], fg=C['muted'])
 
    def on_close(self):
        self.stop_camera()
        self.running = False
        self.root.quit()
 
    def run(self):
        if self.enabled:
            try:
                self.root.mainloop()
            except Exception:
                pass
 
    def cleanup(self):
        self.stop_camera()
        self.running = False
        if self.enabled:
            try:
                self.root.quit()
                self.root.destroy()
            except Exception:
                pass