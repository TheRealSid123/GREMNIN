import re
import math
import json
from sgp4.api import Satrec, jday
from pyproj import Transformer
from datetime import datetime, timedelta, timezone

days_in_month_prefix_sum = [0, 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]

def date_format_check(startdate_str):
    pattern = r"^\d{2}-\d{2}-\d{4}$"
    return bool(re.match(pattern, startdate_str))

def get_day_of_year(day, month, year):
    is_leap = (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0))
    day_of_year = day + days_in_month_prefix_sum[month]
    if is_leap and month > 2:
        day_of_year += 1
    return day_of_year

def gmst(julian_date):
    d = julian_date - 2451545.0
    T = d / 36525.0
    gmst_radians = 280.46061837 + 360.98564736629 * d + 0.000387933 * T**2 - T**3 / 38710000.0
    return math.radians(gmst_radians % 360.0)

def teme_to_ecef(teme_pos, julian_date):
    theta = gmst(julian_date)
    R = [
        [math.cos(theta),  math.sin(theta), 0],
        [-math.sin(theta), math.cos(theta), 0],
        [0,               0,              1]
    ]
    x, y, z = teme_pos
    ecef_x = R[0][0] * x + R[0][1] * y + R[0][2] * z
    ecef_y = R[1][0] * x + R[1][1] * y + R[1][2] * z
    ecef_z = R[2][0] * x + R[2][1] * y + R[2][2] * z
    return (ecef_x, ecef_y, ecef_z)

def ecef_to_geodetic(ecef_pos):
    transformer = Transformer.from_crs(
        {"proj": "geocent", "ellps": "WGS84", "datum": "WGS84"},
        {"proj": "latlong", "ellps": "WGS84", "datum": "WGS84"},
        always_xy=True
    )
    x, y, z = ecef_pos
    lon, lat, alt = transformer.transform(x * 1000, y * 1000, z * 1000)
    return lat, lon, alt / 1000.0

def geodetic_to_cartesian_ecef(lat_deg, lon_deg, alt_km):
    a = 6378.137
    f = 1 / 298.257223563
    e2 = 2 * f - f**2
    lat_rad = math.radians(lat_deg)
    lon_rad = math.radians(lon_deg)
    N = a / math.sqrt(1 - e2 * math.sin(lat_rad)**2)
    X = (N + alt_km) * math.cos(lat_rad) * math.cos(lon_rad)
    Y = (N + alt_km) * math.cos(lat_rad) * math.sin(lon_rad)
    Z = (N * (1 - e2) + alt_km) * math.sin(lat_rad)
    print(f"DEBUG: geodetic_to_cartesian_ecef(lat={lat_deg:.2f}, lon={lon_deg:.2f}, alt={alt_km:.2f}) -> ECEF=({X:.2f}, {Y:.2f}, {Z:.2f})")
    return X, Y, Z

def lat_change(distance_km):
    earth_radius_km = 6371
    return (distance_km / earth_radius_km) * (180 / math.pi)

def lon_change(lat_deg, distance_km):
    lat_rad = math.radians(lat_deg)
    earth_radius_at_lat = 6371 * math.cos(lat_rad)
    if abs(earth_radius_at_lat) < 1e-9:
        return 0
    return (distance_km / earth_radius_at_lat) * (180 / math.pi)

def get_scanning_square_corners(sat_lat, sat_lon, scan_half_width_km=100):
    try:
        if not (-90 <= sat_lat <= 90 and -180 <= sat_lon <= 180):
            raise ValueError(f"Invalid satellite coordinates: lat={sat_lat}, lon={sat_lon}")
        delta_lat = lat_change(scan_half_width_km)
        delta_lon = lon_change(sat_lat, scan_half_width_km)
        min_lat = sat_lat - delta_lat
        max_lat = sat_lat + delta_lat
        min_lon = sat_lon - delta_lon
        max_lon = sat_lon + delta_lon
        min_lon = (min_lon + 180) % 360 - 180
        max_lon = (max_lon + 180) % 360 - 180
        return [min_lat, max_lat, min_lon, max_lon]
    except ValueError as e:
        print(f"Error in get_scanning_square_corners: {e}")
        return [0.0, 0.0, 0.0, 0.0]

