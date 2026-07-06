import sys
import cv2
import pyaudio
import numpy as np
import glob
import os
from contextlib import contextmanager
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QComboBox, QProgressBar,
                             QPushButton, QSizePolicy, QSlider)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QEvent, QRect
from PyQt5.QtGui import QImage, QPixmap, QIcon

# Set environment variables to suppress Qt Wayland and OpenCV internal warning logs
os.environ["QT_LOGGING_RULES"] = "qt.qpa.wayland=false"
os.environ["OPENCV_LOG_LEVEL"] = "OFF"
os.environ["OPENCV_VIDEOIO_LOG_LEVEL"] = "0"

@contextmanager
def suppress_stderr():
    """Context manager to temporarily redirect stderr to /dev/null,
    suppressing noisy C++ library warnings (e.g. V4L2, ALSA, Jack).
    """
    try:
        stderr_fd = sys.stderr.fileno()
        saved_stderr_fd = os.dup(stderr_fd)
        devnull = open(os.devnull, 'w')
        os.dup2(devnull.fileno(), stderr_fd)
        yield
    except Exception:
        yield
    finally:
        try:
            os.dup2(saved_stderr_fd, stderr_fd)
            os.close(saved_stderr_fd)
            devnull.close()
        except Exception:
            pass

# --- THREADING EXPLANATION ---
# Multi-threading is essential in GUI applications that capture continuous data 
# streams (like live video and audio). 
# If we run the video frame extraction or audio reading loop in the main thread, 
# it blocks the GUI's event loop. This causes the UI to freeze, preventing window 
# updates, button clicks, and resize events.
# 
# To solve this:
# 1. We create separate QThread subclasses (VideoThread and AudioThread) to handle I/O.
# 2. These threads run infinite loops (while self._run_flag) that fetch data.
# 3. We use PyQt's pyqtSignal to safely pass the captured frames/volume data back 
#    to the main thread, which updates the UI elements (Label and ProgressBar).
# -----------------------------

class VideoThread(QThread):
    # Signal to pass the numpy array (image frame) back to the main GUI thread
    change_pixmap_signal = pyqtSignal(np.ndarray)

    def __init__(self, camera_identifier):
        super().__init__()
        self.camera_identifier = camera_identifier
        self._run_flag = True

    def run(self):
        # Initialize video capture using the selected device (e.g., "/dev/video0")
        with suppress_stderr():
            self.cap = cv2.VideoCapture(self.camera_identifier)
        
        while self._run_flag:
            ret, cv_img = self.cap.read()
            if ret:
                # Safely emit the frame to the GUI thread
                self.change_pixmap_signal.emit(cv_img)
                
        # Graceful hardware release
        with suppress_stderr():
            self.cap.release()

    def stop(self):
        # Break the loop and wait for the thread to exit gracefully
        self._run_flag = False
        self.wait()

