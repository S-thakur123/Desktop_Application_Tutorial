import sys
import time
from PyQt6.QtWidgets import (QApplication, QMainWindow, QGraphicsView, QGraphicsScene, 
                             QGraphicsPixmapItem, QVBoxLayout, QWidget, QPushButton, 
                             QFileDialog, QHBoxLayout, QSlider, QLabel)
from PyQt6.QtGui import QImage, QPixmap, QPainter 
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QTimer, QPoint, QEasingCurve, QPropertyAnimation
from ffpyplayer.player import MediaPlayer

'''class MediaWorker(QThread):
    frame_ready = pyqtSignal(QImage, float, float)
    position_changed = pyqtSignal(float)
    duration_found = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        self.player = None
        self.file_path = ""
        self.running = False
        self.cmd_seek = -1
        self.cmd_speed = 1.0
        self.cmd_volume = 1.0

    def load(self, path):
        self.file_path = path
        self.running = True

    def run(self):
        # Initialize player
        self.player = MediaPlayer(self.file_path, ff_opts={'sync': 'audio'})
        
        # Get metadata
        time.sleep(0.5) # Wait for engine to init
        duration = self.player.get_metadata().get('duration', 0)
        self.duration_found.emit(duration)

        while self.running:
            # Handle External Commands
            if self.cmd_seek != -1:
                self.player.seek(self.cmd_seek, relative=False)
                self.cmd_seek = -1
            
            self.player.set_volume(self.cmd_volume)

            frame, val = self.player.get_frame()
            
            if val == 'eof':
                self.player.seek(0, relative=False)
                continue
            
            if frame is None:
                time.sleep(0.01)
                continue
            
            if val > 0:
                # Adjust sleep by playback speed
                time.sleep(val / self.cmd_speed)

            img, t = frame
            w, h = img.get_size()
            
            # Update UI slider position
            self.position_changed.emit(self.player.get_pts())

            data = img.to_bytearray()[0]
            qimg = QImage(data, w, h, QImage.Format.Format_RGB888).copy()
            self.frame_ready.emit(qimg, float(w), float(h))

    def stop(self):
        self.running = False
        if self.player:
            self.player.close_player()
        self.wait()'''

class MediaWorker(QThread):
    frame_ready = pyqtSignal(QImage, float, float)
    position_changed = pyqtSignal(float)
    duration_found = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        self.player = None
        self.file_path = ""
        self.running = False
        self.cmd_seek = -1
        self.cmd_speed = 1.0
        self.cmd_volume = 1.0
        self.is_paused = False

    def load(self, path):
        self.file_path = path
        self.running = True
        self.is_paused = False

    def toggle_pause(self):
        if self.player:
            self.is_paused = not self.is_paused
            self.player.set_pause(self.is_paused)
        return self.is_paused

    def run(self):
        # Start player - we use 'sync': 'audio' to let audio play normally
        self.player = MediaPlayer(self.file_path, ff_opts={'sync': 'audio'})
        
        time.sleep(0.7) 
        duration = self.player.get_metadata().get('duration', 0)
        self.duration_found.emit(duration)

        while self.running:
            if self.cmd_seek != -1:
                self.player.seek(self.cmd_seek, relative=False)
                self.cmd_seek = -1
            
            # Volume is almost always supported
            self.player.set_volume(self.cmd_volume)

            if self.is_paused:
                time.sleep(0.1)
                continue

            # Get the frame
            frame, val = self.player.get_frame()
            
            if val == 'eof':
                self.player.seek(0, relative=False)
                continue
            
            if frame is None:
                time.sleep(0.01)
                continue
            
            # --- MANUAL SPEED SYNC ---
            # If val is 0.033 (for 30fps) and speed is 2.0, 
            # we only sleep for 0.016, making it play twice as fast.
            if val > 0:
                time.sleep(val / self.cmd_speed)

            img, t = frame
            w, h = img.get_size()
            
            # Update position signal
            self.position_changed.emit(self.player.get_pts())

            # Convert to QImage
            data = img.to_bytearray()[0]
            qimg = QImage(data, w, h, QImage.Format.Format_RGB888).copy()
            self.frame_ready.emit(qimg, float(w), float(h))
            
    def stop(self):
        """This is the missing method that fixed your error"""
        self.running = False
        if self.player:
            self.player.close_player()
        self.wait() # Wait for the thread to actually exit

