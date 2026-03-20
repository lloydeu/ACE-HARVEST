"""Display Output Handler - Full UI with Camera Feed (Tkinter + GStreamer)"""
import tkinter as tk
from tkinter import font as tkfont
import threading
import time
import subprocess
import os
import sys

try:
    from config import config, state
except ImportError:
    config = {'video_enabled': False, 'display_overlay': True, 'video_port': 5001}
    state = {}

# Try to import PIL for image handling
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("Warning: PIL not installed - camera will not display")

class DisplayOutput:
    """Full UI display - camera feed, telemetry overlay, touch buttons"""
    
    def __init__(self, width=800, height=480):
        try:
            # Create main window
            self.root = tk.Tk()
            self.root.title("RPi4 Bottom Controller")
            self.root.geometry(f"{width}x{height}")
            self.root.overrideredirect(True)
            self.root.configure(bg='#1e1e1e')
            self.root.attributes('-topmost', True)
            
            self.width = width
            self.height = height
            
            # Camera area
            self.camera_width = int(width * 0.7)
            self.camera_height = int(self.camera_width * 9 / 16)
            
            # Camera settings
            self.video_port = config.get('video_port', 5001)
            self.camera_process = None
            self.camera_running = False
            self.camera_thread = None
            self.camera_photo = None
            self.frame_ready = False
            
            # Fonts
            self.font_large = tkfont.Font(family='Arial', size=20, weight='bold')
            self.font_medium = tkfont.Font(family='Arial', size=14)
            self.font_small = tkfont.Font(family='Arial', size=10)
            
            # Variables
            self.video_enabled = tk.BooleanVar(value=config.get('video_enabled', False))
            self.overlay_enabled = tk.BooleanVar(value=config.get('display_overlay', True))
            
            # State
            self.current_state = {}
            self.event_queue = []
            self.event_lock = threading.Lock()
            self.running = True
            
            # Create UI
            self.create_ui()
            
            # Start update loop
            self.update_ui()
            
            self.enabled = True
            print("Display initialized with GStreamer support")
            
        except Exception as e:
            print(f"Display init failed: {e}")
            self.enabled = False
    
    def create_ui(self):
        """Create UI elements"""
        # Top frame
        top_frame = tk.Frame(self.root, bg='#2a2a2a', height=60)
        top_frame.pack(fill=tk.X, padx=5, pady=5)
        top_frame.pack_propagate(False)
        
        # Camera button
        self.camera_btn = tk.Button(top_frame, text="Camera",
                                   command=self.toggle_camera,
                                   bg='#2a6f2a' if self.video_enabled.get() else '#6f2a2a',
                                   fg='white', font=self.font_small, width=10)
        self.camera_btn.pack(side=tk.LEFT, padx=5, pady=10)
        
        # Overlay button
        self.overlay_btn = tk.Button(top_frame, text="Overlay",
                                    command=self.toggle_overlay,
                                    bg='#2a6f2a' if self.overlay_enabled.get() else '#6f2a2a',
                                    fg='white', font=self.font_small, width=10)
        self.overlay_btn.pack(side=tk.LEFT, padx=5, pady=10)
        
        # Clock
        self.clock_label = tk.Label(top_frame, text="",
                                   bg='#2a2a2a', fg='#00ffff',
                                   font=self.font_small)
        self.clock_label.pack(side=tk.RIGHT, padx=10, pady=10)
        
        # Main content
        content = tk.Frame(self.root, bg='#1e1e1e')
        content.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Camera frame
        self.camera_frame = tk.Frame(content, bg='#2a2a2a',
                                    width=self.camera_width, height=self.camera_height)
        self.camera_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.camera_frame.pack_propagate(False)
        
        self.camera_label = tk.Label(self.camera_frame,
                                     text="LIVE FEED\n(Camera disabled)",
                                     bg='#2a2a2a', fg='#6f6f6f',
                                     font=self.font_large)
        self.camera_label.pack(expand=True, fill=tk.BOTH)
        
        # Overlay frame (for telemetry)
        self.overlay_frame = tk.Frame(self.camera_frame, bg='#000000')
        self.overlay_frame.place(x=10, y=self.camera_height-130, width=250, height=120)
        
        self.overlay_texts = []
        for title in ["Pressure:", "pH:", "Current 1:", "Current 2:"]:
            frame = tk.Frame(self.overlay_frame, bg='#000000')
            frame.pack(fill=tk.X, padx=5, pady=2)
            
            tk.Label(frame, text=title, bg='#000000', fg='#00ffff',
                    font=self.font_small, width=8, anchor='w').pack(side=tk.LEFT)
            
            value = tk.Label(frame, text="0.0", bg='#000000', fg='#00ff00',
                           font=self.font_small, width=8, anchor='e')
            value.pack(side=tk.RIGHT)
            self.overlay_texts.append(value)
        
        # Control panel
        panel = tk.Frame(content, bg='#2a2a2a', width=int(self.width * 0.28))
        panel.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(5, 0))
        panel.pack_propagate(False)
        
        # Status
        status = tk.Frame(panel, bg='#353535')
        status.pack(fill=tk.X, padx=5, pady=5)
        
        self.status_label = tk.Label(status, text="SYSTEM IDLE",
                                    bg='#353535', fg='#ffff00',
                                    font=self.font_medium)
        self.status_label.pack(pady=5)
        
        self.winch_label = tk.Label(status, text="Winch: STOP",
                                   bg='#353535', fg='#cccccc',
                                   font=self.font_small)
        self.winch_label.pack(pady=2)
        
        self.liquid_label = tk.Label(status, text="",
                                    bg='#353535', fg='#00ffff',
                                    font=self.font_small)
        self.liquid_label.pack(pady=2)
        
        # Bind close
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
    
    # ========== GStreamer Camera Methods ==========
    
    def start_camera(self):
        """Start GStreamer pipeline to receive video stream"""
        if self.camera_running or not PIL_AVAILABLE:
            return
        
        try:
            print(f"Starting camera receiver on port {self.video_port}")
            self.camera_running = True
            
            # Start receiver thread
            self.camera_thread = threading.Thread(
                target=self.camera_receiver_thread,
                daemon=True
            )
            self.camera_thread.start()
            
            self.camera_label.configure(text="LIVE FEED\n(Waiting for stream...)")
            print("Camera receiver started")
            
        except Exception as e:
            print(f"Error starting camera: {e}")
            self.camera_running = False
    
    def camera_receiver_thread(self):
        """Thread to receive and decode H264 RTP stream"""
        try:
            # GStreamer pipeline to receive and decode
            pipeline = [
                'gst-launch-1.0', '-q', '-e',
                'udpsrc', f'port={self.video_port}',
                'caps=application/x-rtp,media=video,clock-rate=90000,encoding-name=H264',
                '!', 'rtph264depay',
              
                '!', 'avdec_h264',
                
                '!', 'autovideosink', 'sync=false'
            ]
            
            # Start process
            process = subprocess.Popen(
                pipeline,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0
            )
            
            self.camera_process = process
            for line in process.stderr:
                print(f"GStreamer: {line.strip()}")

            # Frame size (640x480 RGB)
            frame_size = 640 * 480 * 3
            
            while self.camera_running and self.running:
                try:
                    # Read frame from stdout
                    data = process.stdout.read(frame_size)
                    
                    if len(data) == frame_size and PIL_AVAILABLE:
                        # Convert to PIL Image
                        img = Image.frombytes('RGB', (640, 480), data)
                        
                        # Resize to fit camera area
                        img = img.resize((self.camera_width, self.camera_height),
                                        Image.Resampling.LANCZOS)
                        
                        # Convert to PhotoImage
                        self.camera_photo = ImageTk.PhotoImage(img)
                        self.frame_ready = True
                        
                        # Update UI
                        self.root.after(0, self.update_camera_image)
                    
                except Exception as e:
                    print(e)
                    time.sleep(0.01)
            
        except Exception as e:
            print(f"Camera receiver error: {e}")
        finally:
            if self.camera_process:
                self.camera_process.terminate()
    
    def update_camera_image(self):
        """Update camera image in UI"""
        if self.frame_ready and self.camera_photo:
            self.camera_label.configure(image=self.camera_photo, text="")
            self.camera_label.image = self.camera_photo
            self.frame_ready = False
    
    def stop_camera(self):
        """Stop camera receiver"""
        print("Stopping camera...")
        self.camera_running = False
        
        if self.camera_process:
            try:
                self.camera_process.terminate()
                self.camera_process.wait(timeout=2)
            except:
                self.camera_process.kill()
            self.camera_process = None
        
        self.camera_label.configure(text="LIVE FEED\n(Camera disabled)")
        print("Camera stopped")
    
    # ========== UI Methods ==========
    
    def on_close(self):
        """Handle window close"""
        self.stop_camera()
        self.running = False
        self.root.quit()
    
    def toggle_camera(self):
        """Toggle camera"""
        current = not self.video_enabled.get()
        self.video_enabled.set(current)
        self.camera_btn.configure(bg='#2a6f2a' if current else '#6f2a2a')
        self.add_event({'type': 'toggle_camera'})
        
        if current:
            self.start_camera()
        else:
            self.stop_camera()
    
    def toggle_overlay(self):
        """Toggle overlay"""
        current = not self.overlay_enabled.get()
        self.overlay_enabled.set(current)
        self.overlay_btn.configure(bg='#2a6f2a' if current else '#6f2a2a')
        
        if current:
            self.overlay_frame.lift()
        else:
            self.overlay_frame.lower()
        
        self.add_event({'type': 'toggle_overlay'})
    
    def add_event(self, event):
        """Add event to queue"""
        with self.event_lock:
            self.event_queue.append(event)
    
    def get_events(self):
        """Get pending events"""
        with self.event_lock:
            events = self.event_queue.copy()
            self.event_queue.clear()
            return events
    
    def handle_events(self):
        """Get UI events (called from main thread)"""
        return self.get_events()
    
    def update_ui(self):
        """Update UI periodically"""
        if not self.running:
            return
        
        try:
            # Update clock
            self.clock_label.config(text=time.strftime("%H:%M:%S"))
            
            # Update status from current_state
            if self.current_state.get('emergency_stop'):
                self.status_label.configure(text="EMERGENCY STOP", fg='#ff0000')
            elif self.current_state.get('running'):
                self.status_label.configure(text="SYSTEM ACTIVE", fg='#00ff00')
            else:
                self.status_label.configure(text="SYSTEM IDLE", fg='#ffff00')
            
            # Update winch
            winch = self.current_state.get('winch_direction', 'stop')
            winch_text = {'forward': 'UP', 'reverse': 'DOWN', 'stop': 'STOP'}.get(winch, 'STOP')
            self.winch_label.configure(text=f"Winch: {winch_text}")
            
            # Update liquid
            if self.current_state.get('liquid_detected'):
                self.liquid_label.configure(text="LIQUID DETECTED")
            else:
                self.liquid_label.configure(text="")
            
            # Update telemetry overlay
            telemetry = self.current_state.get('telemetry', {})
            if 'sensors' in telemetry:
                sensors = telemetry['sensors']
                values = [
                    f"{sensors.get('pressure_kpa', 0):.1f}",
                    f"{sensors.get('ph_level', 7):.2f}",
                    f"{sensors.get('current_amps_1', 0):.2f}",
                    f"{sensors.get('current_amps_2', 0):.2f}"
                ]
                for i, value in enumerate(values):
                    if i < len(self.overlay_texts):
                        self.overlay_texts[i].configure(text=value)
            
            self.root.after(100, self.update_ui)
            
        except Exception as e:
            print(f"UI update error: {e}")
    
    def update(self, new_state):
        """Update display with new state (called from main thread)"""
        self.current_state = new_state.copy()
    
    def run(self):
        """Run main loop"""
        if self.enabled:
            try:
                self.root.mainloop()
            except:
                pass
    
    def cleanup(self):
        """Clean up"""
        self.stop_camera()
        self.running = False
        if self.enabled:
            try:
                self.root.quit()
                self.root.destroy()
            except:
                pass
