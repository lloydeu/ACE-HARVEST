"""Camera Output - GStreamer Video Streaming"""
import subprocess
from config import config

class CameraOutput:
    """Stream camera to RPi Bottom via GStreamer"""
    
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.process = None
    
    def start(self):
        """Start GStreamer pipeline"""
        width = config.get('camera_width')
        height = config.get('camera_height')
        fps = config.get('camera_fps')
        bitrate = config.get('camera_bitrate')
        
        # Use libcamera-vid instead of libcamerasrc (works on RPi OS)
        pipeline = [
            'gst-launch-1.0',
            'libcamerasrc',
            '!', f'video/x-raw,width={width},height={height},framerate={fps}/1',
            '!', 'videoconvert',
            '!', 'v4l2h264enc',
            'extra-controls="controls,h264_i_frame_period=30,video_bitrate=2000000"',
            '!', 'video/x-h264,level=(string)4,profile=(string)baseline',
            '!', 'rtph264pay',
            'config-interval=1',
            '!', 'udpsink',
            f'host={self.host}',
            f'port={self.port}']      
        print("GStreamer pipeline:")
        print(" ".join(pipeline))
 
        try:
            self.process = subprocess.Popen(
                pipeline,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
  		bufsize=1
            )
            for line in self.process.stderr:
                print(f"GStreamer: {line.strip()}")

            return True
        except Exception as e:
            print(f"Camera start failed: {e}")
            return False
    
    def stop(self):
        """Stop streaming"""
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)
            self.process = None
