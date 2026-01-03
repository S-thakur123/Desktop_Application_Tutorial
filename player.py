import sys
import time
from PyQt6.QtWidgets import (QApplication, QMainWindow, QGraphicsView, QGraphicsScene, 
                             QGraphicsPixmapItem, QVBoxLayout, QWidget, QPushButton, 
                             QFileDialog, QHBoxLayout, QSlider, QLabel, QFrame,
                             QGraphicsDropShadowEffect)
from PyQt6.QtGui import QImage, QPixmap, QPainter , QTransform, QColor
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QTimer, QPoint, QEasingCurve, QPropertyAnimation
from ffpyplayer.player import MediaPlayer

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
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.zoom_factor = 1.0

    def wheelEvent(self, event):
        factor = 1.05 if event.angleDelta().y() > 0 else 0.9
        # Update the tracker
        self.zoom_factor *= factor
        potential_zoom = self.zoom_factor * factor
        # Clamp between 10% and 500%
        if 0.1 <= potential_zoom <= 5.0:
            self.zoom_factor = potential_zoom
            
            # --- THE SYNC STEP ---
            # Update the slider in the main window
            # This will automatically trigger set_custom_zoom via the signal
            self.window().zoom_slider.setValue(int(self.zoom_factor * 100))
        # Apply the scale
        self.scale(factor, factor)
        
        # Tell the main window to update the text
        if self.window():
            self.window().update_status_bar()
            

