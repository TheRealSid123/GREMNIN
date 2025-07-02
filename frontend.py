import os
import sys
import traceback
from backend import *

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QRadioButton, QGroupBox, QButtonGroup,
    QMessageBox, QTextBrowser, QCheckBox
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
        self.create_input_panel()
        self.create_map_panel()
        self.create_output_panel()

    def create_input_panel(self):
        self.input_group = QGroupBox("Orbit Parameters")
        input_layout = QVBoxLayout()
        self.input_group.setLayout(input_layout)
        self.input_group.setFixedWidth(450)
        form_layout_tle = QVBoxLayout()
        form_layout_tle.addWidget(QLabel("TLE Line 1:"))
        self.tle1_entry = QLineEdit()
        self.tle1_entry.setPlaceholderText("Enter TLE Line 1 (69 chars)")
        form_layout_tle.addWidget(self.tle1_entry)
        form_layout_tle.addWidget(QLabel("TLE Line 2:"))
        self.tle2_entry = QLineEdit()
        self.tle2_entry.setPlaceholderText("Enter TLE Line 2 (69 chars)")
        form_layout_tle.addWidget(self.tle2_entry)
        input_layout.addLayout(form_layout_tle)
        start_date_group = QGroupBox("Start Date Option")
        start_date_layout = QVBoxLayout()
        self.start_date_choice_group = QButtonGroup(self)
        self.radio_tle_date = QRadioButton("From TLE Date")
        self.radio_tle_date.setChecked(True)
        self.radio_tle_date.toggled.connect(self.toggle_date_entry)
        start_date_layout.addWidget(self.radio_tle_date)
        self.start_date_choice_group.addButton(self.radio_tle_date, 2)
        self.radio_select_date = QRadioButton("Select Date (DD-MM-YYYY)")
        self.radio_select_date.toggled.connect(self.toggle_date_entry)
        start_date_layout.addWidget(self.radio_select_date)
        self.start_date_choice_group.addButton(self.radio_select_date, 1)
        start_date_group.setLayout(start_date_layout)
        input_layout.addWidget(start_date_group)
        self.start_date_label = QLabel("Start Date:")
        self.start_date_entry = QLineEdit()
        self.start_date_entry.setPlaceholderText("DD-MM-YYYY")
        self.start_date_entry.setEnabled(False)
        input_layout.addWidget(self.start_date_label)
        input_layout.addWidget(self.start_date_entry)
        rate_group = QGroupBox("Sampling Rate")
        rate_layout = QHBoxLayout()
        self.rate_choice_group = QButtonGroup(self)
        self.radio_seconds = QRadioButton("Seconds")
        self.radio_seconds.setChecked(True)
        rate_layout.addWidget(self.radio_seconds)
        self.rate_choice_group.addButton(self.radio_seconds, 1)
        self.radio_minutes = QRadioButton("Minutes")
        rate_layout.addWidget(self.radio_minutes)
        self.rate_choice_group.addButton(self.radio_minutes, 2)
        self.radio_hours = QRadioButton("Hours")
        rate_layout.addWidget(self.radio_hours)
        self.rate_choice_group.addButton(self.radio_hours, 3)
        rate_group.setLayout(rate_layout)
        input_layout.addWidget(rate_group)
        input_layout.addWidget(QLabel("Simulation Length (hours):"))
        self.sim_length_entry = QLineEdit()
        self.sim_length_entry.setPlaceholderText("e.g., 24 or -12")
        input_layout.addWidget(self.sim_length_entry)
        target_point_group = QGroupBox("Target Point for Coverage Check")
        target_point_layout = QVBoxLayout()
        target_point_layout.addWidget(QLabel("Target Latitude:"))
        self.target_lat_entry = QLineEdit()
        self.target_lat_entry.setPlaceholderText("e.g., 34.05")
        target_point_layout.addWidget(self.target_lat_entry)
        target_point_layout.addWidget(QLabel("Target Longitude:"))
        self.target_lon_entry = QLineEdit()
        self.target_lon_entry.setPlaceholderText("e.g., -118.25")
        target_point_layout.addWidget(self.target_lon_entry)
        target_point_group.setLayout(target_point_layout)
        input_layout.addWidget(target_point_group)
        vis_type_group = QGroupBox("Visualization Type")
        vis_type_layout = QHBoxLayout()
        self.vis_type_choice_group = QButtonGroup(self)
        self.radio_2d_map = QRadioButton("2D Map")
        self.radio_2d_map.setChecked(True)
        self.radio_2d_map.toggled.connect(self.toggle_3d_options)
        vis_type_layout.addWidget(self.radio_2d_map)
        self.vis_type_choice_group.addButton(self.radio_2d_map, 1)
        self.radio_3d_globe = QRadioButton("3D Globe")
        self.radio_3d_globe.toggled.connect(self.toggle_3d_options)
        vis_type_layout.addWidget(self.radio_3d_globe)
        self.vis_type_choice_group.addButton(self.radio_3d_globe, 2)
        vis_type_group.setLayout(vis_type_layout)
        input_layout.addWidget(vis_type_group)
        self.globe_options_group = QGroupBox("3D Globe Options")
        globe_options_layout = QVBoxLayout()
        self.checkbox_show_scan_boxes = QCheckBox("Show Scan Area Boxes")
        self.checkbox_show_scan_boxes.setChecked(True)
        self.checkbox_show_scan_boxes.setEnabled(False)
        globe_options_layout.addWidget(self.checkbox_show_scan_boxes)
        self.checkbox_enable_live_updates = QCheckBox("Enable Live Updates")
        self.checkbox_enable_live_updates.setChecked(True)
        self.checkbox_enable_live_updates.stateChanged.connect(self.toggle_live_updates)
        globe_options_layout.addWidget(self.checkbox_enable_live_updates)
        self.globe_options_group.setLayout(globe_options_layout)
        input_layout.addWidget(self.globe_options_group)
        self.visualize_button = QPushButton("Calculate & Visualize Orbit")
        self.visualize_button.clicked.connect(self.on_visualize_click)
        input_layout.addWidget(self.visualize_button)
        self.status_label = QLabel("")
        input_layout.addWidget(self.status_label)
        input_layout.addStretch(1)
        self.main_layout.addWidget(self.input_group)

    def create_map_panel(self):
        self.map_view = QWebEngineView()
        settings = self.map_view.page().settings()
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
        self.map_view.page().setWebChannel(self.web_channel)
        self.map_view.setUrl(QUrl("about:blank"))
        self.main_layout.addWidget(self.map_view)

    def create_output_panel(self):
        self.output_group = QGroupBox("Overpass Information")
        output_layout = QVBoxLayout()
        self.output_text_browser = QTextBrowser()
        self.output_text_browser.setHtml("Enter parameters and click 'Calculate & Visualize Orbit' to see overpass information.")
        output_layout.addWidget(self.output_text_browser)
        self.output_group.setLayout(output_layout)
        self.main_layout.addWidget(self.output_group)

    def toggle_date_entry(self):
        self.start_date_entry.setEnabled(self.start_date_choice_group.checkedId() == 1)

    def toggle_3d_options(self):
        is_3d_selected = (self.vis_type_choice_group.checkedId() == 2)
        self.checkbox_show_scan_boxes.setEnabled(is_3d_selected)

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
        _, _, _, _, _, live_sat_pos_geodetic, live_sat_pos_ecef = calculate_orbit_data(
            self.tle1, self.tle2, "", 1, 0, True, 0, 0, live_only=True
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

    def on_visualize_click(self):
        self.tle1 = self.tle1_entry.text().strip() or None
        self.tle2 = self.tle2_entry.text().strip() or None
        start_date_str = self.start_date_entry.text().strip()
        rate_choice = self.rate_choice_group.checkedId()
        start_from_tle_date = (self.start_date_choice_group.checkedId() == 2)
        requested_time_h_str = self.sim_length_entry.text().strip()

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

        self.status_label.setText("Calculating orbit...")
        message, orbit_data_main, covered_orbit_positions_with_time_and_box, target_point_geodetic_output, start_datetime_utc, live_sat_pos_geodetic, live_sat_pos_ecef = calculate_orbit_data(
            self.tle1, self.tle2, start_date_str, rate_choice, self.requested_time_h_float,
            start_from_tle_date, self.target_point_geodetic[0] or 0, self.target_point_geodetic[1] or 0
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
                html_content, error = generate_2d_map_html(orbit_data_main, self.requested_time_h_float, covered_orbit_positions_with_time_and_box, target_point_geodetic_output, live_sat_pos_geodetic)
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
                self.generate_and_load_3d_globe(orbit_data_main, self.requested_time_h_float, covered_orbit_positions_with_time_and_box, target_point_geodetic_output, live_sat_pos_geodetic, show_scan_boxes)
                self.map_initialized = True
                self.update_live_position()
            self.display_overpass_information(covered_orbit_positions_with_time_and_box, target_point_geodetic_output)
            self.status_label.setText(f"Orbit visualized successfully! {message}")
            if self.checkbox_enable_live_updates.isChecked():
                self.live_update_timer.start()

    def generate_and_load_3d_globe(self, orbit_data_all_points, requested_time_h_float, covered_orbit_positions_with_time_and_box, target_point_geodetic, live_sat_pos_geodetic, show_scan_boxes):
        """
        Prepares and loads data for the 3D globe using only geodetic coordinates.
        """
        if not orbit_data_all_points:
            QMessageBox.warning(self, "Globe Warning", "No valid orbit data to display.")
            return

        orbit_data_geodetic = []
        for point in orbit_data_all_points:
            if point[3] == 0:
                orbit_data_geodetic.append([point[0], point[1], point[2]])

        covered_points_geodetic = [[p[0], p[1], p[2]] for p in covered_orbit_positions_with_time_and_box]
        live_sat_data_for_html = self.live_sat_pos_geodetic if self.live_sat_pos_geodetic else None
        scan_boxes_geodetic = prepare_3d_scan_box_data(orbit_data_all_points)

        html_content = generate_3d_globe_html(
            orbit_data_geodetic,
            covered_points_geodetic,
            target_point_geodetic,
            scan_boxes_geodetic,
            live_sat_data_for_html,
            show_scan_boxes
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
    """Check if required dependencies are installed."""
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