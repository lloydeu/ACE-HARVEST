"""
Display Output Handler - RPi4 Bottom
Dark industrial UI - GTK4 - Wayland native fullscreen
gtk4paintablesink camera - hardware decode via v4l2h264dec

Install (once):
    sudo apt install python3-gi gir1.2-gtk-4.0 \
         gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 \
         gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
         gstreamer1.0-libav gstreamer1.0-gtk3
"""

import threading
import time

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Gdk, GLib

try:
    from config import config, state
except ImportError:
    class _Cfg:
        _d = {'video_enabled': False, 'display_overlay': True, 'video_port': 5001}
        def get(self, k, default=None): return self._d.get(k, default)
    config = _Cfg()
    state  = {}

try:
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst
    Gst.init(None)
    GST_AVAILABLE = True
except Exception as e:
    GST_AVAILABLE = False
    print(f"Warning: GStreamer unavailable ({e})")

# ── Layout constants ──────────────────────────────────────────────────────
PANEL_W  = 220
TOPBAR_H = 44

# ── CSS design tokens ─────────────────────────────────────────────────────
CSS = b"""
* { font-family: monospace; }

window, .root-bg        { background-color: #0d0d0d; }
.topbar                 { background-color: #141414; border-bottom: 1px solid #272727; }
.panel                  { background-color: #141414; border-left: 1px solid #272727; }
.tab-bar                { background-color: #0d0d0d; }
.tab-btn                { background-color: #0d0d0d; color: #4a4a4a;
                          border: none; border-radius: 0; padding: 6px 4px; }
.tab-btn:hover          { background-color: #1c1c1c; }
.tab-btn.active         { background-color: #1c1c1c; color: #e2e2e2; }
.section-label          { color: #4a4a4a; font-size: 9px; font-weight: bold;
                          padding: 6px 10px 2px 10px; }
.divider-h              { background-color: #272727; min-height: 1px; margin: 4px; }
.cam-bg                 { background-color: #090909; }
.overlay-bg             { background-color: #0a0a0a; border: 1px solid #272727; }
.overlay-label          { color: #4a4a4a; font-size: 9px; }
.overlay-value          { color: #00c8ff; font-size: 9px; font-family: monospace; }
.status-idle            { color: #f59e0b; font-weight: bold; font-size: 13px; }
.status-active          { color: #22c55e; font-weight: bold; font-size: 13px; }
.status-estop           { color: #ef4444; font-weight: bold; font-size: 13px; }
.liquid-badge           { color: #ef4444; font-size: 11px; }
.winch-badge            { color: #4a4a4a; font-size: 9px; }
.winch-active           { color: #00c8ff; font-size: 9px; }
.clock                  { color: #4a4a4a; font-size: 9px; font-family: monospace; }
.no-signal              { color: #4a4a4a; font-size: 13px; font-weight: bold; }

.btn                    { background-color: #505050; color: #000000;
                          border: 3px solid #ffffff; border-radius: 3px;
                          padding: 6px 10px; font-size: 12px; font-weight: bold; }
.btn:hover              { background-color: #707070; border-color: #ffff99; color: #000000; }
.btn:active             { background-color: #606060; border-color: #ffff99; color: #000000; }
.btn-on-green           { background-color: #00aa00; color: #000000; border-color: #00ff00; }
.btn-on-green:hover     { background-color: #00dd00; border-color: #ffff00; color: #000000; }
.btn-on-amber           { background-color: #ffaa00; color: #000000; border-color: #ffff00; }
.btn-on-amber:hover     { background-color: #ffdd00; border-color: #ffffff; color: #000000; }
.btn-on-cyan            { background-color: #00aaff; color: #000000; border-color: #00ffff; }
.btn-on-cyan:hover      { background-color: #00ddff; border-color: #ffffff; color: #000000; }
.btn-exit               { background-color: #141414; color: #4a4a4a;
                          border: none; border-radius: 0;
                          font-size: 13px; font-weight: bold; padding: 0 12px; }
.btn-exit:hover         { background-color: #2a0a0a; color: #ef4444; }
.btn-exit-armed         { background-color: #ef4444; color: white; }
"""

def _css_provider():
    p = Gtk.CssProvider()
    p.load_from_data(CSS)
    return p

_PROVIDER = None

def _add_class(widget, *classes):
    ctx = widget.get_style_context()
    for c in classes:
        ctx.add_class(c)

