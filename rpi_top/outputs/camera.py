"""Camera Output - GStreamer Video Streaming"""
import subprocess
import threading
from config import config

class CameraOutput:
    """Stream camera to RPi Bottom via GStreamer"""
    
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.process = None
        self._log_thread = None
    
    def start(self):
        """Start GStreamer pipeline"""
        width = config.get('camera_width')
        height = config.get('camera_height')
        fps = config.get('camera_fps')
        bitrate = config.get('camera_bitrate')
        
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
            f'port={self.port}',
        ]

        print("GStreamer pipeline:")
        print(" ".join(pipeline))

        try:
            # FIX #3: stderr was piped and read in a blocking for-loop inside start(),
            # which prevented start() from ever returning True.
            # Now stderr is read in a background daemon thread so start() returns immediately.
            self.process = subprocess.Popen(
                pipeline,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            # Log GStreamer output without blocking
            self._log_thread = threading.Thread(
                target=self._log_stderr,
                daemon=True,
                name="CameraLog",
            )
            self._log_thread.start()

            return True
        except Exception as e:
            print(f"Camera start failed: {e}")
            return False

    def _log_stderr(self):
        """Background thread: drain and print GStreamer stderr"""
        try:
            for line in self.process.stderr:
                print(f"GStreamer: {line.rstrip()}")
        except Exception:
            pass

    def stop(self):
        """Stop streaming"""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None