class AudioThread(QThread):
    # Signal to pass the calculated volume (float) back to the GUI thread
    volume_signal = pyqtSignal(float)

    def __init__(self, device_index=None):
        super().__init__()
        self.device_index = device_index
        self._run_flag = True
        self.chunk = 1024
        self.format = pyaudio.paInt16
        self.channels = 1
        with suppress_stderr():
            self.p = pyaudio.PyAudio()

        # Dynamically fetch the device's default sample rate to avoid Errno -9997 (Invalid sample rate)
        self.rate = 44100
        if self.device_index is not None:
            try:
                device_info = self.p.get_device_info_by_host_api_device_index(0, self.device_index)
                self.rate = int(device_info.get('defaultSampleRate', 44100))
            except Exception as e:
                print(f"Error fetching device sample rate: {e}")

        self.volume_multiplier = 1.0

    def set_volume(self, multiplier):
        self.volume_multiplier = multiplier

    def run(self):
        try:
            with suppress_stderr():
                # Open the audio input stream for the selected microphone
                in_stream = self.p.open(format=self.format,
                                        channels=self.channels,
                                        rate=self.rate,
                                        input=True,
                                        input_device_index=self.device_index,
                                        frames_per_buffer=self.chunk)
                
                # Open the default audio output stream for playback
                out_stream = self.p.open(format=self.format,
                                         channels=self.channels,
                                         rate=self.rate,
                                         output=True,
                                         frames_per_buffer=self.chunk)
        except Exception as e:
            print(f"Error opening audio stream: {e}")
            return

        while self._run_flag:
            try:
                # Read audio chunk
                data = in_stream.read(self.chunk, exception_on_overflow=False)
                # Convert raw bytes to a numpy array of 16-bit integers
                audio_data = np.frombuffer(data, dtype=np.int16)
                
                # Apply volume multiplier for playback
                if self.volume_multiplier != 1.0:
                    playback_data = audio_data.astype(np.float32) * self.volume_multiplier
                    # Clip to int16 range to avoid overflow/distortion and cast back
                    playback_data = np.clip(playback_data, -32768, 32767).astype(np.int16)
                else:
                    playback_data = audio_data
                
                # Write to output stream to play the sound
                out_stream.write(playback_data.tobytes())
                
                # Calculate the Root Mean Square (RMS) to determine the visual volume level
                if len(audio_data) > 0:
                    rms = np.sqrt(np.mean(np.square(audio_data.astype(np.float32))))
                    self.volume_signal.emit(rms)
            except Exception as e:
                print(f"Audio read/write error: {e}")
                break

        # Graceful hardware release
        with suppress_stderr():
            in_stream.stop_stream()
            in_stream.close()
            out_stream.stop_stream()
            out_stream.close()
            self.p.terminate()

    def stop(self):
        self._run_flag = False
        self.wait()

class CameraAudioApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Camera & Audio Preview")
        self.resize(800, 600)
        self.setMinimumSize(400, 300)

        # Set App Icon
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pyCamIn.jpeg')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Custom resize variables
        self.EDGE_NONE = 0
        self.EDGE_LEFT = 1
        self.EDGE_RIGHT = 2
        self.EDGE_TOP = 4
        self.EDGE_BOTTOM = 8
        self.MARGIN = 8

        self.current_edge = self.EDGE_NONE
        self.is_resizing = False
        self.drag_start_pos = None
        self.drag_start_geo = None

        # Set up the main central widget and vertical layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(9, 9, 9, 9)

        # --- Video Preview Area ---
        self.image_label = QLabel(self)
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: black;")
        self.layout.addWidget(self.image_label, stretch=1)

        # --- Bottom Bar (Audio Meter + Controls) ---
        self.bottom_bar = QWidget()
        self.bottom_layout = QVBoxLayout(self.bottom_bar)
        self.bottom_layout.setContentsMargins(0, 0, 0, 0)

        # --- Audio Visualizer Area ---
        self.audio_meter = QProgressBar()
        self.audio_meter.setTextVisible(False)
        self.audio_meter.setRange(0, 5000)  # Adjust the maximum based on mic sensitivity
        self.audio_meter.setFixedHeight(20)
        self.bottom_layout.addWidget(self.audio_meter)

        # --- Controls Area ---
        self.controls_widget = QWidget()
        self.controls_layout = QHBoxLayout(self.controls_widget)
        self.controls_layout.setContentsMargins(0, 0, 0, 0)
        
        # Camera Dropdown
        self.controls_layout.addWidget(QLabel("Camera:"))
        self.camera_combo = QComboBox()
        self.controls_layout.addWidget(self.camera_combo)
        
        # Microphone Dropdown
        self.controls_layout.addWidget(QLabel("Microphone:"))
        self.mic_combo = QComboBox()
        self.controls_layout.addWidget(self.mic_combo)

        # Volume Slider for Playback
        self.controls_layout.addWidget(QLabel("Volume:"))
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 200) # 0 to 200%
        self.volume_slider.setValue(100)    # Default 100%
        self.volume_slider.setFixedWidth(100)
        self.volume_slider.valueChanged.connect(self.change_volume)
        self.controls_layout.addWidget(self.volume_slider)

        # Full-Screen Toggle
        self.fullscreen_btn = QPushButton("Toggle Fullscreen (F11)")
        self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)
        self.controls_layout.addWidget(self.fullscreen_btn)

        self.bottom_layout.addWidget(self.controls_widget)
        self.layout.addWidget(self.bottom_bar)

        # Enable mouse tracking and event filters for hover/resizing detection
        self.setMouseTracking(True)
        self.central_widget.setMouseTracking(True)
        self.image_label.setMouseTracking(True)
        self.bottom_bar.setMouseTracking(True)
        self.controls_widget.setMouseTracking(True)

        self.central_widget.installEventFilter(self)
        self.image_label.installEventFilter(self)
        self.bottom_bar.installEventFilter(self)
        self.controls_widget.installEventFilter(self)

        # Background state objects
        self.video_thread = None
        self.audio_thread = None
        with suppress_stderr():
            self.pyaudio_instance = pyaudio.PyAudio()

        # Discover devices and populate dropdowns
        self.populate_cameras()
        self.populate_mics()

        # Connect UI changes to thread restarts
        self.camera_combo.currentIndexChanged.connect(self.start_video)
        self.mic_combo.currentIndexChanged.connect(self.start_audio)

        # Autostart the streams if devices were found
        if self.camera_combo.count() > 0:
            self.start_video()
        if self.mic_combo.count() > 0:
            self.start_audio()

    def populate_cameras(self):
        """Scans for video devices and populates the camera dropdown,
        excluding devices that cannot be successfully opened.
        """
        # On Linux (Debian/Kali), cameras are exposed as /dev/video*
        cameras = glob.glob("/dev/video*")
        cameras.sort()
        
        with suppress_stderr():
            if not cameras:
                # Fallback for alternative environments: manually test indexes 0-3
                for i in range(4):
                    cap = cv2.VideoCapture(i)
                    if cap.isOpened():
                        self.camera_combo.addItem(f"Camera Index {i}", i)
                        cap.release()
            else:
                for cam in cameras:
                    cap = cv2.VideoCapture(cam)
                    if cap.isOpened():
                        # Read one frame to make sure it is a valid video capture source
                        ret, _ = cap.read()
                        if ret:
                            self.camera_combo.addItem(cam, cam)
                    cap.release()

    def populate_mics(self):
        """Scans for audio input devices using PyAudio and populates the mic dropdown,
        excluding internal/default microphones.
        """
        info = self.pyaudio_instance.get_host_api_info_by_index(0)
        num_devices = info.get('deviceCount')
        
        # Internal microphone and default audio keywords to exclude
        internal_keywords = [
            'analog', 'pch', 'intel', 'loopback', 'sysdefault', 'default', 
            'pipewire', 'pulse', 'dmix', 'builtin', 'built-in', 'internal'
        ]
        
        for i in range(0, num_devices):
            device_info = self.pyaudio_instance.get_device_info_by_host_api_device_index(0, i)
            # Only add devices that have input channels (microphones)
            if device_info.get('maxInputChannels') > 0:
                name = device_info.get('name')
                name_lower = name.lower()
                
                # Exclude if device name matches any internal keyword
                is_internal = any(kw in name_lower for kw in internal_keywords)
                if not is_internal:
                    self.mic_combo.addItem(name, i)

    def start_video(self):
        """Starts or restarts the video thread when the selection changes."""
        if self.video_thread is not None:
            self.video_thread.stop()
        
        camera_id = self.camera_combo.currentData()
        if camera_id is not None:
            self.video_thread = VideoThread(camera_id)
            self.video_thread.change_pixmap_signal.connect(self.update_image)
            self.video_thread.start()

    def change_volume(self, value):
        """Updates the audio playback volume multiplier."""
        multiplier = value / 100.0
        if self.audio_thread is not None:
            self.audio_thread.set_volume(multiplier)

    def start_audio(self):
        """Starts or restarts the audio thread when the selection changes."""
        if self.audio_thread is not None:
            self.audio_thread.stop()
        
        mic_id = self.mic_combo.currentData()
        if mic_id is not None:
            self.audio_thread = AudioThread(mic_id)
            self.audio_thread.set_volume(self.volume_slider.value() / 100.0)
            self.audio_thread.volume_signal.connect(self.update_meter)
            self.audio_thread.start()

    def update_image(self, cv_img):
        """Slot triggered by VideoThread to display the new frame."""
        # Convert the raw OpenCV BGR image to RGB
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        
        # Convert to QImage and scale it to fit the QLabel while maintaining aspect ratio
        qt_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        scaled_img = qt_img.scaled(self.image_label.width(), self.image_label.height(), Qt.KeepAspectRatio)
        
        # Set it on the UI
        self.image_label.setPixmap(QPixmap.fromImage(scaled_img))

    def update_meter(self, volume):
        """Slot triggered by AudioThread to update the progress bar."""
        # Clamp the calculated RMS volume so it doesn't exceed the meter's maximum
        val = min(int(volume), self.audio_meter.maximum())
        self.audio_meter.setValue(val)

    def toggle_fullscreen(self):
        """Switches between borderless full-screen and normal windowed mode."""
        if self.isFullScreen():
            self.showNormal()
            self.fullscreen_btn.setText("Toggle Fullscreen (F11)")
            self.bottom_bar.show()
            self.layout.setContentsMargins(9, 9, 9, 9)
        else:
            self.showFullScreen()
            self.fullscreen_btn.setText("Exit Fullscreen (Esc)")
            self.bottom_bar.hide()
            self.layout.setContentsMargins(0, 0, 0, 0)

    def handle_mouse_move(self, event):
        """Show/hide the bottom action bar based on mouse position when in fullscreen,
        or handle custom window resizing when not in fullscreen.
        """
        pos = self.mapFromGlobal(event.globalPos())
        y = pos.y()
        x = pos.x()
        window_height = self.height()
        window_width = self.width()

        if self.isFullScreen():
            # Hysteresis thresholding to prevent flickering in fullscreen
            # Show bottom bar if mouse cursor is within 30 pixels of the bottom
            if y >= window_height - 30:
                if not self.bottom_bar.isVisible():
                    self.bottom_bar.show()
            # Hide bottom bar if mouse cursor moves above the bottom bar area
            elif y < window_height - 120:
                if self.bottom_bar.isVisible():
                    self.bottom_bar.hide()
            return

        # Do not allow resizing if the window is maximized
        if self.isMaximized():
            self.unsetCursor()
            return

        # --- Handle custom window resizing when not in fullscreen ---
        if self.is_resizing:
            delta = event.globalPos() - self.drag_start_pos
            dx = delta.x()
            dy = delta.y()
            
            left = self.drag_start_geo.left()
            top = self.drag_start_geo.top()
            width = self.drag_start_geo.width()
            height = self.drag_start_geo.height()
            
            min_w = self.minimumWidth()
            min_h = self.minimumHeight()
            
            if self.current_edge & self.EDGE_LEFT:
                new_width = width - dx
                if new_width < min_w:
                    dx = width - min_w
                left = self.drag_start_geo.left() + dx
                width = width - dx
            elif self.current_edge & self.EDGE_RIGHT:
                width = max(min_w, width + dx)
                
            if self.current_edge & self.EDGE_TOP:
                new_height = height - dy
                if new_height < min_h:
                    dy = height - min_h
                top = self.drag_start_geo.top() + dy
                height = height - dy
            elif self.current_edge & self.EDGE_BOTTOM:
                height = max(min_h, height + dy)
                
            self.setGeometry(left, top, width, height)
            return

        # Determine which edge we are hovering over to set the cursor
        edge = self.EDGE_NONE
        if x <= self.MARGIN:
            edge |= self.EDGE_LEFT
        elif x >= window_width - self.MARGIN:
            edge |= self.EDGE_RIGHT
            
        if y <= self.MARGIN:
            edge |= self.EDGE_TOP
        elif y >= window_height - self.MARGIN:
            edge |= self.EDGE_BOTTOM
            
        self.current_edge = edge
        
        if edge == self.EDGE_LEFT or edge == self.EDGE_RIGHT:
            self.setCursor(Qt.SizeHorCursor)
        elif edge == self.EDGE_TOP or edge == self.EDGE_BOTTOM:
            self.setCursor(Qt.SizeVerCursor)
        elif edge == (self.EDGE_LEFT | self.EDGE_TOP) or edge == (self.EDGE_RIGHT | self.EDGE_BOTTOM):
            self.setCursor(Qt.SizeFDiagCursor)
        elif edge == (self.EDGE_RIGHT | self.EDGE_TOP) or edge == (self.EDGE_LEFT | self.EDGE_BOTTOM):
            self.setCursor(Qt.SizeBDiagCursor)
        else:
            self.unsetCursor()

    def mouseMoveEvent(self, event):
        self.handle_mouse_move(event)
        super().mouseMoveEvent(event)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseMove:
            self.handle_mouse_move(event)
            if self.is_resizing:
                return True
        elif event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton and self.current_edge != self.EDGE_NONE:
                self.drag_start_pos = event.globalPos()
                self.drag_start_geo = self.geometry()
                self.is_resizing = True
                return True
        elif event.type() == QEvent.MouseButtonRelease:
            if event.button() == Qt.LeftButton and self.is_resizing:
                self.is_resizing = False
                self.unsetCursor()
                return True
        elif event.type() == QEvent.Leave:
            if self.isFullScreen() and self.bottom_bar.isVisible():
                self.bottom_bar.hide()
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        """Listen for keyboard shortcuts to control the application."""
        key = event.key()

        # Fullscreen toggles
        if key in (Qt.Key_F11, Qt.Key_F):
            self.toggle_fullscreen()
        elif key == Qt.Key_Escape and self.isFullScreen():
            self.toggle_fullscreen()

        # Volume Controls
        elif key in (Qt.Key_Equal, Qt.Key_Plus):
            new_val = min(self.volume_slider.value() + 10, 200)
            self.volume_slider.setValue(new_val)
        elif key in (Qt.Key_Minus, Qt.Key_Underscore):
            new_val = max(self.volume_slider.value() - 10, 0)
            self.volume_slider.setValue(new_val)
        elif key == Qt.Key_M:
            if self.volume_slider.value() > 0:
                self.previous_volume = self.volume_slider.value()
                self.volume_slider.setValue(0)
            else:
                self.volume_slider.setValue(getattr(self, 'previous_volume', 100) or 100)

        # Video Source Change (1-9)
        elif Qt.Key_1 <= key <= Qt.Key_9:
            target_index = key - Qt.Key_1
            if target_index < self.camera_combo.count():
                self.camera_combo.setCurrentIndex(target_index)

        super().keyPressEvent(event)

    def closeEvent(self, event):
        """Ensures that all threads are stopped and resources are gracefully released upon exit."""
        if self.video_thread is not None:
            self.video_thread.stop()
        if self.audio_thread is not None:
            self.audio_thread.stop()
        self.pyaudio_instance.terminate()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Use the 'Fusion' style for a cleaner, modern look on Linux
    app.setStyle("Fusion")
    
    # Set global application icon
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pyCamIn.jpeg')
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
        
    main_app = CameraAudioApp()
    main_app.show()
    
    sys.exit(app.exec_())