class DesktopPlayer(QMainWindow):
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
        self.control_bar.setStyleSheet("""#ControlBar { background-color: rgba(0, 0, 0, 180); border-top-left-radius: 15px; border-top-right-radius: 15px;}
        QLabel, QPushButton { color: white; background: transparent; border: none; padding: 5px; }
        QPushButton:hover { background-color: rgba(255, 255, 255, 50); } """)
        # --- Reusing your Sliders/Buttons ---
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.sliderMoved.connect(self.seek_video)
        self.open_btn = QPushButton("📁")
        self.open_btn.clicked.connect(self.open_file)
        self.play_btn = QPushButton("⏸") # Start with Pause if it auto-plays
        self.play_btn.clicked.connect(self.toggle_playback)
        # Add rotation state
        self.current_rotation = 0      
        # Create Rotate Button
        self.rotate_btn = QPushButton("⟳°")
        self.rotate_btn.clicked.connect(self.rotate_video)
        # Custom Rotation Slider (0 to 360 degrees)
        self.rotate_slider = QSlider(Qt.Orientation.Horizontal)
        self.rotate_slider.setRange(0, 360)
        self.rotate_slider.setValue(0)
        self.rotate_slider.setFixedWidth(150)
        self.rotate_slider.valueChanged.connect(self.set_custom_rotation)
        self.fullscreen_btn = QPushButton("⛶")
        self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)
        self.reset_btn = QPushButton("🔄")
        self.reset_btn.clicked.connect(self.reset_zoom)
        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(100)
        self.vol_slider.setFixedWidth(100)
        self.vol_slider.valueChanged.connect(self.update_volume)
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(2, 30)
        self.speed_slider.setValue(10)
        self.speed_slider.setFixedWidth(120)
        self.speed_slider.valueChanged.connect(self.update_speed)
        self.speed_label = QLabel("1.0x")
        # Zoom Slider (10% to 500%)
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(10, 500) # 10% to 500%
        self.zoom_slider.setValue(100)     # Default 100%
        self.zoom_slider.setFixedWidth(150)
        self.zoom_slider.valueChanged.connect(self.set_custom_zoom)
        self.zoom_label = QLabel(": 100%")
        self.zoom_label.setStyleSheet("color: white;")
        # --- Layouts ---
        # Putting your rows into the transparent bar
        bar_layout = QVBoxLayout(self.control_bar)        
        row1 = QHBoxLayout()
        row1.addWidget(self.time_slider)        
        row2 = QHBoxLayout()
        row2.addWidget(self.rotate_btn)
        row2.addWidget(self.open_btn)
        row2.addWidget(self.play_btn)
        row2.addWidget(self.reset_btn)
        row2.addStretch()
        row2.addWidget(QLabel("⌕:"))
        row2.addWidget(self.zoom_slider)
        row2.addWidget(self.zoom_label)
        row2.addWidget(QLabel("⟳°:"))
        row2.addWidget(self.rotate_slider)
        row2.addWidget(QLabel("🔇:"))
        row2.addWidget(self.vol_slider)
        row2.addWidget(self.speed_label)
        row2.addWidget(self.fullscreen_btn)
        # row2.addWidget(self.speed_slider)        
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
        self.control_bar.move(0, self.height() - self.control_bar.height())
        # Worker setup
        self.worker = MediaWorker()
        self.worker.frame_ready.connect(self.on_frame_ready)
        self.worker.duration_found.connect(lambda d: self.time_slider.setRange(0, int(d)))
        self.worker.position_changed.connect(self.update_slider_pos)
         # 1. Create the Status Bar (Top Overlay)
        self.status_label = QLabel(self)
        self.status_label.setObjectName("StatusBar")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("""
            QLabel#StatusBar {
                background-color: rgba(0, 0, 0, 120);
                color: #00FF00; /* Neon green text for a "pro" monitor look */
                font-weight: bold;
                font-family: 'Consolas', 'Courier New', monospace;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
                padding: 5px;
            }
        """)
        self.status_label.setText("Zoom: 100% | Rotate: 0°")
        self.status_label.setFixedWidth(250)
        self.status_label.setFixedHeight(30)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25)
        shadow.setXOffset(0)
        shadow.setYOffset(10)
        shadow.setColor(QColor(0, 0, 0, 180)) # Dark shadow
        self.control_bar.setGraphicsEffect(shadow)

    def update_status_bar(self):
        zoom_pct = int(self.view.zoom_factor * 100)
        rotate_deg = self.current_rotation
        self.status_label.setText(f"Zoom: {zoom_pct}% | Rotate: {rotate_deg}°")
        
        # Position it at the top center
        label_x = (self.width() - self.status_label.width()) // 2
        self.status_label.move(label_x, 0)    

    def resizeEvent(self, event):
        """Keep the control bar at the bottom during resize"""
        margin_bottom = 20
        margin_side = 50
        bar_height = 100
        
        bar_width = self.width() - (margin_side * 2)
        bar_x = margin_side
        bar_y = self.height() - bar_height - margin_bottom
        self.control_bar.setGeometry(bar_x, bar_y, bar_width, bar_height)
        # 2. Floating Top Status Bar
        status_x = (self.width() - self.status_label.width()) // 2
        self.status_label.move(status_x, 10) # 10px from top
        
        super().resizeEvent(event)
    
    def toggle_playback(self):
        if self.worker.isRunning():
            is_paused = self.worker.toggle_pause()
            # Update the button text based on state
            if is_paused:
                self.play_btn.setText(" ▶ ")
                self.setWindowTitle("Pro Media Desktop (Paused)")
            else:
                self.play_btn.setText("⏸")
                self.setWindowTitle("Pro Media Desktop")

    def mouseMoveEvent(self, event):
        """Show controls when mouse moves"""
        self.show_controls()
        super().mouseMoveEvent(event)

    def show_controls(self):
        self.control_bar.show()
        self.status_label.show() # Show top bar
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.hide_timer.start(1500) # Reset timer to 3 seconds

    def fade_out_controls(self):
        """Hide controls if not hovering over them"""
        if not self.control_bar.underMouse():
            self.control_bar.hide()
            self.status_label.hide()
            if self.isFullScreen():
                self.setCursor(Qt.CursorShape.BlankCursor)

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Video")
        if path:
            self.worker.stop()
            self.worker.load(path)
            self.worker.start()

    def set_custom_zoom(self, val):
        # 1. Calculate the scale factor (e.g., 100 becomes 1.0)
        new_zoom = val / 100.0
        self.view.zoom_factor = new_zoom       
        # 2. Update the Label
        self.zoom_label.setText(f"Zoom: {val}%")      
        # 3. Apply the transformation (keep rotation included!)
        from PyQt6.QtGui import QTransform
        transform = QTransform()
        transform.rotate(self.current_rotation)
        transform.scale(new_zoom, new_zoom)
        self.view.setTransform(transform)       
        # 4. Sync the Status Bar if you have it
        if hasattr(self, 'update_status_bar'):
            self.update_status_bar()

    def set_custom_rotation(self, angle):
        # 1. Update the state
        self.current_rotation = angle        
        # 2. Create a new transform combining rotation and existing zoom
        from PyQt6.QtGui import QTransform
        transform = QTransform()        
        # 3. Apply rotation then scale
        transform.rotate(self.current_rotation)
        transform.scale(self.view.zoom_factor, self.view.zoom_factor)        
        # 4. Apply to view
        self.view.setTransform(transform)        
        # 5. Update the Green Status Bar text
        self.update_status_bar()

    def rotate_video(self):
        """Update the 90 degree button to move the slider too"""
        new_angle = (self.current_rotation + 90) % 360
        self.rotate_slider.setValue(new_angle) # This triggers set_custom_rotation
        self.update_status_bar()

    @pyqtSlot(QImage, float, float)
    def on_frame_ready(self, qimg, w, h):
        self.pixmap_item.setPixmap(QPixmap.fromImage(qimg))
        # Adjust scene size to video size on first frame    
        if self.scene.sceneRect().width() != w:
            self.scene.setSceneRect(0, 0, w, h)
            self.pixmap_item.setPos(0, 0)

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
        if event.key() == Qt.Key.Key_R:
            self.rotate_video()    
        # 'L' increases speed
        if event.key() == Qt.Key.Key_L:
            new_val = self.speed_slider.value() + 2
            self.speed_slider.setValue(min(new_val, 30))
        # 'J' decreases speed
        elif event.key() == Qt.Key.Key_J:
            new_val = self.speed_slider.value() - 2
            self.speed_slider.setValue(max(new_val, 2))
        # 'K' resets to 1.0x (or pauses)
        elif event.key() == Qt.Key.Key_K:
            self.speed_slider.setValue(10)
        super().keyPressEvent(event)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def reset_zoom(self):
        self.view.resetTransform()
        self.update_status_bar()
        self.zoom_slider.setValue(100) # This triggers set_custom_zoom(100)
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        # Position Control Bar at bottom
        self.control_bar.setGeometry(0, self.height() - 100, self.width(), 100)
        # Position Status Bar at top center
        label_x = (self.width() - self.status_label.width()) // 2
        self.status_label.move(label_x, 0)
        super().resizeEvent(event)    

    def closeEvent(self, event):
        self.worker.stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    player = DesktopPlayer()
    player.show()
    sys.exit(app.exec())