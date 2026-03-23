"""Camera Output - GStreamer Video Streaming"""
import subprocess
import threading
from config import config

class CameraOutput:
    """Stream camera to RPi Bottom via GStreamer — v4l2h264enc hardware encoder"""

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
        bitrate = config.get('camera_bitrate', 2000000)

        # FIX sender #1: config-interval=1 is a property of rtph264pay, not a
        # standalone pipeline element — must be on the same token, not a separate
        # list entry. The old code passed it as a new element name which caused
        # a silent parse error and broken RTP packetization.
        #
        # v4l2h264enc: RPi hardware H264 encoder — low latency, low CPU.
        # extra-controls sets I-frame interval and target bitrate via V4L2 API.
        # Requires: gstreamer1.0-plugins-good (v4l2 plugin)
        pipeline = [
            'gst-launch-1.0', '-e',
            'libcamerasrc',
            '!', f'video/x-raw,width={width},height={height},framerate={fps}/1',
            '!', 'videoconvert',
            '!', 'v4l2h264enc',
                 f'extra-controls="controls,h264_i_frame_period=30,video_bitrate={bitrate}"',
            '!', 'video/x-h264,level=(string)4,profile=(string)baseline',
            '!', 'rtph264pay config-interval=1',   # config-interval is a property here
            '!', f'udpsink host={self.host} port={self.port}',
        ]

        print("GStreamer sender pipeline:")
        print(" ".join(pipeline))

        try:
            self.process = subprocess.Popen(
                pipeline,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

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
                print(f"GStreamer[sender]: {line.rstrip()}")
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