class ZoomView(QGraphicsView):
    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setBackgroundBrush(Qt.GlobalColor.black)

    def wheelEvent(self, event):
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.scale(factor, factor)

class DesktopPlayer(QMainWindow):
    '''def __init__(self):
        super().__init__()
        self.setWindowTitle("Pro Media Desktop")
        self.resize(1200, 800)
        
        self.scene = QGraphicsScene()
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)
        self.view = ZoomView(self.scene)

        # Time Slider
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.sliderMoved.connect(self.seek_video)

        # Control Row 1: Buttons
        self.open_btn = QPushButton("📁 Open")
        self.open_btn.clicked.connect(self.open_file)
        self.fullscreen_btn = QPushButton("📺 Fullscreen")
        self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)
        self.reset_btn = QPushButton("🔄 Reset Zoom")
        self.reset_btn.clicked.connect(self.reset_zoom)

        # Control Row 2: Volume and Speed
        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(100)
        self.vol_slider.setFixedWidth(120)
        self.vol_slider.valueChanged.connect(self.update_volume)

        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(5, 20) # 0.5x to 2.0x
        self.speed_slider.setValue(10) # 1.0x
        self.speed_slider.setFixedWidth(120)
        self.speed_slider.valueChanged.connect(self.update_speed)
        self.speed_label = QLabel("Speed: 1.0x")

        # Layouts
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.open_btn)
        btn_layout.addWidget(self.fullscreen_btn)
        btn_layout.addWidget(self.reset_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(QLabel("Vol:"))
        btn_layout.addWidget(self.vol_slider)
        btn_layout.addWidget(self.speed_label)
        btn_layout.addWidget(self.speed_slider)

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.view)
        main_layout.addWidget(self.time_slider)
        main_layout.addLayout(btn_layout)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        self.worker = MediaWorker()
        self.worker.frame_ready.connect(self.on_frame_ready)
        self.worker.duration_found.connect(lambda d: self.time_slider.setRange(0, int(d)))
        self.worker.position_changed.connect(self.update_slider_pos)'''

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pro Media Desktop")
        self.resize(1200, 800)
        
        # 1. Enable Mouse Tracking on the window to detect movement for auto-hide
        self.setMouseTracking(True)
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # 2. Setup Video View
        self.scene = QGraphicsScene()
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)
        self.view = ZoomView(self.scene)
        self.view.setMouseTracking(True) # Ensure view passes mouse events

        # 3. Transparent Control Bar Widget
        self.control_bar = QWidget(self)
        self.control_bar.setObjectName("ControlBar")
        # semi-transparent black (180 alpha)
        self.control_bar.setStyleSheet("""
#ControlBar {
    background-color: rgba(0, 0, 0, 180);
    border-top-left-radius: 15px;
    border-top-right-radius: 15px;
}
QLabel, QPushButton {
    color: white;
    background: transparent;
    border: none;
    padding: 5px;
}
QPushButton:hover { background-color: rgba(255, 255, 255, 50); }
""")

        # --- Reusing your Sliders/Buttons ---
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.sliderMoved.connect(self.seek_video)
        
        self.open_btn = QPushButton("📁 Open")
        self.open_btn.clicked.connect(self.open_file)
        self.play_btn = QPushButton("▶ Play/Pause")
        self.play_btn.clicked.connect(self.toggle_playback)
        self.play_btn.clicked.connect(self.toggle_pause)
        self.fullscreen_btn = QPushButton("📺 Fullscreen")
        self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)
        self.reset_btn = QPushButton("🔄 Reset Zoom")
        self.reset_btn.clicked.connect(self.reset_zoom)

        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(100)
        self.vol_slider.setFixedWidth(100)
        self.vol_slider.valueChanged.connect(self.update_volume)

        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(5, 20)
        self.speed_slider.setValue(10)
        self.speed_slider.setFixedWidth(100)
        self.speed_slider.valueChanged.connect(self.update_speed)
        self.speed_label = QLabel("1.0x")

        # --- Layouts ---
        # Putting your rows into the transparent bar
        bar_layout = QVBoxLayout(self.control_bar)
        
        row1 = QHBoxLayout()
        row1.addWidget(self.time_slider)
        
        row2 = QHBoxLayout()
        row2.addWidget(self.open_btn)
        row2.addWidget(self.play_btn)
        row2.addWidget(self.fullscreen_btn)
        row2.addWidget(self.reset_btn)
        row2.addStretch()
        row2.addWidget(QLabel("Vol:"))
        row2.addWidget(self.vol_slider)
        row2.addWidget(self.speed_label)
        row2.addWidget(self.speed_slider)
        
        bar_layout.addLayout(row1)
        bar_layout.addLayout(row2)

        # Main Layout: Use a Stacked approach or Overlay
        # For simplicity, we use a VBox but set margins to 0 so bar "floats"
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        self.main_layout.addWidget(self.view)

        self.view.setFrameStyle(0) # 0 means NoFrame
        # Alternatively via stylesheet:
        self.view.setStyleSheet("border: none; background-color: black;")
        
        # 4. Timer for Auto-Hide (3 seconds)
        self.hide_timer = QTimer()
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.fade_out_controls)
        
        # Position the bar
        self.control_bar.setFixedHeight(100)

        # Worker setup
        self.worker = MediaWorker()
        self.worker.frame_ready.connect(self.on_frame_ready)
        self.worker.duration_found.connect(lambda d: self.time_slider.setRange(0, int(d)))
        self.worker.position_changed.connect(self.update_slider_pos)

    def resizeEvent(self, event):
        """Keep the control bar at the bottom during resize"""
        super().resizeEvent(event)
        self.control_bar.setGeometry(0, self.height() - 100, self.width(), 100)

    def toggle_playback(self):
        self.thread.running = not self.thread.running
        if self.thread.running :
            self.thread.start()

    def toggle_pause(self):
        if self.player:
            self.is_paused = not self.is_paused
            self.player.set_pause(self.is_paused)
        return self.is_paused

    def mouseMoveEvent(self, event):
        """Show controls when mouse moves"""
        self.show_controls()
        super().mouseMoveEvent(event)

    def show_controls(self):
        self.control_bar.show()
        self.hide_timer.start(3000) # Reset timer to 3 seconds

    def fade_out_controls(self):
        """Hide controls if not hovering over them"""
        if not self.control_bar.underMouse():
            self.control_bar.hide()

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Video")
        if path:
            self.worker.stop()
            self.worker.load(path)
            self.worker.start()

    def on_frame_ready(self, qimg, w, h):
        self.pixmap_item.setPixmap(QPixmap.fromImage(qimg))
        if self.scene.sceneRect().width() != w:
            self.scene.setSceneRect(0, 0, w, h)

    def update_slider_pos(self, pts):
        self.time_slider.blockSignals(True)
        self.time_slider.setValue(int(pts))
        self.time_slider.blockSignals(False)

    def seek_video(self, pos):
        self.worker.cmd_seek = pos

    def update_volume(self, val):
        self.worker.cmd_volume = val / 100.0

    def update_speed(self, val):
        speed = val / 10.0
        self.worker.cmd_speed = speed
        self.speed_label.setText(f"Speed: {speed}x")

    def keyPressEvent(self, event):
        # Spacebar to Play/Pause
        if event.key() == Qt.Key.Key_Space:
            paused = self.worker.toggle_pause()
            status = "PAUSED" if paused else "PLAYING"
            self.setWindowTitle(f"Pro Media Desktop - {status}")
        
        # 'M' to Mute
        elif event.key() == Qt.Key.Key_M:
            current_vol = self.vol_slider.value()
            if current_vol > 0:
                self.prev_vol = current_vol # Store to restore later
                self.vol_slider.setValue(0)
            else:
                self.vol_slider.setValue(getattr(self, 'prev_vol', 70))
        
        # 'F' for Fullscreen
        elif event.key() == Qt.Key.Key_F:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
        
        # Escape to exit Fullscreen
        elif event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.showNormal()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def reset_zoom(self):
        self.view.resetTransform()

    def closeEvent(self, event):
        self.worker.stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    player = DesktopPlayer()
    player.show()
    sys.exit(app.exec())