def _remove_class(widget, *classes):
    ctx = widget.get_style_context()
    for c in classes:
        ctx.remove_class(c)

def _set_class(widget, cls, on, off=None):
    _add_class(widget, cls) if on else _remove_class(widget, cls)
    if off:
        _remove_class(widget, off) if on else _add_class(widget, off)


def _flat_btn(label, callback=None, css_classes=('btn',)):
    """Standard flat dark button."""
    b = Gtk.Button(label=label)
    b.set_hexpand(True)
    b.set_vexpand(False)
    for c in css_classes:
        _add_class(b, c)
    if callback:
        b.connect('clicked', callback)
    return b


def _section(label):
    lbl = Gtk.Label(label=label)
    lbl.set_xalign(0)
    _add_class(lbl, 'section-label')
    return lbl


def _hsep():
    sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
    _add_class(sep, 'divider-h')
    return sep


# ══════════════════════════════════════════════════════════════════════════
class DisplayOutput:
    """GTK4 dark industrial UI - Wayland native."""

    def __init__(self, width=None, height=None):
        self.enabled = False

        # shared state
        self.current_state = {}
        self.event_queue   = []
        self.event_lock    = threading.Lock()
        self.running       = False

        # camera state
        self.video_port     = config.get('video_port', 5001)
        self.camera_running = False
        self.gst_pipeline   = None

        # relay/pump visual state
        self._lights_on = False
        self._valve_on  = False
        self._pump_on   = False

        # exit confirm
        self._exit_armed = False
        self._exit_timer = None

        # video toggle
        self._video_on   = config.get('video_enabled',   False)
        self._overlay_on = config.get('display_overlay', True)

        # build GTK app
        self.app = Gtk.Application(application_id='com.robot.bottom')
        self.app.connect('activate', self._on_activate)

    # ── App activate ──────────────────────────────────────────────────────

    def _on_activate(self, app):
        global _PROVIDER
        _PROVIDER = _css_provider()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), _PROVIDER,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.win = Gtk.ApplicationWindow(application=app)
        self.win.set_title("RPi4 Bottom")
        self.win.fullscreen()
        self.win.connect('close-request', self._on_close_request)

        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        _add_class(root_box, 'root-bg')
        self.win.set_child(root_box)

        self._build_topbar(root_box)
        self._build_body(root_box)

        self.win.present()
        self.running = True
        self.enabled = True

        GLib.timeout_add(100, self._tick)

        # Autostart camera if configured
        if config.get('video_enabled', False):
            GLib.idle_add(self._autostart_camera)

        print("Display ready - GTK4 Wayland")

    def _autostart_camera(self):
        self.start_camera()
        self._video_on = True
        _add_class(self.cam_btn, 'btn-on-green')
        return GLib.SOURCE_REMOVE

    # ── Topbar ────────────────────────────────────────────────────────────

    def _build_topbar(self, parent):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        bar.set_size_request(-1, TOPBAR_H)
        _add_class(bar, 'topbar')
        parent.append(bar)

        # status badge
        self.status_lbl = Gtk.Label(label="[*] IDLE")
        _add_class(self.status_lbl, 'status-idle')
        self.status_lbl.set_margin_start(14)
        self.status_lbl.set_margin_end(8)
        bar.append(self.status_lbl)

        # liquid badge (hidden until triggered)
        self.liquid_lbl = Gtk.Label(label="[!] LIQUID DETECTED")
        _add_class(self.liquid_lbl, 'liquid-badge')
        self.liquid_lbl.set_margin_start(8)
        self.liquid_lbl.set_visible(False)
        bar.append(self.liquid_lbl)

        # spacer
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        bar.append(spacer)

        # clock
        self.clock_lbl = Gtk.Label(label="")
        _add_class(self.clock_lbl, 'clock')
        self.clock_lbl.set_margin_end(16)
        bar.append(self.clock_lbl)

        # winch badge
        self.winch_lbl = Gtk.Label(label="WINCH --")
        _add_class(self.winch_lbl, 'winch-badge')
        self.winch_lbl.set_margin_end(14)
        bar.append(self.winch_lbl)

        # separator
        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep.set_margin_top(8)
        sep.set_margin_bottom(8)
        bar.append(sep)

        # exit button
        self.exit_btn = Gtk.Button(label="X")
        _add_class(self.exit_btn, 'btn-exit')
        self.exit_btn.set_size_request(44, TOPBAR_H)
        self.exit_btn.connect('clicked', self._on_exit_tap)
        bar.append(self.exit_btn)

    # ── Body ──────────────────────────────────────────────────────────────

    def _build_body(self, parent):
        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        body.set_vexpand(True)
        parent.append(body)

        # camera area (expands to fill remaining width)
        self._build_camera_area(body)

        # right panel (fixed width)
        panel_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        panel_box.set_size_request(PANEL_W, -1)
        panel_box.set_vexpand(True)
        _add_class(panel_box, 'panel')
        body.append(panel_box)
        self._build_panel(panel_box)

    def _build_camera_area(self, parent):
        overlay = Gtk.Overlay()
        overlay.set_hexpand(True)
        overlay.set_vexpand(True)
        _add_class(overlay, 'cam-bg')
        parent.append(overlay)

        # Camera picture widget
        self.cam_picture = Gtk.Picture()
        self.cam_picture.set_hexpand(True)
        self.cam_picture.set_vexpand(True)
        self.cam_picture.set_content_fit(Gtk.ContentFit.FILL)
        _add_class(self.cam_picture, 'cam-bg')
        overlay.set_child(self.cam_picture)

        # "NO SIGNAL" label (shown when no frame)
        self.no_signal_lbl = Gtk.Label(label="NO SIGNAL")
        _add_class(self.no_signal_lbl, 'no-signal')
        self.no_signal_lbl.set_halign(Gtk.Align.CENTER)
        self.no_signal_lbl.set_valign(Gtk.Align.CENTER)
        overlay.add_overlay(self.no_signal_lbl)

        # Telemetry overlay (bottom-left)
        self._build_overlay(overlay)

    def _build_overlay(self, overlay_container):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_halign(Gtk.Align.START)
        box.set_valign(Gtk.Align.END)
        box.set_margin_start(8)
        box.set_margin_bottom(8)
        box.set_size_request(230, -1)
        _add_class(box, 'overlay-bg')
        box.set_visible(self._overlay_on)
        self.overlay_box = box
        overlay_container.add_overlay(box)

        self.overlay_values = {}
        for label, key, fmt in [
            ('PRESSURE', 'pressure_kpa', '{:.1f} kPa'),
            ('BATTERY',  'battery_percent', '{:.0f}%'),
        ]:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            row.set_margin_start(8)
            row.set_margin_end(8)
            row.set_margin_top(2)
            row.set_margin_bottom(2)
            box.append(row)

            lbl = Gtk.Label(label=label)
            lbl.set_xalign(0)
            lbl.set_hexpand(True)
            _add_class(lbl, 'overlay-label')
            row.append(lbl)

            val = Gtk.Label(label="-")
            val.set_xalign(1)
            _add_class(val, 'overlay-value')
            row.append(val)

            self.overlay_values[key] = (val, fmt)

    # ── Right panel ───────────────────────────────────────────────────────

    def _build_panel(self, parent):
        # Tab bar
        tab_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        _add_class(tab_bar, 'tab-bar')
        parent.append(tab_bar)

        self._tab_pages = {}
        self._tab_btns  = {}
        notebook_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        notebook_box.set_vexpand(True)
        parent.append(notebook_box)

        def _show_tab(name):
            for n, page in self._tab_pages.items():
                page.set_visible(n == name)
                btn = self._tab_btns[n]
                _set_class(btn, 'active', n == name)

        for label, key in [("CONTROLS", 'controls'), ("SERVOS", 'servos')]:
            btn = Gtk.Button(label=label)
            btn.set_hexpand(True)
            _add_class(btn, 'tab-btn')
            if key == 'controls':
                _add_class(btn, 'active')
            btn.connect('clicked', lambda b, k=key: _show_tab(k))
            tab_bar.append(btn)
            self._tab_btns[key] = btn

            page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            page.set_vexpand(True)
            page.set_visible(key == 'controls')
            notebook_box.append(page)
            self._tab_pages[key] = page

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        parent.append(sep)

        self._fill_controls(self._tab_pages['controls'])
        self._fill_servos(self._tab_pages['servos'])

    def _fill_controls(self, p):
        PAD = 6

        # VIEW
        p.append(_section("VIEW"))
        view_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        view_row.set_margin_start(PAD)
        view_row.set_margin_end(PAD)
        view_row.set_margin_bottom(4)
        p.append(view_row)

        self.cam_btn = _flat_btn("[O] CAM", self._toggle_camera)
        if self._video_on:
            _add_class(self.cam_btn, 'btn-on-green')
        view_row.append(self.cam_btn)

        self.ovrl_btn = _flat_btn("[+] OVRL", self._toggle_overlay)
        if self._overlay_on:
            _add_class(self.ovrl_btn, 'btn-on-green')
        view_row.append(self.ovrl_btn)

        p.append(_hsep())

        # WINCH
        p.append(_section("WINCH"))
        wr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        wr.set_margin_start(PAD); wr.set_margin_end(PAD); wr.set_margin_bottom(4)
        p.append(wr)
        wr.append(_flat_btn("UP",   lambda b: self._emit('winch_up')))
        wr.append(_flat_btn("DOWN", lambda b: self._emit('winch_down')))

        p.append(_hsep())

        # MOTORS
        p.append(_section("MOTORS"))
        for la, lb, ca, cb in [
            ("ARM UP",   "ARM DOWN",   "MOTOR_ARM_UP",          "MOTOR_ARM_DOWN"),
            ("CLAMP OPEN", "CLAMP CLOSE", "MOTOR_CLAMP_OPEN",      "MOTOR_CLAMP_CLOSE"),
            ("ACT EXTEND",   "ACT RETRACT",   "MOTOR_ACTUATOR_EXTEND", "MOTOR_ACTUATOR_RETRACT"),
        ]:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            row.set_margin_start(PAD); row.set_margin_end(PAD); row.set_margin_bottom(4)
            p.append(row)
            row.append(_flat_btn(la, lambda b, c=ca: self._motor(c)))
            row.append(_flat_btn(lb, lambda b, c=cb: self._motor(c)))

        self.pump_btn = _flat_btn("[*] PUMP OFF", self._toggle_pump)
        self.pump_btn.set_margin_start(PAD)
        self.pump_btn.set_margin_end(PAD)
        self.pump_btn.set_margin_bottom(4)
        p.append(self.pump_btn)

        p.append(_hsep())

        # RELAYS
        p.append(_section("RELAYS"))
        rr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        rr.set_margin_start(PAD); rr.set_margin_end(PAD); rr.set_margin_bottom(4)
        p.append(rr)

        self.lights_btn = _flat_btn("[L] LIGHTS", self._toggle_lights)
        rr.append(self.lights_btn)

        self.valve_btn = _flat_btn("[V] VALVE", self._toggle_valve)
        rr.append(self.valve_btn)

    def _fill_servos(self, p):
        PAD = 6
        p.append(_section("SERVOS"))
        for name, idx in [
            ("SG90",    0),
            ("MG996-1", 1), ("MG996-2", 2), ("MG996-3", 3),
            ("MG996-4", 4), ("MG996-5", 5), ("MG996-6", 6),
        ]:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
            row.set_margin_start(PAD); row.set_margin_end(PAD); row.set_margin_bottom(3)
            p.append(row)

            name_lbl = Gtk.Label(label=name)
            name_lbl.set_size_request(56, -1)
            name_lbl.set_xalign(0)
            _add_class(name_lbl, 'overlay-label')
            row.append(name_lbl)

            for angle, lbl in [(0,"0"),(45,"45"),(90,"90"),(135,"135"),(180,"180")]:
                b = Gtk.Button(label=lbl)
                b.set_hexpand(True)
                _add_class(b, 'btn')
                b.connect('clicked', lambda btn, i=idx, a=angle: self._servo(i, a))
                row.append(b)

    # ── Button callbacks ──────────────────────────────────────────────────

    def _emit(self, t, **kw):
        self.add_event({'type': t, **kw})

    def _motor(self, cmd):
        self._emit('motor_cmd', cmd=cmd)

    def _servo(self, idx, angle):
        self._emit('servo_control', servo_idx=idx, angle=angle)

    def _toggle_pump(self, btn):
        self._pump_on = not self._pump_on
        if self._pump_on:
            btn.set_label("[*] PUMP ON")
            _add_class(btn, 'btn-on-green')
        else:
            btn.set_label("[*] PUMP OFF")
            _remove_class(btn, 'btn-on-green')
        self._emit('motor_cmd', cmd='MOTOR_PUMP_TOGGLE')

    def _toggle_lights(self, btn):
        self._lights_on = not self._lights_on
        _set_class(btn, 'btn-on-amber', self._lights_on)
        self._emit('relay_cmd', cmd='RELAY_LIGHTS_TOGGLE', state=self._lights_on)

    def _toggle_valve(self, btn):
        self._valve_on = not self._valve_on
        _set_class(btn, 'btn-on-cyan', self._valve_on)
        self._emit('relay_cmd', cmd='RELAY_SOLENOID_TOGGLE', state=self._valve_on)

    def _toggle_camera(self, btn):
        self._video_on = not self._video_on
        _set_class(btn, 'btn-on-green', self._video_on)
        self._emit('toggle_camera')
        if self._video_on:
            self.start_camera()
        else:
            self.stop_camera()

    def toggle_camera(self):
        self._toggle_camera(self.cam_btn)

    def _toggle_overlay(self, btn):
        self._overlay_on = not self._overlay_on
        _set_class(btn, 'btn-on-green', self._overlay_on)
        self.overlay_box.set_visible(self._overlay_on)
        self._emit('toggle_overlay')

    def toggle_overlay(self):
        self._toggle_overlay(self.ovrl_btn)

    # ── Exit ──────────────────────────────────────────────────────────────

    def _on_exit_tap(self, btn):
        if self._exit_armed:
            self.cleanup()
        else:
            self._exit_armed = True
            _remove_class(btn, 'btn-exit')
            _add_class(btn,    'btn-exit-armed')
            btn.set_label("EXIT?")
            if self._exit_timer:
                GLib.source_remove(self._exit_timer)
            self._exit_timer = GLib.timeout_add(3000, self._exit_disarm)

    def _exit_disarm(self):
        self._exit_armed = False
        self._exit_timer = None
        _remove_class(self.exit_btn, 'btn-exit-armed')
        _add_class(self.exit_btn,    'btn-exit')
        self.exit_btn.set_label("X")
        return GLib.SOURCE_REMOVE

    def _on_close_request(self, win):
        self.cleanup()
        return True

    # ── GStreamer appsink camera ───────────────────────────────────────────

    def start_camera(self):
        if self.camera_running:
            return
        if not GST_AVAILABLE:
            self.no_signal_lbl.set_label("GSTREAMER NOT INSTALLED")
            return

        port = self.video_port

        decoder = "v4l2h264dec" if Gst.ElementFactory.find("v4l2h264dec") else "avdec_h264"
        print(f"Camera decoder: {decoder}")

        ps = (
            f'udpsrc port={port} '
            f'caps="application/x-rtp,media=video,clock-rate=90000,'
            f'encoding-name=H264,payload=96" '
            f'! rtph264depay '
            f'! h264parse config-interval=1 '
            f'! queue leaky=downstream max-size-buffers=2 '
            f'! {decoder} '
            f'! videoconvert '
            f'! gtk4paintablesink name=gtksink sync=false'
        )

        try:
            self.gst_pipeline = Gst.parse_launch(ps)
        except Exception as e:
            print(f"GStreamer pipeline error: {e}")
            self.no_signal_lbl.set_label("PIPELINE ERROR")
            return

        # Wire gtk4paintablesink's paintable directly to the GtkPicture
        gtksink = self.gst_pipeline.get_by_name('gtksink')
        paintable = gtksink.get_property('paintable')
        self.cam_picture.set_paintable(paintable)

        bus = self.gst_pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect('message::error', self._on_gst_error)
        bus.connect('message::eos',   self._on_gst_eos)

        if self.gst_pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            print("GStreamer: failed to reach PLAYING state")
            self.no_signal_lbl.set_label("PIPELINE FAILED")
            self.gst_pipeline = None
            return

        self.camera_running = True
        self.no_signal_lbl.set_label("WAITING FOR STREAM...")
        # hide no-signal label once paintable is connected
        GLib.timeout_add(2000, self._check_stream_started)
        print("Camera started (gtk4paintablesink + hardware decode)")

    def _check_stream_started(self):
        """Hide the no-signal label after 2s if pipeline is running."""
        if self.camera_running:
            self.no_signal_lbl.set_visible(False)
        return GLib.SOURCE_REMOVE

    def _on_gst_error(self, bus, msg):
        err, dbg = msg.parse_error()
        print(f"GStreamer error: {err.message} | {dbg}")
        GLib.idle_add(lambda: (
            self.no_signal_lbl.set_label("STREAM ERROR"),
            self.no_signal_lbl.set_visible(True)
        ) and GLib.SOURCE_REMOVE)

    def _on_gst_eos(self, bus, msg):
        GLib.idle_add(lambda: (
            self.no_signal_lbl.set_label("STREAM ENDED"),
            self.no_signal_lbl.set_visible(True)
        ) and GLib.SOURCE_REMOVE)

    def stop_camera(self):
        self.camera_running = False
        if self.gst_pipeline:
            self.gst_pipeline.set_state(Gst.State.NULL)
            self.gst_pipeline = None
        GLib.idle_add(self._reset_camera_ui)

    def _reset_camera_ui(self):
        self.cam_picture.set_paintable(None)
        self.no_signal_lbl.set_label("NO SIGNAL")
        self.no_signal_lbl.set_visible(True)
        return GLib.SOURCE_REMOVE

    # ── Periodic tick (100ms) ─────────────────────────────────────────────

    def _tick(self):
        if not self.running:
            return GLib.SOURCE_REMOVE
        try:
            # Clock
            self.clock_lbl.set_label(time.strftime("%H:%M:%S"))

            # Status badge
            if self.current_state.get('emergency_stop'):
                self.status_lbl.set_label("[!!] E-STOP")
                self.status_lbl.get_style_context().remove_class('status-idle')
                self.status_lbl.get_style_context().remove_class('status-active')
                self.status_lbl.get_style_context().add_class('status-estop')
            elif self.current_state.get('running'):
                self.status_lbl.set_label("[*] ACTIVE")
                self.status_lbl.get_style_context().remove_class('status-idle')
                self.status_lbl.get_style_context().remove_class('status-estop')
                self.status_lbl.get_style_context().add_class('status-active')
            else:
                self.status_lbl.set_label("[*] IDLE")
                self.status_lbl.get_style_context().remove_class('status-active')
                self.status_lbl.get_style_context().remove_class('status-estop')
                self.status_lbl.get_style_context().add_class('status-idle')

            # Winch badge
            winch = self.current_state.get('winch_direction', 'stop')
            wmap  = {'forward': 'WINCH /\\', 'reverse': 'WINCH \\/', 'stop': 'WINCH --'}
            self.winch_lbl.set_label(wmap.get(winch, 'WINCH --'))
            _set_class(self.winch_lbl, 'winch-active', winch != 'stop', 'winch-badge')

            # Liquid badge
            self.liquid_lbl.set_visible(bool(self.current_state.get('liquid_detected')))

            # Telemetry overlay values
            sensors  = self.current_state.get('telemetry', {}).get('sensors', {})
            defaults = {'pressure_kpa': 0.0, 'ph_level': 7.0,
                        'current_amps_1': 0.0, 'battery_percent': 0.0}
            for key, (lbl, fmt) in self.overlay_values.items():
                lbl.set_label(fmt.format(sensors.get(key, defaults[key])))

            # Sync relay button colours from telemetry
            tele = self.current_state
            if 'relay_lights' in tele and tele['relay_lights'] != self._lights_on:
                self._lights_on = tele['relay_lights']
                _set_class(self.lights_btn, 'btn-on-amber', self._lights_on)
            if 'relay_valve' in tele and tele['relay_valve'] != self._valve_on:
                self._valve_on = tele['relay_valve']
                _set_class(self.valve_btn, 'btn-on-cyan', self._valve_on)

        except Exception as e:
            print(f"Tick error: {e}")

        return GLib.SOURCE_CONTINUE

    # ── Public interface ──────────────────────────────────────────────────

    def update(self, new_state):
        """Thread-safe state update from background thread."""
        self.current_state = new_state.copy()

    def add_event(self, event):
        with self.event_lock:
            self.event_queue.append(event)

    def handle_events(self):
        with self.event_lock:
            events = self.event_queue.copy()
            self.event_queue.clear()
        return events

    def run(self):
        import sys
        self.app.run(sys.argv[:1])

    def cleanup(self):
        self.running = False
        self.stop_camera()
        try:
            self.app.quit()
        except Exception:
            pass