def is_point_in_scan_area(target_lat, target_lon, scan_box):
    try:
        min_lat, max_lat, min_lon, max_lon = scan_box
        if not all(isinstance(x, (int, float)) for x in [min_lat, max_lat, min_lon, max_lon]):
            print(f"Invalid scan box coordinates: {scan_box}")
            return False
        if not (min_lat <= target_lat <= max_lat):
            return False
        if min_lon <= max_lon:
            return min_lon <= target_lon <= max_lon
        else:
            return (min_lon <= target_lon <= 180) or (-180 <= target_lon <= max_lon)
    except Exception as e:
        print(f"Error in is_point_in_scan_area: {e}")
        return False

def calculate_orbit_data(tle1, tle2, start_date_str, rate_choice, requested_time_h_float, start_from_tle_date, target_lat, target_lon, scan_area_size, sat_id, satellite_name, sampling_interval=1.0, live_only=False):
    if not (tle1 and tle2 and len(tle1) == 69 and len(tle2) == 69):
        return "Error: Please enter valid TLE lines (69 characters each).", None, None, None, None, None, None
    try:
        satellite = Satrec.twoline2rv(tle1, tle2)
    except Exception as e:
        return f"Error parsing TLE: {e}", None, None, None, None, None, None
    current_utc_dt = datetime.now(timezone.utc)
    jd_live, fr_live = jday(current_utc_dt.year, current_utc_dt.month, current_utc_dt.day,
                            current_utc_dt.hour, current_utc_dt.minute, current_utc_dt.second + current_utc_dt.microsecond / 1e6)
    error_code_live, position_live, velocity_live = satellite.sgp4(jd_live, fr_live)
    live_sat_pos_geodetic = None
    live_sat_pos_ecef = None
    if error_code_live == 0:
        ecef_pos_live = teme_to_ecef(position_live, jd_live + fr_live)
        live_sat_lat, live_sat_lon, live_sat_alt = ecef_to_geodetic(ecef_pos_live)
        live_sat_pos_geodetic = [live_sat_lat, live_sat_lon, live_sat_alt, current_utc_dt]
        live_sat_pos_ecef = geodetic_to_cartesian_ecef(live_sat_lat, live_sat_lon, live_sat_alt)
        print(f"DEBUG: Live satellite position: lat={live_sat_lat:.2f}, lon={live_sat_lon:.2f}, alt={live_sat_alt:.2f}, ECEF={live_sat_pos_ecef}")
    else:
        print(f"WARNING: Could not calculate live satellite position. SGP4 Error: {error_code_live}")
        live_sat_pos_geodetic = [0.0, 0.0, 0.0, current_utc_dt]
        live_sat_pos_ecef = [0.0, 0.0, 6378.137 * 1.1]
    if live_only:
        return None, None, None, None, None, live_sat_pos_geodetic, live_sat_pos_ecef
    time_step_seconds = 0
    if rate_choice == 1:
        time_step_seconds = sampling_interval
    elif rate_choice == 2:
        time_step_seconds = sampling_interval * 60
    elif rate_choice == 3:
        time_step_seconds = sampling_interval * 3600
    else:
        return "Error: Invalid sampling rate choice.", None, None, None, None, None, None
    if requested_time_h_float == 0:
        return "Error: Please enter a non-zero value for simulation length.", None, None, None, None, None, None
    requested_time_seconds = requested_time_h_float * 3600
    num_samples = int(math.ceil(abs(requested_time_seconds) / time_step_seconds))
    orbit_data_main = []
    covered_orbit_positions_with_time_and_box = []
    jd_epoch, fr_epoch = 0, 0
    start_datetime_utc = None
    if start_from_tle_date:
        try:
            year_short = int(tle1[18:20])
            full_year = year_short + (2000 if year_short < 57 else 1900)
            day_of_year_float = float(tle1[20:32])
            days_offset = int(day_of_year_float) - 1
            fraction_of_day = day_of_year_float - days_offset
            seconds_in_fraction = fraction_of_day * 86400
            tle_epoch_datetime = datetime(full_year, 1, 1, tzinfo=timezone.utc) + timedelta(days=days_offset, seconds=seconds_in_fraction)
            start_datetime_utc = tle_epoch_datetime
            jd_epoch, fr_epoch = jday(tle_epoch_datetime.year, tle_epoch_datetime.month, tle_epoch_datetime.day,
                                      tle_epoch_datetime.hour, tle_epoch_datetime.minute, tle_epoch_datetime.second)
        except ValueError as e:
            return f"Error parsing TLE epoch: {e}", None, None, None, None, None, None
    else:
        if not date_format_check(start_date_str):
            return "Error: Please enter start date exactly as DD-MM-YYYY.", None, None, None, None, None, None
        parts = start_date_str.split('-')
        try:
            day = int(parts[0])
            month = int(parts[1])
            year = int(parts[2])
            start_datetime_utc = datetime(year, month, day, 0, 0, 0, tzinfo=timezone.utc)
            jd_epoch, fr_epoch = jday(start_datetime_utc.year, start_datetime_utc.month, start_datetime_utc.day,
                                      start_datetime_utc.hour, start_datetime_utc.minute, start_datetime_utc.second)
        except ValueError as e:
            return f"Error converting selected date to Julian: {e}", None, None, None, None, None, None
    total_found_times = 0
    successful_propagations = 0
    sgp4_error_codes_encountered = {}
    for i in range(num_samples + 1):
        current_datetime_sample = start_datetime_utc + timedelta(seconds=i * time_step_seconds * (1 if requested_time_h_float >= 0 else -1))
        jd_current_sample, fr_current_sample = jday(current_datetime_sample.year, current_datetime_sample.month, current_datetime_sample.day,
                                                    current_datetime_sample.hour, current_datetime_sample.minute, current_datetime_sample.second + current_datetime_sample.microsecond / 1e6)
        error_code, position, velocity = satellite.sgp4(jd_current_sample, fr_current_sample)
        current_sat_lat, current_sat_lon, current_sat_alt = 0.0, 0.0, 0.0
        scan_box_min_lat, scan_box_max_lat, scan_box_min_lon, scan_box_max_lon = 0.0, 0.0, 0.0, 0.0
        is_covered_flag = 0
        if error_code == 0:
            successful_propagations += 1
            ecef_pos = teme_to_ecef(position, jd_current_sample + fr_current_sample)
            current_sat_lat, current_sat_lon, current_sat_alt = ecef_to_geodetic(ecef_pos)
            scan_box_corners = get_scanning_square_corners(current_sat_lat, current_sat_lon, scan_half_width_km=scan_area_size / 2)
            if all(isinstance(x, (int, float)) for x in scan_box_corners):
                scan_box_min_lat, scan_box_max_lat, scan_box_min_lon, scan_box_max_lon = scan_box_corners
                if is_point_in_scan_area(target_lat, target_lon, scan_box_corners):
                    is_covered_flag = 1
                    covered_orbit_positions_with_time_and_box.append([current_sat_lat, current_sat_lon, current_sat_alt, current_datetime_sample, scan_box_corners])
                    total_found_times += 1
            else:
                print(f"DEBUG: Invalid scan box corners at sample {i}: {scan_box_corners}")
        else:
            print(f"DEBUG: SGP4 Error: Sample {i}, Code {error_code} (JD={jd_current_sample+fr_current_sample:.5f})")
            sgp4_error_codes_encountered[error_code] = sgp4_error_codes_encountered.get(error_code, 0) + 1
        orbit_data_main.append([
            current_sat_lat, current_sat_lon, current_sat_alt, error_code,
            is_covered_flag, scan_box_min_lat, scan_box_max_lat, scan_box_min_lon, scan_box_max_lon
        ])
    if successful_propagations == 0:
        error_details = ", ".join([f"Code {code}: {count} times" for code, count in sgp4_error_codes_encountered.items()])
        if not error_details and num_samples > 0:
            error_details = "No specific SGP4 errors recorded. This might indicate an issue with TLE epoch or initial conditions."
        elif num_samples == 0:
            error_details = "Simulation length resulted in zero samples."
        return f"Error: SGP4 failed to propagate for any requested point. Details: {error_details}.", None, None, None, None, None, None
    else:
        message = f"Orbit data calculated successfully. Total propagated points: {successful_propagations}. Satellite can scan target point {total_found_times} times."
        if sgp4_error_codes_encountered:
            message += f" (Note: Some SGP4 errors occurred for codes: {sgp4_error_codes_encountered})"
        return message, orbit_data_main, covered_orbit_positions_with_time_and_box, [target_lat, target_lon], start_datetime_utc, live_sat_pos_geodetic, live_sat_pos_ecef

