import os
import sys
import traceback
from backend import *

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QRadioButton, QGroupBox, QButtonGroup,
    QMessageBox, QTextBrowser, QCheckBox, QSplitter, QSpacerItem, QScrollArea
)
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings
from PyQt5.QtCore import QUrl, Qt, QTimer
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtCore import QObject, pyqtSlot

class LiveSatelliteUpdater(QObject):
    @pyqtSlot(float, float, float, str)
    def updatePosition(self, lat, lon, alt, time_str):
        pass  # For 3D globe

    @pyqtSlot(float, float, float, str)
    def update2DPosition(self, lat, lon, alt, time):
        pass  # For 2D map

class OrbitVisualizerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Satellite Orbit Visualizer")
        self.setGeometry(100, 100, 1200, 800)
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        self.requested_time_h_float = 0.0
        self.target_point_geodetic = [0.0, 0.0]
        self.scan_area_size = 200.0
        self.sampling_interval = 1.0
        self.satellite_name = "Unknown"
        self.start_datetime_utc = None
        self.tle1 = None
        self.tle2 = None
        self.live_sat_pos_ecef = None
        self.live_sat_pos_geodetic = None
        self.map_initialized = False
        self.web_channel = QWebChannel()
        self.live_updater = LiveSatelliteUpdater()
        self.web_channel.registerObject("liveSatelliteUpdater", self.live_updater)
        self.live_update_timer = QTimer(self)
        self.live_update_timer.timeout.connect(self.update_live_position)
        self.live_update_timer.setInterval(5000)
        self.create_map_panel()
        self.create_output_panel()
        self.create_input_panel()

    def safe_add_widget(self, layout, widget, name="Widget"):
        if widget is None:
            print(f"ERROR: Attempted to add null {name} to layout")
            return False
        try:
            layout.addWidget(widget)
            print(f"DEBUG: Successfully added {name} to layout")
            return True
        except Exception as e:
            print(f"ERROR: Failed to add {name} to layout: {e}")
            return False

    def safe_add_layout(self, layout, sub_layout, name="Layout"):
        if sub_layout is None:
            print(f"ERROR: Attempted to add null {name} to layout")
            return False
        try:
            layout.addLayout(sub_layout)
            print(f"DEBUG: Successfully added {name} to layout")
            return True
        except Exception as e:
            print(f"ERROR: Failed to add {name} to layout: {e}")
            return False

    def create_map_panel(self):
        print("DEBUG: Creating map panel...")
        self.map_view = QWebEngineView()
        if self.map_view is None:
            print("ERROR: Failed to create QWebEngineView")
            return
        settings = self.map_view.page().settings()
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
        self.map_view.page().setWebChannel(self.web_channel)
        self.map_view.setUrl(QUrl("about:blank"))
        print("DEBUG: Map panel created successfully")

    def create_output_panel(self):
        print("DEBUG: Creating output panel...")
        self.output_group = QGroupBox("Overpass Information")
        if self.output_group is None:
            print("ERROR: Failed to create output_group")
            return
        output_layout = QVBoxLayout()
        output_layout.setSpacing(5)
        output_layout.setContentsMargins(9, 9, 9, 9)
        self.output_text_browser = QTextBrowser()
        if self.output_text_browser is None:
            print("ERROR: Failed to create output_text_browser")
            return
        self.output_text_browser.setHtml("Enter parameters and click 'Calculate & Visualize Orbit' to see overpass information.")
        self.safe_add_widget(output_layout, self.output_text_browser, "output_text_browser")
        self.output_group.setLayout(output_layout)
        print("DEBUG: Output panel created successfully")

    def create_input_panel(self):
        print("DEBUG: Creating input panel...")
        self.input_group = QGroupBox("Orbit Parameters")
        if self.input_group is None:
            print("ERROR: Failed to create input_group")
            return
        input_layout = QVBoxLayout()
        input_layout.setSpacing(5)
        input_layout.setContentsMargins(9, 9, 9, 9)

        # TLE form
        form_layout_tle = QVBoxLayout()
        form_layout_tle.setSpacing(5)
        sat_name_label = QLabel("Satellite Name (e.g., ISS):")
        sat_name_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        self.safe_add_widget(form_layout_tle, sat_name_label, "sat_name_label")
        self.sat_name_entry = QLineEdit()
        self.sat_name_entry.setPlaceholderText("Enter satellite name, e.g., ISS")
        self.sat_name_entry.setToolTip("Enter the name of the satellite (e.g., ISS, NOAA-15)")
        self.safe_add_widget(form_layout_tle, self.sat_name_entry, "sat_name_entry")
        tle1_label = QLabel("TLE Line 1 (69 characters):")
        tle1_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        self.safe_add_widget(form_layout_tle, tle1_label, "tle1_label")
        self.tle1_entry = QLineEdit()
        self.tle1_entry.setPlaceholderText("Enter 69-character TLE Line 1")
        self.tle1_entry.setToolTip("Enter the first line of the TLE (exactly 69 characters)")
        self.safe_add_widget(form_layout_tle, self.tle1_entry, "tle1_entry")
        tle2_label = QLabel("TLE Line 2 (69 characters):")
        tle2_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        self.safe_add_widget(form_layout_tle, tle2_label, "tle2_label")
        self.tle2_entry = QLineEdit()
        self.tle2_entry.setPlaceholderText("Enter 69-character TLE Line 2")
        self.tle2_entry.setToolTip("Enter the second line of the TLE (exactly 69 characters)")
        self.safe_add_widget(form_layout_tle, self.tle2_entry, "tle2_entry")
        self.safe_add_layout(input_layout, form_layout_tle, "form_layout_tle")
        input_layout.addSpacerItem(QSpacerItem(0, 10))

        # Start date group
        start_date_group = QGroupBox("Start Date Option")
        start_date_layout = QVBoxLayout()
        start_date_layout.setSpacing(5)
        self.start_date_choice_group = QButtonGroup(self)
        self.radio_tle_date = QRadioButton("From TLE Date")
        self.radio_tle_date.setChecked(True)
        self.radio_tle_date.toggled.connect(self.toggle_date_entry)
        self.safe_add_widget(start_date_layout, self.radio_tle_date, "radio_tle_date")
        self.start_date_choice_group.addButton(self.radio_tle_date, 2)
        self.radio_select_date = QRadioButton("Select Date (DD-MM-YYYY)")
        self.radio_select_date.toggled.connect(self.toggle_date_entry)
        self.safe_add_widget(start_date_layout, self.radio_select_date, "radio_select_date")
        self.start_date_choice_group.addButton(self.radio_select_date, 1)
        start_date_group.setLayout(start_date_layout)
        self.safe_add_widget(input_layout, start_date_group, "start_date_group")
        self.start_date_label = QLabel("Start Date (DD-MM-YYYY):")
        self.start_date_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        self.safe_add_widget(input_layout, self.start_date_label, "start_date_label")
        self.start_date_entry = QLineEdit()
        self.start_date_entry.setPlaceholderText("e.g., 01-01-2025")
        self.start_date_entry.setToolTip("Enter start date as DD-MM-YYYY (e.g., 01-01-2025)")
        self.start_date_entry.setEnabled(False)
        self.safe_add_widget(input_layout, self.start_date_entry, "start_date_entry")
        input_layout.addSpacerItem(QSpacerItem(0, 10))

        # Sampling rate group
        rate_group = QGroupBox("Sampling Rate")
        rate_layout = QHBoxLayout()
        rate_layout.setSpacing(5)
        self.rate_choice_group = QButtonGroup(self)
        self.radio_seconds = QRadioButton("Seconds")
        self.radio_seconds.setChecked(True)
        self.safe_add_widget(rate_layout, self.radio_seconds, "radio_seconds")
        self.rate_choice_group.addButton(self.radio_seconds, 1)
        self.radio_minutes = QRadioButton("Minutes")
        self.safe_add_widget(rate_layout, self.radio_minutes, "radio_minutes")
        self.rate_choice_group.addButton(self.radio_minutes, 2)
        self.radio_hours = QRadioButton("Hours")
        self.safe_add_widget(rate_layout, self.radio_hours, "radio_hours")
        self.rate_choice_group.addButton(self.radio_hours, 3)
        rate_group.setLayout(rate_layout)
        self.safe_add_widget(input_layout, rate_group, "rate_group")
        sampling_interval_label = QLabel("Sampling Interval (in selected units):")
        sampling_interval_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        self.safe_add_widget(input_layout, sampling_interval_label, "sampling_interval_label")
        self.sampling_interval_entry = QLineEdit()
        self.sampling_interval_entry.setPlaceholderText("e.g., 2")
        self.sampling_interval_entry.setToolTip("Enter sampling interval in seconds, minutes, or hours (e.g., 2)")
        self.safe_add_widget(input_layout, self.sampling_interval_entry, "sampling_interval_entry")
        input_layout.addSpacerItem(QSpacerItem(0, 10))

        # Simulation length
        sim_length_label = QLabel("Simulation Length (hours):")
        sim_length_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        self.safe_add_widget(input_layout, sim_length_label, "sim_length_label")
        self.sim_length_entry = QLineEdit()  # Fixed: Correctly define sim_length_entry
        self.sim_length_entry.setPlaceholderText("e.g., 24 or -12")
        self.sim_length_entry.setToolTip("Enter simulation duration in hours (positive or negative, e.g., 24)")
        self.safe_add_widget(input_layout, self.sim_length_entry, "sim_length_entry")
        input_layout.addSpacerItem(QSpacerItem(0, 10))

        # Target point group
        target_point_group = QGroupBox("Target Point for Coverage Check")
        target_point_layout = QVBoxLayout()
        target_point_layout.setSpacing(5)
        target_lat_label = QLabel("Target Latitude (degrees):")
        target_lat_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        self.safe_add_widget(target_point_layout, target_lat_label, "target_lat_label")
        self.target_lat_entry = QLineEdit()
        self.target_lat_entry.setPlaceholderText("e.g., 34.05")
        self.target_lat_entry.setToolTip("Enter target latitude in degrees (e.g., 34.05)")
        self.safe_add_widget(target_point_layout, self.target_lat_entry, "target_lat_entry")
        target_lon_label = QLabel("Target Longitude (degrees):")
        target_lon_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        self.safe_add_widget(target_point_layout, target_lon_label, "target_lon_label")
        self.target_lon_entry = QLineEdit()
        self.target_lon_entry.setPlaceholderText("e.g., -118.25")
        self.target_lon_entry.setToolTip("Enter target longitude in degrees (e.g., -118.25)")
        self.safe_add_widget(target_point_layout, self.target_lon_entry, "target_lon_entry")
        scan_area_label = QLabel("Scanning Area Size (km):")
        scan_area_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        self.safe_add_widget(target_point_layout, scan_area_label, "scan_area_label")
        self.scan_area_entry = QLineEdit()
        self.scan_area_entry.setPlaceholderText("e.g., 200")
        self.scan_area_entry.setToolTip("Enter scanning area size in kilometers (e.g., 200)")
        self.safe_add_widget(target_point_layout, self.scan_area_entry, "scan_area_entry")
        target_point_group.setLayout(target_point_layout)
        self.safe_add_widget(input_layout, target_point_group, "target_point_group")
        input_layout.addSpacerItem(QSpacerItem(0, 10))

        # Visualization type group
        vis_type_group = QGroupBox("Visualization Type")
        vis_type_layout = QHBoxLayout()
        vis_type_layout.setSpacing(5)
        self.vis_type_choice_group = QButtonGroup(self)
        self.radio_2d_map = QRadioButton("2D Map")
        self.radio_2d_map.setChecked(True)
        self.radio_2d_map.toggled.connect(self.toggle_3d_options)
        self.safe_add_widget(vis_type_layout, self.radio_2d_map, "radio_2d_map")
        self.vis_type_choice_group.addButton(self.radio_2d_map, 1)
        self.radio_3d_globe = QRadioButton("3D Globe")
        self.radio_3d_globe.toggled.connect(self.toggle_3d_options)
        self.safe_add_widget(vis_type_layout, self.radio_3d_globe, "radio_3d_globe")
        self.vis_type_choice_group.addButton(self.radio_3d_globe, 2)
        vis_type_group.setLayout(vis_type_layout)
        self.safe_add_widget(input_layout, vis_type_group, "vis_type_group")
        input_layout.addSpacerItem(QSpacerItem(0, 10))

        # 3D globe options
        self.globe_options_group = QGroupBox("3D Globe Options")
        globe_options_layout = QVBoxLayout()
        globe_options_layout.setSpacing(5)
        self.checkbox_show_scan_boxes = QCheckBox("Show Scan Area Boxes")
        self.checkbox_show_scan_boxes.setChecked(True)
        self.checkbox_show_scan_boxes.setEnabled(False)
        self.safe_add_widget(globe_options_layout, self.checkbox_show_scan_boxes, "checkbox_show_scan_boxes")
        self.checkbox_enable_live_updates = QCheckBox("Enable Live Updates")
        self.checkbox_enable_live_updates.setChecked(True)
        self.checkbox_enable_live_updates.stateChanged.connect(self.toggle_live_updates)
        self.safe_add_widget(globe_options_layout, self.checkbox_enable_live_updates, "checkbox_enable_live_updates")
        self.recenter_button = QPushButton("Recenter on Satellite")
        self.recenter_button.setEnabled(False)
        self.recenter_button.clicked.connect(self.recenter_on_satellite)
        self.safe_add_widget(globe_options_layout, self.recenter_button, "recenter_button")
        self.globe_options_group.setLayout(globe_options_layout)
        self.safe_add_widget(input_layout, self.globe_options_group, "globe_options_group")
        input_layout.addSpacerItem(QSpacerItem(0, 10))

        # Visualize button and status
        self.visualize_button = QPushButton("Calculate & Visualize Orbit")
        self.visualize_button.clicked.connect(self.on_visualize_click)
        self.safe_add_widget(input_layout, self.visualize_button, "visualize_button")
        self.status_label = QLabel("")
        self.safe_add_widget(input_layout, self.status_label, "status_label")
        input_layout.addStretch(1)

        # Wrap input_group in QScrollArea
        self.input_group.setLayout(input_layout)
        self.scroll_area = QScrollArea()
        if self.scroll_area is None:
            print("ERROR: Failed to create QScrollArea")
            return
        self.scroll_area.setWidget(self.input_group)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setMinimumWidth(300)
        self.scroll_area.setMinimumHeight(400)  # Ensure inputs are visible
        print("DEBUG: QScrollArea created and configured")

        # Splitter
        self.splitter = QSplitter(Qt.Horizontal)
        if self.scroll_area is None or self.map_view is None or self.output_group is None:
            print("ERROR: One or more splitter widgets are None: scroll_area=%s, map_view=%s, output_group=%s" % 
                  (self.scroll_area, self.map_view, self.output_group))
            return
        self.safe_add_widget(self.splitter, self.scroll_area, "scroll_area")
        self.safe_add_widget(self.splitter, self.map_view, "map_view")
        self.safe_add_widget(self.splitter, self.output_group, "output_group")
        self.splitter.setSizes([300, 600, 300])
        self.scroll_area.setMinimumWidth(300)
        self.map_view.setMinimumWidth(400)
        self.output_group.setMinimumWidth(250)
        self.splitter.splitterMoved.connect(self.on_splitter_moved)
        self.safe_add_widget(self.main_layout, self.splitter, "splitter")
        print("DEBUG: Input panel created successfully")

    def on_splitter_moved(self):
        if not self.map_initialized:
            return
        if self.vis_type_choice_group.checkedId() == 1:
            self.map_view.page().runJavaScript("if (typeof map !== 'undefined' && map) map.invalidateSize();")
        elif self.vis_type_choice_group.checkedId() == 2:
            self.map_view.page().runJavaScript("""
                if (typeof renderer !== 'undefined' && renderer && typeof camera !== 'undefined' && camera) {
                    renderer.setSize(window.innerWidth, window.innerHeight);
                    camera.aspect = window.innerWidth / window.innerHeight;
                    camera.updateProjectionMatrix();
                }
            """)

    def recenter_on_satellite(self):
        if (self.vis_type_choice_group.checkedId() == 2 and 
            self.map_initialized and 
            self.live_sat_pos_geodetic and 
            all(isinstance(x, (int, float)) for x in self.live_sat_pos_geodetic[:3])):
            lat, lon, alt, _ = self.live_sat_pos_geodetic
            self.map_view.page().runJavaScript(f"""
                if (typeof recenterOnSatellite !== 'undefined') {{
                    recenterOnSatellite({lat}, {lon}, {alt});
                }}
            """)
        else:
            QMessageBox.warning(self, "Recenter Error", "Cannot recenter: 3D globe not active or no valid satellite position.")

    def toggle_date_entry(self):
        self.start_date_entry.setEnabled(self.start_date_choice_group.checkedId() == 1)

    def toggle_3d_options(self):
        is_3d_selected = (self.vis_type_choice_group.checkedId() == 2)
        self.checkbox_show_scan_boxes.setEnabled(is_3d_selected)
        self.recenter_button.setEnabled(is_3d_selected and self.map_initialized and self.live_sat_pos_geodetic is not None)

    def toggle_live_updates(self, state):
        if state == Qt.Checked:
            if self.tle1 and self.tle2 and len(self.tle1) == 69 and len(self.tle2) == 69:
                self.live_update_timer.start()
                self.status_label.setText("Live updates enabled")
                self.update_live_position()
            else:
                self.status_label.setText("Live updates disabled: Invalid or missing TLE data")
                self.checkbox_enable_live_updates.setChecked(False)
        else:
            self.live_update_timer.stop()
            self.status_label.setText("Live updates disabled")

    def update_live_position(self):
        if not (self.tle1 and self.tle2 and len(self.tle1) == 69 and len(self.tle2) == 69):
            print("DEBUG: update_live_position skipped: Invalid TLE")
            return
        sat_id = self.tle1[2:7] if self.tle1 and len(self.tle1) >= 7 else "Unknown"
        _, _, _, _, _, live_sat_pos_geodetic, live_sat_pos_ecef = calculate_orbit_data(
            self.tle1, self.tle2, "", 1, 0, True, 0, 0, self.scan_area_size, sat_id, self.satellite_name, live_only=True
        )
        if live_sat_pos_geodetic and live_sat_pos_ecef:
            self.live_sat_pos_geodetic = live_sat_pos_geodetic
            self.live_sat_pos_ecef = live_sat_pos_ecef
            live_lat, live_lon, live_alt, live_time = live_sat_pos_geodetic
            if self.vis_type_choice_group.checkedId() == 1 and self.map_initialized:
                js_code = f"""
                    if (window.liveSatelliteUpdater && window.liveSatelliteUpdater.update2DPosition) {{
                        window.liveSatelliteUpdater.update2DPosition({live_lat}, {live_lon}, {live_alt}, '{live_time.strftime('%Y-%m-%d %H:%M:%S')}');
                    }} else {{
                        updateLiveSatellite({live_lat}, {live_lon}, {live_alt}, '{live_time.strftime('%Y-%m-%d %H:%M:%S')}');
                    }}
                """
                self.map_view.page().runJavaScript(js_code)
            elif self.vis_type_choice_group.checkedId() == 2 and self.map_initialized:
                js_code = f"""
                    if (window.liveSatelliteUpdater && window.liveSatelliteUpdater.updatePosition) {{
                        window.liveSatelliteUpdater.updatePosition({live_lat}, {live_lon}, {live_alt}, '{live_time.strftime('%Y-%m-%d %H:%M:%S')}');
                    }} else {{
                        updateLiveSatellite({live_lat}, {live_lon}, {live_alt}, '{live_time.strftime('%Y-%m-%d %H:%M:%S')}');
                    }}
                """
                self.map_view.page().runJavaScript(js_code)
            self.toggle_3d_options()

    def on_visualize_click(self):
        self.tle1 = self.tle1_entry.text().strip() or None
        self.tle2 = self.tle2_entry.text().strip() or None
        self.satellite_name = self.sat_name_entry.text().strip() or "Unknown"
        start_date_str = self.start_date_entry.text().strip()
        rate_choice = self.rate_choice_group.checkedId()
        start_from_tle_date = (self.start_date_choice_group.checkedId() == 2)
        requested_time_h_str = self.sim_length_entry.text().strip()
        sampling_interval_str = self.sampling_interval_entry.text().strip()
        scan_area_str = self.scan_area_entry.text().strip()

        try:
            lat_str = self.target_lat_entry.text().strip()
            lon_str = self.target_lon_entry.text().strip()
            self.target_point_geodetic = [float(lat_str) if lat_str else None, float(lon_str) if lon_str else None]
        except ValueError:
            QMessageBox.critical(self, "Input Error", "Target Latitude and Longitude must be numbers or empty.")
            return

        try:
            self.requested_time_h_float = float(requested_time_h_str)
        except ValueError:
            QMessageBox.critical(self, "Input Error", "Simulation Length must be a number.")
            return

        try:
            self.sampling_interval = float(sampling_interval_str) if sampling_interval_str else 1.0
            if self.sampling_interval <= 0:
                raise ValueError
        except ValueError:
            QMessageBox.critical(self, "Input Error", "Sampling Interval must be a positive number.")
            return

        try:
            self.scan_area_size = float(scan_area_str) if scan_area_str else 200.0
            if self.scan_area_size <= 0:
                raise ValueError
        except ValueError:
            QMessageBox.critical(self, "Input Error", "Scanning Area Size must be a positive number.")
            return

        self.status_label.setText("Calculating orbit...")
        sat_id = self.tle1[2:7] if self.tle1 and len(self.tle1) >= 7 else "Unknown"
        message, orbit_data_main, covered_orbit_positions_with_time_and_box, target_point_geodetic_output, start_datetime_utc, live_sat_pos_geodetic, live_sat_pos_ecef = calculate_orbit_data(
            self.tle1, self.tle2, start_date_str, rate_choice, self.requested_time_h_float,
            start_from_tle_date, self.target_point_geodetic[0] or 0, self.target_point_geodetic[1] or 0,
            self.scan_area_size, sat_id, self.satellite_name, self.sampling_interval
        )
        self.start_datetime_utc = start_datetime_utc
        self.orbit_data_main = orbit_data_main
        self.covered_orbit_positions_with_time_and_box = covered_orbit_positions_with_time_and_box
        self.live_sat_pos_geodetic = live_sat_pos_geodetic
        self.live_sat_pos_ecef = live_sat_pos_ecef

        if "Error" in message:
            QMessageBox.critical(self, "Orbit Calculation Error", message)
            self.status_label.setText(f"Error: {message}")
        else:
            self.status_label.setText(f"Generating visualization... {message}")
            vis_type = self.vis_type_choice_group.checkedId()
            self.map_initialized = False
            if vis_type == 1:
                html_content, error = generate_2d_map_html(orbit_data_main, self.requested_time_h_float, covered_orbit_positions_with_time_and_box, target_point_geodetic_output, live_sat_pos_geodetic, sat_id, self.satellite_name)
                if error:
                    QMessageBox.warning(self, "Map Warning", error)
                else:
                    with open("satellite_orbit_2d_map.html", "w") as f:
                        f.write(html_content)
                    self.map_view.setUrl(QUrl.fromLocalFile(os.path.abspath("satellite_orbit_2d_map.html")))
                    self.map_initialized = True
                    self.update_live_position()
            elif vis_type == 2:
                show_scan_boxes = self.checkbox_show_scan_boxes.isChecked()
                self.generate_and_load_3d_globe(orbit_data_main, self.requested_time_h_float, covered_orbit_positions_with_time_and_box, target_point_geodetic_output, live_sat_pos_geodetic, show_scan_boxes, sat_id, self.satellite_name)
                self.map_initialized = True
                self.update_live_position()
            self.display_overpass_information(covered_orbit_positions_with_time_and_box, target_point_geodetic_output)
            self.status_label.setText(f"Orbit visualized successfully! {message}")
            if self.checkbox_enable_live_updates.isChecked():
                self.live_update_timer.start()

    def generate_and_load_3d_globe(self, orbit_data_all_points, requested_time_h_float, covered_orbit_positions_with_time_and_box, target_point_geodetic, live_sat_pos_geodetic, show_scan_boxes, sat_id, satellite_name):
        if not orbit_data_all_points:
            QMessageBox.warning(self, "Globe Warning", "No valid orbit data to display.")
            return
        orbit_data_geodetic = []
        for point in orbit_data_all_points:
            if point[3] == 0:
                orbit_data_geodetic.append([point[0], point[1], point[2]])
        covered_points_geodetic = [[p[0], p[1], p[2]] for p in covered_orbit_positions_with_time_and_box]
        live_sat_data_for_html = live_sat_pos_geodetic if live_sat_pos_geodetic else [0.0, 0.0, 0.0, datetime.now(timezone.utc)]
        scan_boxes_geodetic = prepare_3d_scan_box_data(orbit_data_all_points)
        html_content = generate_3d_globe_html(
            orbit_data_geodetic, covered_points_geodetic, target_point_geodetic, scan_boxes_geodetic,
            live_sat_data_for_html, show_scan_boxes, sat_id, satellite_name
        )
        with open("temp_3d_globe.html", "w", encoding="utf-8") as f:
            f.write(html_content)
        self.map_view.setUrl(QUrl.fromLocalFile(os.path.abspath("temp_3d_globe.html")))

    def display_overpass_information(self, covered_orbit_positions_with_time_and_box, target_point_geodetic):
        self.output_text_browser.clear()
        if not target_point_geodetic or None in target_point_geodetic:
            self.output_text_browser.append("No target point specified.")
            return
        target_lat, target_lon = target_point_geodetic
        self.output_text_browser.append(f"Target Point: Lat {target_lat:.2f}, Lon {target_lon:.2f}")
        if covered_orbit_positions_with_time_and_box:
            self.output_text_browser.append(f"Total Overpasses: {len(covered_orbit_positions_with_time_and_box)}")
            for i, (sat_lat, sat_lon, sat_alt, time, _) in enumerate(covered_orbit_positions_with_time_and_box, 1):
                self.output_text_browser.append(
                    f"Overpass {i}: Time: {time.strftime('%Y-%m-%d %H:%M:%S UTC')}, "
                    f"Sat Lat: {sat_lat:.2f}, Lon: {sat_lon:.2f}, Alt: {sat_alt:.2f} km"
                )
        else:
            self.output_text_browser.append("No overpasses found where the satellite's scan area covers the target point.")

def check_dependencies():
    required = ['PyQt5', 'pyproj', 'sgp4', 'numpy']
    missing = []
    for module in required:
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    return missing

def main():
    try:
        print("Checking dependencies...")
        missing_deps = check_dependencies()
        if missing_deps:
            print(f"Error: Missing dependencies: {', '.join(missing_deps)}")
            print("Install them using: pip install " + " ".join(missing_deps))
            sys.exit(1)
        print("Starting application...")
        app = QApplication(sys.argv)
        print("QApplication initialized")
        window = OrbitVisualizerApp()
        print("OrbitVisualizerApp created")
        window.show()
        print("Window shown, entering event loop...")
        sys.exit(app.exec_())
    except Exception as e:
        print(f"Error starting application: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()