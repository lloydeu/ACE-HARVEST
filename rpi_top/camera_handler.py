#!/usr/bin/env python3
"""
Camera Handler for RPi4 Top
Streams PiCam Module 3 video to RPi4 Bottom using GStreamer
"""

import subprocess
import threading
import time
import json
from datetime import datetime

class GStreamerCamera:
    """
    Handles PiCam Module 3 video streaming using GStreamer
    Streams H.264 video over UDP to RPi4 Bottom
    """
    
    def __init__(self, 
                 bottom_ip="192.168.1.100", 
                 stream_port=5001,
                 width=1280, 
                 height=720, 
                 framerate=30,
                 bitrate=2000000):
        """
        Initialize camera streamer
        
        Args:
            bottom_ip: IP address of RPi4 Bottom
            stream_port: UDP port for video stream
            width: Video width in pixels
            height: Video height in pixels
            framerate: Frames per second
            bitrate: H.264 bitrate (2Mbps default)
        """
        self.bottom_ip = bottom_ip
        self.stream_port = stream_port
        self.width = width
        self.height = height
        self.framerate = framerate
        self.bitrate = bitrate
        
        self.process = None
        self.streaming = False
        self.frame_count = 0
        self.start_time = None
    
    def start_streaming(self):
        """
        Start GStreamer pipeline for camera streaming
        
        Pipeline:
        libcamerasrc (PiCam Module 3) 
        → capsfilter (set resolution/framerate)
        → video/x-raw conversion
        → x264enc (H.264 encoding)
        → rtph264pay (RTP packetization)
        → udpsink (send to Bottom)
        """
        if self.streaming:
            print("⚠️  Camera already streaming")
            return False
        
        # GStreamer pipeline for PiCam Module 3
        pipeline = [
            'gst-launch-1.0', '-v',
            
            # Source: PiCam Module 3 via libcamera
            'libcamerasrc',
            '!',
            
            # Set resolution and framerate
            f'video/x-raw,width={self.width},height={self.height},framerate={self.framerate}/1',
            '!',
            
            # Convert color format
            'videoconvert',
            '!',
            
            # H.264 encoding
            'x264enc',
            f'bitrate={self.bitrate // 1000}',  # Convert to kbps
            'tune=zerolatency',  # Low latency
            'speed-preset=ultrafast',  # Fast encoding
            '!',
            
            # RTP packetization
            'rtph264pay',
            'config-interval=1',
            'pt=96',
            '!',
            
            # Send over UDP
            'udpsink',
            f'host={self.bottom_ip}',
            f'port={self.stream_port}'
        ]
        
        try:
            print(f"📹 Starting camera stream to {self.bottom_ip}:{self.stream_port}")
            print(f"   Resolution: {self.width}x{self.height} @ {self.framerate}fps")
            
            self.process = subprocess.Popen(
                pipeline,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            self.streaming = True
            self.start_time = time.time()
            print("✓ Camera streaming started")
            return True
            
        except Exception as e:
            print(f"❌ Failed to start camera stream: {e}")
            return False
    
    def stop_streaming(self):
        """Stop the GStreamer pipeline"""
        if not self.streaming:
            return
        
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)
            self.process = None
        
        self.streaming = False
        print("⏹️  Camera streaming stopped")
    
    def get_stream_info(self):
        """
        Get current stream information
        Returns metadata about the stream (not actual frames)
        """
        if not self.streaming:
            return {
                "streaming": False,
                "message": "Camera not streaming"
            }
        
        uptime = time.time() - self.start_time if self.start_time else 0
        
        return {
            "streaming": True,
            "resolution": f"{self.width}x{self.height}",
            "framerate": self.framerate,
            "bitrate": self.bitrate,
            "destination": f"{self.bottom_ip}:{self.stream_port}",
            "uptime_seconds": uptime,
            "timestamp": datetime.now().isoformat()
        }
    
    def get_frame_metadata(self):
        """
        Get frame metadata (for telemetry)
        In a full implementation, this would include CV/AI results
        """
        self.frame_count += 1
        
        metadata = {
            "frame_number": self.frame_count,
            "timestamp": time.time(),
            "streaming": self.streaming
        }
        
        # Placeholder for computer vision results
        # In a real implementation, you would add:
        # - Object detection results
        # - Tracking information
        # - Navigation waypoints
        # - etc.
        
        return metadata
    
    def is_streaming(self):
        """Check if camera is currently streaming"""
        return self.streaming and self.process and self.process.poll() is None
    
    def restart_stream(self):
        """Restart the stream (useful if it crashes)"""
        print("🔄 Restarting camera stream...")
        self.stop_streaming()
        time.sleep(1)
        return self.start_streaming()


class GStreamerCameraMonitor:
    """
    Monitors GStreamer camera and auto-restarts if it crashes
    """
    
    def __init__(self, camera):
        self.camera = camera
        self.monitoring = False
        self.monitor_thread = None
    
    def start_monitoring(self):
        """Start background monitoring"""
        if self.monitoring:
            return
        
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        print("✓ Camera monitor started")
    
    def _monitor_loop(self):
        """Background monitoring loop"""
        while self.monitoring:
            if self.camera.streaming and not self.camera.is_streaming():
                print("⚠️  Camera stream died, restarting...")
                self.camera.restart_stream()
            
            time.sleep(5)  # Check every 5 seconds
    
    def stop_monitoring(self):
        """Stop monitoring"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)


# ========================================
# EXAMPLE USAGE
# ========================================
if __name__ == "__main__":
    # Initialize camera
    camera = GStreamerCamera(
        bottom_ip="192.168.1.100",
        stream_port=5001,
        width=1280,
        height=720,
        framerate=30
    )
    
    # Start monitoring (auto-restart on failure)
    monitor = GStreamerCameraMonitor(camera)
    monitor.start_monitoring()
    
    try:
        # Start streaming
        camera.start_streaming()
        
        # Keep streaming
        print("\nCamera streaming... Press Ctrl+C to stop\n")
        while True:
            # Print stream info every 10 seconds
            time.sleep(10)
            info = camera.get_stream_info()
            print(f"[Stream Info] Uptime: {info['uptime_seconds']:.0f}s | "
                  f"Resolution: {info['resolution']} | "
                  f"FPS: {info['framerate']}")
    
    except KeyboardInterrupt:
        print("\n")
    finally:
        monitor.stop_monitoring()
        camera.stop_streaming()