def prepare_3d_scan_box_data(orbit_data_all_points):
    scan_boxes_3d = []
    for point_data in orbit_data_all_points:
        error_code = point_data[3]
        if error_code == 0:
            is_covered_flag = point_data[4]
            min_lat, max_lat, min_lon, max_lon = point_data[5], point_data[6], point_data[7], point_data[8]
            if all(isinstance(x, (int, float)) for x in [min_lat, max_lat, min_lon, max_lon]):
                scan_boxes_3d.append([min_lat, max_lat, min_lon, max_lon, is_covered_flag])
    return scan_boxes_3d

def generate_3d_globe_html(orbit_data_geodetic, covered_points_geodetic, target_point_geodetic,
                           scan_boxes_geodetic, live_sat_data_full, show_scan_boxes_js, sat_id, satellite_name):
    earth_texture_url = "https://raw.githubusercontent.com/mrdoob/three.js/dev/examples/textures/planets/earth_atmos_2048.jpg"
    live_sat_data_for_json = live_sat_data_full if live_sat_data_full else [0.0, 0.0, 0.0, datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')]
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>3D Satellite Orbit</title>
        <style>body {{ margin: 0; overflow: hidden; }} canvas {{ display: block; }}</style>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/qwebchannel/5.15.0/qwebchannel.js"></script>
    </head>
    <body>
        <script>
            const orbitData = {json.dumps(orbit_data_geodetic)};
            const coveredPointsData = {json.dumps(covered_points_geodetic)};
            const targetData = {json.dumps(target_point_geodetic)};
            const liveSatDataFull = {json.dumps(live_sat_data_for_json, default=str)};
            const scanBoxesData = {json.dumps(scan_boxes_geodetic)};
            const showScanBoxes = {json.dumps(show_scan_boxes_js)};
            const satId = '{sat_id}';
            const satName = '{satellite_name}';
            const scene = new THREE.Scene();
            scene.background = new THREE.Color(0x101015);
            const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 100000);
            const renderer = new THREE.WebGLRenderer({{ antialias: true }});
            renderer.setSize(window.innerWidth, window.innerHeight);
            document.body.appendChild(renderer.domElement);
            const earthRadius = 6378.137;
            camera.position.set(0, earthRadius * 1.2, earthRadius * 1.8);
            function latLonAltToVector3(lat, lon, alt = 0) {{
                const R = earthRadius + alt;
                const phi = (90 - lat) * (Math.PI / 180);
                const theta = (lon + 180) * (Math.PI / 180);
                const x = -R * Math.sin(phi) * Math.cos(theta);
                const y = R * Math.cos(phi);
                const z = R * Math.sin(phi) * Math.sin(theta);
                return new THREE.Vector3(x, y, z);
            }}
            const earthGeometry = new THREE.SphereGeometry(earthRadius, 64, 64);
            const textureLoader = new THREE.TextureLoader();
            const earthMaterial = new THREE.MeshStandardMaterial({{
                map: textureLoader.load('{earth_texture_url}')
            }});
            const earth = new THREE.Mesh(earthGeometry, earthMaterial);
            scene.add(earth);
            scene.add(new THREE.AmbientLight(0xbbbbbb));
            const dirLight = new THREE.DirectionalLight(0xffffff, 0.6);
            dirLight.position.set(earthRadius*2, earthRadius, earthRadius*2);
            scene.add(dirLight);
            if (orbitData && Array.isArray(orbitData)) {{
                const points = orbitData.map(p => latLonAltToVector3(p[0], p[1], p[2]));
                const lineGeo = new THREE.BufferGeometry().setFromPoints(points);
                const lineMat = new THREE.LineBasicMaterial({{ color: 0xff4500, linewidth: 2 }});
                scene.add(new THREE.Line(lineGeo, lineMat));
            }}
            const createMarker = (lat, lon, color, size=25) => {{
                if (lat == null || lon == null || isNaN(lat) || isNaN(lon)) return;
                const marker = new THREE.Mesh(
                    new THREE.SphereGeometry(size, 16, 16),
                    new THREE.MeshBasicMaterial({{ color: color }})
                );
                marker.position.copy(latLonAltToVector3(lat, lon, 1));
                scene.add(marker);
                return marker;
            }};
            if (targetData && Array.isArray(targetData) && targetData[0] != null) {{
                createMarker(targetData[0], targetData[1], 0xff00ff);
            }}
            if (coveredPointsData && Array.isArray(coveredPointsData)) {{
                coveredPointsData.forEach(p => createMarker(p[0], p[1], 0xffa500, 15));
            }}
            if (showScanBoxes && scanBoxesData && Array.isArray(scanBoxesData)) {{
                scanBoxesData.forEach(box => {{
                    const [min_lat, max_lat, min_lon, max_lon, is_covered] = box;
                    if ([min_lat, max_lat, min_lon, max_lon].some(v => v == null || isNaN(v))) return;
                    const c1 = latLonAltToVector3(max_lat, min_lon, 5);
                    const c2 = latLonAltToVector3(max_lat, max_lon, 5);
                    const c3 = latLonAltToVector3(min_lat, max_lon, 5);
                    const c4 = latLonAltToVector3(min_lat, min_lon, 5);
                    const boxGeo = new THREE.BufferGeometry().setFromPoints([c1, c2, c3, c4, c1]);
                    const boxMat = new THREE.LineBasicMaterial({{
                        color: is_covered ? 0x00ff00 : 0x00ffff,
                        transparent: true,
                        opacity: is_covered ? 0.9 : 0.4
                    }});
                    scene.add(new THREE.Line(boxGeo, boxMat));
                }});
            }}
            let liveSatelliteObject = null;
            let liveSatelliteLabel = null;
            const satelliteBodyMaterial = new THREE.MeshStandardMaterial({{ color: 0x808080 }});
            const satellitePanelMaterial = new THREE.MeshStandardMaterial({{ color: 0x0000ff }});
            const satelliteDotMaterial = new THREE.MeshBasicMaterial({{ color: 0xffff00 }});
            function createSatelliteMesh() {{
                const bodyGeometry = new THREE.BoxGeometry(100, 50, 50);
                const body = new THREE.Mesh(bodyGeometry, satelliteBodyMaterial);
                const panelGeometry = new THREE.BoxGeometry(150, 5, 40);
                const panel1 = new THREE.Mesh(panelGeometry, satellitePanelMaterial);
                panel1.position.set(-125, 0, 0);
                body.add(panel1);
                const panel2 = new THREE.Mesh(panelGeometry, satellitePanelMaterial);
                panel2.position.set(125, 0, 0);
                body.add(panel2);
                const dotGeometry = new THREE.SphereGeometry(10, 16, 16);
                const dot = new THREE.Mesh(dotGeometry, satelliteDotMaterial);
                dot.position.set(0, 0, 25);
                body.add(dot);
                const satelliteGroup = new THREE.Group();
                satelliteGroup.add(body);
                return satelliteGroup;
            }}
            function createSatelliteLabel(text) {{
                const canvas = document.createElement('canvas');
                canvas.width = 128;
                canvas.height = 32;
                const context = canvas.getContext('2d');
                context.fillStyle = 'rgba(0, 0, 0, 0.7)';
                context.fillRect(0, 0, canvas.width, canvas.height);
                context.font = '16px Arial';
                context.fillStyle = 'white';
                context.textAlign = 'center';
                context.textBaseline = 'middle';
                context.fillText(text, canvas.width / 2, canvas.height / 2);
                const texture = new THREE.CanvasTexture(canvas);
                const spriteMaterial = new THREE.SpriteMaterial({{ map: texture }});
                const sprite = new THREE.Sprite(spriteMaterial);
                sprite.scale.set(100, 25, 1);
                return sprite;
            }}
            function updateLiveSatellite(lat, lon, alt, time_str) {{
                console.log('updateLiveSatellite called with:', {{lat, lon, alt, time_str}});
                if (lat == null || lon == null || alt == null || isNaN(lat) || isNaN(lon) || isNaN(alt)) {{
                    console.warn('Invalid live satellite data for 3D update, skipping:', {{lat, lon, alt}});
                    return;
                }}
                if (!liveSatelliteObject) {{
                    liveSatelliteObject = createSatelliteMesh();
                    scene.add(liveSatelliteObject);
                    console.log('Satellite object created and added to scene.');
                }}
                if (!liveSatelliteLabel) {{
                    liveSatelliteLabel = createSatelliteLabel(satName);
                    scene.add(liveSatelliteLabel);
                    console.log('Satellite label created and added to scene.');
                }}
                const position = latLonAltToVector3(lat, lon, alt);
                liveSatelliteObject.position.copy(position);
                liveSatelliteLabel.position.copy(position);
                liveSatelliteLabel.position.x += 50;
                console.log('Satellite new position:', liveSatelliteObject.position.x, liveSatelliteObject.position.y, liveSatelliteObject.position.z);
            }}
            function recenterOnSatellite(lat, lon, alt) {{
                if (lat == null || lon == null || alt == null || isNaN(lat) || isNaN(lon) || isNaN(alt)) {{
                    console.warn('Invalid coordinates for recentering:', {{lat, lon, alt}});
                    return;
                }}
                const satPosition = latLonAltToVector3(lat, lon, alt);
                camera.position.set(
                    satPosition.x,
                    satPosition.y + earthRadius * 0.2,
                    satPosition.z + earthRadius * 0.5
                );
                camera.lookAt(satPosition);
                controls.target.copy(satPosition);
                controls.update();
                console.log('Camera recentered on satellite at:', {{lat, lon, alt}});
            }}
            if (liveSatDataFull && Array.isArray(liveSatDataFull) && liveSatDataFull[0] != null) {{
                console.log('Initial live satellite data:', liveSatDataFull);
                updateLiveSatellite(liveSatDataFull[0], liveSatDataFull[1], liveSatDataFull[2], liveSatDataFull[3]);
            }}
            const controls = new THREE.OrbitControls(camera, renderer.domElement);
            controls.minDistance = earthRadius * 1.05;
            function animate() {{
                requestAnimationFrame(animate);
                controls.update();
                renderer.render(scene, camera);
            }}
            animate();
            new QWebChannel(qt.webChannelTransport, function(channel) {{
                console.log('QWebChannel initialized for 3D globe');
                window.liveSatelliteUpdater = channel.objects.liveSatelliteUpdater;
                if (window.liveSatelliteUpdater) {{
                    window.liveSatelliteUpdater.updatePosition.connect(function(lat, lon, alt, time_str) {{
                        updateLiveSatellite(lat, lon, alt, time_str);
                    }});
                    console.log('updatePosition connected successfully.');
                }} else {{
                    console.error('liveSatelliteUpdater object not found in QWebChannel.');
                }}
            }});
        </script>
    </body>
    </html>
    """
    return html_content

def generate_2d_map_html(orbit_data_all_points, requested_time_h_float, covered_orbit_positions_with_time_and_box, target_point_geodetic, live_sat_pos_geodetic, sat_id, satellite_name):
    if not orbit_data_all_points:
        return None, "No valid orbit data to display on map."
    initial_lat = 0
    initial_lon = 0
    found_initial = False
    filtered_orbit_points_for_line = []
    for point_data in orbit_data_all_points:
        error_code = point_data[3]
        if error_code == 0:
            point_lat = point_data[0]
            point_lon = point_data[1]
            filtered_orbit_points_for_line.append([point_lat, point_lon])
            if not found_initial:
                initial_lat = point_lat
                initial_lon = point_lon
                found_initial = True
    if not found_initial:
        return None, "No successful orbit points found."
    map_center_lat = target_point_geodetic[0] if target_point_geodetic and target_point_geodetic[0] is not None else initial_lat
    map_center_lon = target_point_geodetic[1] if target_point_geodetic and target_point_geodetic[1] is not None else initial_lon
    live_sat_data = live_sat_pos_geodetic if live_sat_pos_geodetic else [0.0, 0.0, 0.0, datetime.now(timezone.utc)]
    live_lat, live_lon, live_alt, live_time = live_sat_data
    covered_points = [[p[0], p[1]] for p in covered_orbit_positions_with_time_and_box if p[0] is not None and p[1] is not None]
    valid_scan_boxes = []
    for p in orbit_data_all_points:
        if p[3] == 0 and all(isinstance(x, (int, float)) for x in [p[5], p[6], p[7], p[8]]):
            valid_scan_boxes.append([p[5], p[6], p[7], p[8], p[4]])
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>2D Satellite Orbit Map</title>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.3/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.3/dist/leaflet.js"></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/qwebchannel/5.15.0/qwebchannel.js"></script>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css">
        <style>
            .satellite-label {{ 
                background: rgba(0, 0, 0, 0.7); 
                color: white; 
                padding: 2px 5px; 
                border-radius: 3px; 
                font-size: 12px; 
                white-space: nowrap;
            }}
        </style>
    </head>
    <body>
        <div id="map" style="height: 100vh;"></div>
        <script>
            let map, liveMarker, liveLabel;
            const orbitPoints = {json.dumps(filtered_orbit_points_for_line)};
            const targetPoint = {json.dumps(target_point_geodetic if target_point_geodetic and None not in target_point_geodetic else None)};
            const coveredPoints = {json.dumps(covered_points)};
            const scanBoxes = {json.dumps(valid_scan_boxes)};
            const initialLiveSat = {json.dumps([live_lat, live_lon, live_alt, live_time.strftime('%Y-%m-%d %H:%M:%S')] if live_sat_pos_geodetic else [0.0, 0.0, 0.0, datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')])};
            console.log('Initializing 2D map...');
            map = L.map('map').setView([{map_center_lat}, {map_center_lon}], 4);
            L.tileLayer('https://cartodb-basemaps-{{s}}.global.ssl.fastly.net/dark_all/{{z}}/{{x}}/{{y}}.png', {{
                attribution: '© <a href="https://carto.com/attributions">CARTO</a>',
                subdomains: 'abcd',
                maxZoom: 19
            }}).addTo(map);
            if (orbitPoints && Array.isArray(orbitPoints) && orbitPoints.length > 1) {{
                let currentSegment = [orbitPoints[0]];
                for (let i = 1; i < orbitPoints.length; i++) {{
                    let prevPoint = orbitPoints[i-1];
                    let currentPoint = orbitPoints[i];
                    let lonDiff = Math.abs(currentPoint[1] - prevPoint[1]);
                    if ((prevPoint[1] < -90 && currentPoint[1] > 90) || 
                        (prevPoint[1] > 90 && currentPoint[1] < -90) || 
                        (lonDiff > 270)) {{
                        if (currentSegment.length > 1) {{
                            L.polyline(currentSegment, {{color: 'red', weight: 2.5, opacity: 1}}).addTo(map);
                        }}
                        currentSegment = [currentPoint];
                    }} else {{
                        currentSegment.push(currentPoint);
                    }}
                }}
                if (currentSegment.length > 1) {{
                    L.polyline(currentSegment, {{color: 'red', weight: 2.5, opacity: 1}}).addTo(map);
                }}
                L.marker(orbitPoints[0], {{icon: L.divIcon({{className: 'fas fa-play', html: '<i class="fas fa-play" style="color:blue;font-size:16px;"></i>'}})}})
                    .bindPopup('Orbit Start').addTo(map);
                L.marker(orbitPoints[orbitPoints.length-1], {{icon: L.divIcon({{className: 'fas fa-stop', html: '<i class="fas fa-stop" style="color:green;font-size:16px;"></i>'}})}})
                    .bindPopup('Orbit End').addTo(map);
            }}
            if (targetPoint && Array.isArray(targetPoint) && targetPoint[0] != null && targetPoint[1] != null) {{
                L.marker([targetPoint[0], targetPoint[1]], {{icon: L.divIcon({{className: 'fas fa-crosshairs', html: '<i class="fas fa-crosshairs" style="color:purple;font-size:16px;"></i>'}})}})
                    .bindPopup(`Target: Lat ${{targetPoint[0].toFixed(2)}}, Lon ${{targetPoint[1].toFixed(2)}}`)
                    .addTo(map);
            }}
            if (scanBoxes && Array.isArray(scanBoxes)) {{
                scanBoxes.forEach(box => {{
                    const minLat = box[0], maxLat = box[1], minLon = box[2], maxLon = box[3], isCovered = box[4];
                    if ([minLat, maxLat, minLon, maxLon].some(coord => coord == null || isNaN(coord))) {{
                        console.warn('Invalid scan box coordinates:', box);
                        return;
                    }}
                    const boxColor = isCovered ? 'limegreen' : 'deepskyblue';
                    const fillOpacity = isCovered ? 0.1 : 0.03;
                    const tooltipText = isCovered ? 'Sat Scan Area (Covering Target!)' : 'Sat Scan Area';
                    if (minLon > maxLon || Math.abs(maxLon - minLon) > 270) {{
                        L.polygon([
                            [maxLat, minLon], [maxLat, 180], [minLat, 180], [minLat, minLon]
                        ], {{
                            color: boxColor, weight: 1, fill: true, fillColor: boxColor, fillOpacity: fillOpacity
                        }}).bindTooltip(tooltipText).addTo(map);
                        L.polygon([
                            [maxLat, -180], [maxLat, maxLon], [minLat, maxLon], [minLat, -180]
                        ], {{
                            color: boxColor, weight: 1, fill: true, fillColor: boxColor, fillOpacity: fillOpacity
                        }}).bindTooltip(tooltipText).addTo(map);
                    }} else {{
                        L.polygon([
                            [maxLat, minLon], [maxLat, maxLon], [minLat, maxLon], [minLat, minLon]
                        ], {{
                            color: boxColor, weight: 1, fill: true, fillColor: boxColor, fillOpacity: fillOpacity
                        }}).bindTooltip(tooltipText).addTo(map);
                    }}
                }});
            }}
            if (coveredPoints && Array.isArray(coveredPoints)) {{
                coveredPoints.forEach(pt => {{
                    if (pt && Array.isArray(pt) && pt.length === 2 && pt[0] != null && pt[1] != null) {{
                        L.circleMarker([pt[0], pt[1]], {{
                            radius: 2, color: 'orange', fill: true, fillColor: 'orange', fillOpacity: 0.7
                        }}).bindPopup(`Satellite covering target here.<br>Lat: ${{pt[0].toFixed(2)}}, Lon: ${{pt[1].toFixed(2)}}`).addTo(map);
                    }}
                }});
            }}
            function updateLiveSatellite(lat, lon, alt, time) {{
                console.log('updateLiveSatellite called with:', {{lat, lon, alt, time}});
                if (lat == null || lon == null || alt == null || isNaN(lat) || isNaN(lon)) {{
                    console.warn('Invalid live satellite data, using default:', {{lat, lon, alt, time}});
                    lat = 0.0; lon = 0.0; alt = 0.0; time = new Date().toISOString();
                }}
                if (liveMarker) {{
                    map.removeLayer(liveMarker);
                }}
                if (liveLabel) {{
                    map.removeLayer(liveLabel);
                }}
                liveMarker = L.marker([lat, lon], {{
                    icon: L.divIcon({{className: 'fas fa-satellite', html: '<i class="fas fa-satellite" style="color:yellow;font-size:16px;"></i>'}})
                }}).bindPopup(`<b>LIVE Satellite: {sat_id} - {satellite_name}</b><br>Time: ${{time}}<br>Lat: ${{lat.toFixed(2)}}, Lon: ${{lon.toFixed(2)}}<br>Alt: ${{alt.toFixed(2)}} km`)
                  .addTo(map);
                liveLabel = L.marker([lat, lon], {{
                    icon: L.divIcon({{
                        className: 'satellite-label',
                        html: `<div style="transform: translate(10px, 0);">{satellite_name}</div>`,
                        iconAnchor: [0, 0]
                    }})
                }}).addTo(map);
                console.log('Live satellite marker and label added at:', {{lat, lon, alt, time}});
            }}
            updateLiveSatellite(initialLiveSat[0], initialLiveSat[1], initialLiveSat[2], initialLiveSat[3]);
            new QWebChannel(qt.webChannelTransport, function(channel) {{
                console.log('QWebChannel initialized for 2D map');
                window.liveSatelliteUpdater = channel.objects.liveSatelliteUpdater;
                if (window.liveSatelliteUpdater) {{
                    window.liveSatelliteUpdater.update2DPosition.connect(function(lat, lon, alt, time) {{
                        updateLiveSatellite(lat, lon, alt, time);
                    }});
                }}
            }});
        </script>
    </body>
    </html>
    """
    return html_content, None