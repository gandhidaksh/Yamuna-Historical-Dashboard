"""
Yamuna Plotly Dashboard with Enhanced Insights, Data Input, and Map View
- Place 'Yamuna Report V3.0.xlsx' next to this script, or pick it in the file dialog.
- Run: python yamuna_dashboard.py
- The script writes 'yamuna_dashboard.html' next to the script and attempts to open it in your browser.
- Now includes interactive map view with lat/long coordinates from Excel
- Updated WQI boundaries: <50 (Excellent), 50-100 (Good), 100-200 (Poor), 200-300 (Very Poor), >300 (Unsuitable)
- Excludes WQI=0 values from analysis (but shows them on charts)
"""

from pathlib import Path
import sys
import json
import webbrowser
import datetime
import pandas as pd
import numpy as np

DEFAULT_EXCEL = "Yamuna Report V3.0.xlsx"
OUTPUT_HTML = "yamuna_dashboard.html"


# ----------------------- File locators / IO -----------------------
def locate_input_file():
    base = Path(__file__).resolve().parent
    candidate = base / DEFAULT_EXCEL
    if candidate.exists():
        return candidate
    # fallback - file dialog
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        file_path = filedialog.askopenfilename(
            title="Select Yamuna Excel file",
            filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")]
        )
        root.destroy()
        if not file_path:
            print("No file selected. Exiting.")
            sys.exit(1)
        return Path(file_path)
    except Exception as e:
        print("Could not find default Excel and file dialog not available:", e)
        sys.exit(1)


# ----------------------- Read + Normalize -----------------------
def read_excel_of_interest(path: Path) -> pd.DataFrame:
    try:
        return pd.read_excel(path, sheet_name="Working Sheet")
    except Exception:
        # try default sheet if Working Sheet missing
        return pd.read_excel(path)


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # sanitize column names
    df.columns = df.columns.astype(str).str.strip()

    # drop fully empty columns and Unnamed ones
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
    df = df.dropna(axis=1, how="all")

    # common renames if present
    col_map = {
        "TSS(mg/L)": "TSS_mg_L",
        "Total_Coliform_MPN_100ml": "Total_Coliform",
        "Faecal_Coliform_MPN_100ml": "Faecal_Coliform",
        "Surfactant (mg/L)": "Surfactant_mg_L",
        "COD (mg/l)": "COD_mg_L",  # sometimes alternate
        "BOD (mg/l)": "BOD_mg_L",
        "DO (mg/l)": "DO_mg_L",
    }
    for k, v in col_map.items():
        if k in df.columns and v not in df.columns:
            df = df.rename(columns={k: v})

    # Ensure Year exists
    if "Year" not in df.columns:
        cand = next((c for c in df.columns if c.lower().strip() == "year"), None)
        if cand:
            df = df.rename(columns={cand: "Year"})

    # Ensure Location exists
    if "Location" not in df.columns:
        cand = next((c for c in df.columns if "location" in c.lower() or "site" in c.lower() or "station" in c.lower()),
                    None)
        if cand:
            df = df.rename(columns={cand: "Location"})

    # Handle Lat/Long columns - preserve them if they exist
    lat_cols = [c for c in df.columns if c.lower() in ['lat', 'latitude']]
    lon_cols = [c for c in df.columns if c.lower() in ['long', 'lon', 'longitude']]

    if lat_cols:
        df = df.rename(columns={lat_cols[0]: "Lat"})
    if lon_cols:
        df = df.rename(columns={lon_cols[0]: "Long"})

    # Turn Date into datetime
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

    # If Date missing but Year & Month present -> build Date as Year-Month-01
    if "Date" not in df.columns and {"Year", "Month"} <= set(df.columns):
        month_map = {m: i for i, m in enumerate(
            ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
             "November", "December"], 1)}
        # normalize month strings
        df["Month"] = df["Month"].astype(str).str.strip()
        df["Month_Num"] = df["Month"].map(lambda v: month_map.get(v, None) if isinstance(v, str) else v)
        df["Date"] = pd.to_datetime(df["Year"].astype(str) + "-" + df["Month_Num"].astype(str) + "-01", errors="coerce")

    # If Month missing but Date present, derive Month
    if "Month" not in df.columns and "Date" in df.columns:
        df["Month"] = df["Date"].dt.strftime("%B")

    # Clean Year numeric
    if "Year" in df.columns:
        df["Year"] = pd.to_numeric(df["Year"], errors="coerce").astype("Int64")

    # Clean Lat/Long numeric
    if "Lat" in df.columns:
        df["Lat"] = pd.to_numeric(df["Lat"], errors="coerce")
    if "Long" in df.columns:
        df["Long"] = pd.to_numeric(df["Long"], errors="coerce")

    # Coerce numeric parameters where possible (non-essential)
    essential = {"Year", "Month", "Location", "Date", "Month_Num", "Lat", "Long"}
    for c in [c for c in df.columns if c not in essential]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Drop rows with no Date or Location
    if "Date" in df.columns and "Location" in df.columns:
        df = df.dropna(subset=["Date", "Location"], how="any")

    # Drop rows with no numeric value at all (but keep those that have at least one numeric param)
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    if len(numeric_cols):
        df = df[df[numeric_cols].notna().any(axis=1)]

    # Skip the weights row if it exists (row with description text in parameter columns)
    if len(df) > 0:
        # Check if first row contains weight descriptions
        first_row = df.iloc[0]
        if any(isinstance(val, str) and ("weight" in str(val).lower() or "ideal range" in str(val).lower()) for val in
               first_row.values):
            df = df.iloc[1:].reset_index(drop=True)

    df = df.reset_index(drop=True)
    return df


def prepare_json_rows(df: pd.DataFrame):
    def convert(v):
        if pd.isna(v):
            return None
        if isinstance(v, (pd.Timestamp, datetime.datetime, np.datetime64)):
            try:
                # ISO format so JS Date() can parse it
                return pd.to_datetime(v).isoformat()
            except Exception:
                return str(v)
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return float(v)
        return v

    rows = df.to_dict(orient="records")
    safe = [{k: convert(v) for k, v in r.items()} for r in rows]
    return safe


def prepare_lists_from_df(df: pd.DataFrame):
    def safe_unique(series):
        vals = []
        for v in series.dropna().unique().tolist():
            if v is None:
                continue
            s = str(v).strip()
            if s == "" or s.lower() == "nan":
                continue
            vals.append(s)
        # preserve order unique
        seen = set();
        out = []
        for v in vals:
            if v not in seen:
                seen.add(v);
                out.append(v)
        return out

    locations = safe_unique(df["Location"]) if "Location" in df.columns else []
    # ensure month order consistent
    months_possible = ["January", "February", "March", "April", "May", "June",
                       "July", "August", "September", "October", "November", "December"]
    months_in = safe_unique(df["Month"]) if "Month" in df.columns else []
    months = [m for m in months_possible if m in months_in] if months_in else months_possible

    years = []
    if "Year" in df.columns:
        try:
            ys = df["Year"].dropna().unique().tolist()
            years = sorted([int(y) for y in ys])
        except Exception:
            years = []
    if not years and "Date" in df.columns:
        years = sorted(list({int(d.year) for d in pd.to_datetime(df["Date"].dropna())}))

    if not months:
        months = months_possible
    if not locations:
        locations = ["No location found"]
    if not years:
        current = datetime.datetime.now().year
        years = list(range(current - 4, current + 1))
    return locations, months, years


def get_numeric_params(df: pd.DataFrame):
    essential = {"Year", "Month", "Location", "Date", "Month_Num", "Lat", "Long"}
    candidates = [c for c in df.columns if c not in essential]
    numeric_params = []

    for c in candidates:
        if pd.api.types.is_numeric_dtype(df[c]) and df[c].dropna().apply(lambda v: np.isfinite(v)).any():
            numeric_params.append(c)

    if not numeric_params:
        # fallback common names
        for cand in ["WQI", "pH", "DO_mg_L", "BOD_mg_L", "COD_mg_L", "TSS_mg_L", "Total_Coliform"]:
            if cand in df.columns:
                numeric_params.append(cand)

    return numeric_params


def check_coordinates_availability(df: pd.DataFrame):
    """Check if lat/long coordinates are available and return location coordinate info"""
    if "Lat" not in df.columns or "Long" not in df.columns:
        return False, {}

    # Get locations with valid coordinates
    location_coords = {}
    for _, row in df.iterrows():
        location = row.get("Location")
        lat = row.get("Lat")
        lng = row.get("Long")

        if location and pd.notna(lat) and pd.notna(lng):
            if location not in location_coords:
                location_coords[location] = {"lat": float(lat), "lng": float(lng)}

    has_coords = len(location_coords) > 0
    return has_coords, location_coords


# ----------------------- HTML builder -----------------------
def build_html(data_rows, months, params, locations, years, location_coords, out_path: Path):
    # helper to safely dump JSON and avoid closing script tag issues
    def dump_safe(obj):
        js = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        return js.replace("</script>", "<\\/script>")

    data_json = dump_safe(data_rows)
    months_json = dump_safe(months)
    params_json = dump_safe(params)
    locs_json = dump_safe(locations)
    years_json = dump_safe(years)
    coords_json = dump_safe(location_coords)

    # Full HTML template with FIXED JavaScript for map functionality
    html_template = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Yamuna Water Quality - Enhanced Dashboard</title>

<link href="https://cdn.jsdelivr.net/npm/tom-select/dist/css/tom-select.default.min.css" rel="stylesheet" />
<link href="https://cdnjs.cloudflare.com/ajax/libs/noUiSlider/14.6.4/nouislider.min.css" rel="stylesheet" />
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />

<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/tom-select/dist/js/tom-select.complete.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/noUiSlider/14.6.4/nouislider.min.js"></script>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

<style>
:root{ --accent1:#0ea5e9; --accent2:#2563eb; --card-bg:#fff; --muted:#6b7280; --ui-width:360px; }
*{box-sizing:border-box}
body{font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial; background:#f3f6fb; margin:0; color:#0f172a;}
.header{background:linear-gradient(90deg,var(--accent2),var(--accent1)); color:#fff; padding:12px 18px; position:relative; z-index:2100;}
.header h1{margin:0; font-size:18px;}
.layout{ display:block; padding:14px 14px 80px 14px; }
.sidebar{background:var(--card-bg); padding:12px; border-radius:12px; box-shadow:0 20px 40px rgba(2,6,23,0.12); width:var(--ui-width); position:fixed; left:16px; top:72px; height:calc(100vh - 88px); z-index:2000; overflow:auto; transition: transform .28s cubic-bezier(.2,.9,.2,1), opacity .25s;}
.sidebar.hidden{ transform: translateX(calc(-1 * (var(--ui-width) + 40px))); opacity:0; pointer-events:none; }
.top-actions{display:flex; gap:8px; align-items:center; margin-bottom:8px;}
.toggle-btn{background:#fff; border:1px solid #e6eefb; padding:6px 8px; border-radius:8px; cursor:pointer; color:var(--accent2);}
.select-label{font-size:13px; color:var(--muted); margin:6px 0; display:flex; justify-content:space-between; align-items:center;}
.slider-wrap{padding:6px 0 24px 0;}
.btn{background:var(--accent2); color:#fff; border:none; padding:10px 12px; border-radius:8px; cursor:pointer;}
.small-btn{background:#fff;color:var(--accent2);border:1px solid #e6eefb;padding:6px 8px;border-radius:8px;cursor:pointer;font-size:12px;}
.footer-note{color:var(--muted); font-size:13px; margin-top:12px;}
.main{ padding-left: calc(var(--ui-width) + 28px); transition: padding-left .28s; padding-right: 28px; }
.main.fullwidth{ padding-left: 20px; }
.card{background:var(--card-bg); padding:12px; border-radius:12px; box-shadow:0 6px 18px rgba(45,55,72,0.04); margin-bottom:12px;}
.kpis{display:flex; gap:10px; flex-wrap:wrap;}
.kpi{background:linear-gradient(180deg,#fff,#fbfdff); padding:8px 10px; border-radius:10px; min-width:100px; text-align:center; box-shadow:0 3px 10px rgba(16,24,40,0.04);}
.insight-box{background:linear-gradient(135deg,#f0f9ff,#e0f2fe); padding:12px; border-radius:8px; border-left:4px solid var(--accent1); font-size:13px; color:#0c4a6e; margin-bottom:8px;}
.insight-box strong{color:var(--accent2); font-weight:600;}
.charts-grid{display:flex; flex-direction:column; gap:12px;}
.param-title{font-weight:700; margin-bottom:8px;}
.quality-criteria{background:#f1f5f9; padding:8px 12px; margin-bottom:12px; border-radius:6px; font-size:12px; color:#475569; border-left:4px solid var(--accent2);}
.param-insights{background:#fefce8; padding:8px 12px; margin-bottom:12px; border-radius:6px; font-size:12px; color:#a16207; border-left:4px solid #eab308;}
.param-insights strong{color:#92400e;}
.form-row{display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:10px; margin-bottom:10px;}
.form-field{display:flex; flex-direction:column;}
.form-field label{font-size:12px; color:#666; margin-bottom:2px;}
.form-field input, .form-field select{padding:6px; border:1px solid #e2e8f0; border-radius:4px; font-size:13px;}
.table-wrap{max-height:420px; overflow:auto; margin-top:8px; font-size:14px;}
.table-wrap table{width:100%; border-collapse:collapse;}
.table-wrap th, .table-wrap td{padding:8px 10px; border-bottom:1px solid #f1f5f9; text-align:left; word-break:break-word;}
.table-wrap th{background:#fbfdff; position:sticky; top:0; z-index:1;}
.debugbox{display:none;}
html,body,#chartsContainer{width:100%; height:100%; overflow-x:hidden;}
.card .plotly-graph-div{width:100% !important; max-width:100% !important;}
.plotly-graph-div .main-svg { overflow: visible!important; }
.compact .table-wrap{font-size:12px;}
.compact .kpi{min-width:90px; padding:6px 8px; font-size:13px;}
.floating-toggle { position: fixed; left: 12px; top: 16px; z-index: 2200; border-radius: 10px; padding: 8px 10px; background: var(--card-bg); box-shadow: 0 6px 18px rgba(45,55,72,0.10); cursor: pointer; display: inline-flex; align-items: center; gap: 8px; font-weight: 600; color: var(--accent2); border: 1px solid #e6eefb; }
.floating-toggle.hidden { display: none; }
.warning-insight { background: linear-gradient(135deg,#fef3c7,#fde68a); border-left-color: #f59e0b; color: #92400e; }
.critical-insight { background: linear-gradient(135deg,#fee2e2,#fecaca); border-left-color: #ef4444; color: #991b1b; }
.positive-insight { background: linear-gradient(135deg,#ecfdf5,#d1fae5); border-left-color: #10b981; color: #065f46; }

.view-toggle {
  display: flex;
  gap: 4px;
  background: #f1f5f9;
  padding: 4px;
  border-radius: 8px;
  margin-bottom: 12px;
}
.view-toggle button {
  flex: 1;
  padding: 8px 12px;
  border: none;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: #64748b;
  transition: all 0.2s;
}
.view-toggle button.active {
  background: white;
  color: var(--accent2);
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

#mapContainer {
  height: 500px;
  border-radius: 8px;
  overflow: hidden;
}
.leaflet-popup-content {
  max-width: 300px;
}
.popup-content {
  font-size: 12px;
}
.popup-content h4 {
  margin: 0 0 8px 0;
  color: var(--accent2);
}
.popup-content table {
  width: 100%;
  border-collapse: collapse;
}
.popup-content td {
  padding: 2px 4px;
  border-bottom: 1px solid #f1f5f9;
}
.popup-content .param-name {
  font-weight: 600;
  color: #475569;
}

.no-coords-message {
  background: linear-gradient(135deg, #fef3c7, #fde68a);
  border-left: 4px solid #f59e0b;
  padding: 12px;
  border-radius: 8px;
  color: #92400e;
  text-align: center;
  margin: 20px;
}

@media (max-width: 900px){ :root{ --ui-width: 300px; } .sidebar{ left: 8px; width: calc(var(--ui-width) - 40px); } .main{ padding-left: calc(var(--ui-width) + 28px); } }
</style>
</head>
<body>
<div class="header"><h1>🌊 Yamuna Water Quality - Enhanced Dashboard</h1></div>

<button id="sidebarToggle" class="floating-toggle hidden" title="Show / hide controls">☰ Controls</button>

<div class="layout">
  <aside id="sidebar" class="sidebar">
    <div class="top-actions">
      <button id="hideBtn" class="toggle-btn" title="Hide controls">Hide</button>
      <div style="flex:1"></div>
      <button id="resetBtn" class="toggle-btn" title="Reset filters">Reset</button>
    </div>

    <div class="card" style="margin-bottom:10px;">
      <div class="select-label">
        <div>Locations</div>
        <div style="display:flex; gap:6px;">
          <button id="selectAllLocations" class="small-btn" title="Select all locations">All</button>
          <button id="clearLocations" class="small-btn" title="Clear locations">Clear</button>
        </div>
      </div>
      <select id="selLocation" multiple placeholder="Choose locations..."></select>

      <div class="select-label" style="margin-top:12px;">
        <div>Year range</div>
      </div>
      <div id="yearSlider" class="slider-wrap"></div>
      <div style="display:flex; gap:8px; justify-content:space-between; margin-bottom:8px;">
        <div><small style="color:var(--muted)">From</small><div id="yearMin" style="font-weight:700"></div></div>
        <div><small style="color:var(--muted)">To</small><div id="yearMax" style="font-weight:700"></div></div>
      </div>

      <div class="select-label">
        <div>Months</div>
        <div style="display:flex; gap:6px;">
          <button id="selectAllMonths" class="small-btn" title="Select all months">All</button>
          <button id="clearMonths" class="small-btn" title="Clear months">Clear</button>
        </div>
      </div>
      <select id="selMonth" multiple placeholder="Choose months..."></select>

      <div class="select-label" style="margin-top:12px;">
        <div>Parameters</div>
        <div style="display:flex; gap:6px;">
          <button id="selectAllParams" class="small-btn" title="Select all parameters">All</button>
          <button id="clearParams" class="small-btn" title="Clear parameters">Clear</button>
        </div>
      </div>
      <select id="selParam" multiple placeholder="Choose parameters..."></select>

      <div style="display:flex; gap:8px; margin-top:12px;">
        <button id="applyReset" class="btn" style="flex:1">Clear</button>
        <button id="downloadCsv" class="btn" style="flex:1">Download CSV</button>
      </div>

      <div style="margin-top:8px;">
        <label><input type="checkbox" id="monthlyAvgToggle" /> Use monthly averages (when plotting)</label>
      </div>

      <div class="footer-note">Tips: search in dropdowns, click × to remove selections. Use "Hide" for full-screen charts.</div>

      <div class="debugbox" id="debugInfo" style="margin-top:12px;"></div>
    </div>
  </aside>

  <main class="main">
    <div class="card kpis" id="kpisArea"></div>

    <div class="card">
      <div class="param-title">Key Insights & Analysis</div>
      <div id="insightsArea" style="display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:12px;">
        <div class="insight-box">Select parameters to view insights</div>
      </div>
    </div>

    <div class="card">
      <div class="param-title">Add New Data Entry</div>
      <div class="form-row">
        <div class="form-field">
          <label>Date</label>
          <input type="date" id="inputDate">
        </div>
        <div class="form-field">
          <label>Location</label>
          <select id="inputLocation">
            <option value="">Select location...</option>
          </select>
        </div>
        <div class="form-field">
          <label>Parameter</label>
          <select id="inputParameter">
            <option value="">Select parameter...</option>
          </select>
        </div>
        <div class="form-field">
          <label>Value</label>
          <input type="number" id="inputValue" step="0.01" placeholder="Enter value">
        </div>
      </div>
      <button id="addDataBtn" class="btn" style="margin-right:8px;">Add Data Point</button>
      <button id="clearFormBtn" class="small-btn">Clear Form</button>
    </div>

    <div class="card">
      <div class="view-toggle">
        <button id="chartsViewBtn" class="active">📊 Charts View</button>
        <button id="mapViewBtn">🗺️ Map View</button>
      </div>

      <div id="chartsContainer" class="charts-grid"></div>
      <div id="mapContainer" style="display:none;"></div>
      <div id="noMapMessage" style="display:none;" class="no-coords-message">
        <strong>No Location Coordinates Available</strong><br>
        The Excel file does not contain latitude and longitude data for the selected locations. 
        Map view requires coordinate data to display monitoring stations.
      </div>
    </div>

    <div class="card">
      <div class="param-title">Data / Selection</div>
      <div>Filtered rows: <strong id="recCount"></strong></div>
      <div id="tableContainer" style="display:none; margin-top:10px;">
        <div class="table-wrap" id="tableWrap"></div>
      </div>
    </div>
  </main>
</div>

<script>
document.addEventListener('DOMContentLoaded', function() {
  const DATA = __DATA_JSON__;
  const MONTHS = __MONTHS_JSON__;
  const PARAMS = __PARAMS_JSON__;
  const LOCS = __LOCS_JSON__;
  const YEARS = __YEARS_JSON__;
  const LOCATION_COORDS = __COORDS_JSON__;

  const HAS_COORDINATES = Object.keys(LOCATION_COORDS).length > 0;

  let userAddedData = [];
  let map = null;
  let currentView = 'charts';

  // CRITICAL: Helper function to get valid numeric value for analysis (excludes 0 for WQI)
  function getAnalysisValue(val, param) {
    const num = Number(val);
    if (!Number.isFinite(num)) return null;

    // Exclude 0 values from WQI analysis (they represent missing data)
    if (param === 'WQI' && num === 0) {
      return null;
    }

    return num;
  }

  // Helper function for display values (includes 0s)
  function getDisplayValue(val) {
    const num = Number(val);
    return Number.isFinite(num) ? num : null;
  }

  const STANDARDS = {
    "WQI":[
      { range: "Below 50",   label: "Excellent (A)", grade: "A", min: -999, max: 50, color: '#059669' },
      { range: "50-100",     label: "Good Water (B)", grade: "B", min: 50, max: 100, color: '#0891b2' },
      { range: "100-200",    label: "Poor Water (C)", grade: "C", min: 100, max: 200, color: '#f59e0b' },
      { range: "200-300",    label: "Very Poor/Bad (D)", grade: "D", min: 200, max: 300, color: '#ef4444' },
      { range: "Above 300",  label: "Unsuitable/Unfit (E)", grade: "E", min: 300, max: 999999, color: '#7c2d12' }
    ],
    "pH":[
      {min:6.5,max:8.5,color:'#059669',label:'Good'},
      {min:6.0,max:9.0,color:'#f59e0b',label:'Acceptable'},
      {min:-999,max:5.99,color:'#ef4444',label:'Out of range'},
      {min:9.01,max:999,color:'#ef4444',label:'Out of range'}
    ],
    "DO_mg_L":[
      {min:5,max:999,color:'#059669',label:'Good (>=5)'},
      {min:3,max:4.9,color:'#f59e0b',label:'Fair (3-4.9)'},
      {min:-999,max:2.9,color:'#ef4444',label:'Poor (<3)'}
    ],
    "BOD_mg_L":[
      {min:-999,max:3,color:'#059669',label:'Good (<=3)'},
      {min:3.01,max:6,color:'#f59e0b',label:'Caution'},
      {min:6.01,max:9999,color:'#ef4444',label:'Poor'}
    ],
    "COD_mg_L":[
      {min:-999,max:3,color:'#059669',label:'Good (<=3)'},
      {min:3.01,max:999,color:'#f59e0b',label:'Acceptable'},
      {min:999.01,max:9999,color:'#ef4444',label:'Poor'}
    ],
    "Total_Coliform":[
      {min:-999,max:500,color:'#059669',label:'Desirable'},
      {min:501,max:2500,color:'#f59e0b',label:'Permissible'},
      {min:2501,max:9999999999,color:'#ef4444',label:'Unsafe'}
    ],
    "Faecal_Coliform":[
      {min:-999,max:500,color:'#059669',label:'Desirable'},
      {min:501,max:2500,color:'#f59e0b',label:'Permissible'},
      {min:2501,max:9999999999,color:'#ef4444',label:'Unsafe'}
    ]
  };

  const QUALITY_RANGES = {
    "pH": "6.5-8.5 (acceptable range)",
    "COD_mg_L": "≤3 mg/l (desirable)",
    "BOD_mg_L": "≤3 mg/l (desirable)",
    "DO_mg_L": "≥5 mg/l (good quality)",
    "Total_Coliform": "≤500 MPN/100ml (desirable), ≤2500 (max permissible)",
    "Faecal_Coliform": "≤500 MPN/100ml (desirable), ≤2500 (max permissible)",
    "WQI": "Below 50 (Excellent-A), 50-100 (Good-B), 100-200 (Poor-C), 200-300 (Very Poor-D), Above 300 (Unsuitable-E)"
  };

  function safeAddOptions(selectEl, arr) { 
    selectEl.innerHTML=''; 
    for(const v of arr){ 
      const opt=document.createElement('option'); 
      opt.value=v; 
      opt.text=v; 
      selectEl.appendChild(opt);
    } 
  }
  function getTomValues(ts) { try{ const v = ts.getValue(); return Array.isArray(v)? v : (v? [v] : []); } catch(e){ return []; } }
  function sanitizeId(s) { return String(s).replace(/[^a-z0-9]/gi,'_'); }

  safeAddOptions(document.getElementById('selLocation'), LOCS);
  safeAddOptions(document.getElementById('selMonth'), MONTHS);
  safeAddOptions(document.getElementById('selParam'), PARAMS);
  safeAddOptions(document.getElementById('inputLocation'), LOCS);
  safeAddOptions(document.getElementById('inputParameter'), PARAMS);

  const tomLoc = new TomSelect('#selLocation', { plugins:['remove_button'], create:false, placeholder:'Choose locations...', hideSelected:true });
  const tomMonth = new TomSelect('#selMonth', { plugins:['remove_button'], create:false, placeholder:'Choose months...', hideSelected:true });
  const tomParam = new TomSelect('#selParam', { plugins:['remove_button'], create:false, placeholder:'Choose parameters...', hideSelected:true });

  const yearMinEl = document.getElementById('yearMin'), yearMaxEl = document.getElementById('yearMax');
  const yearsSorted = (YEARS||[]).slice().sort((a,b)=>a-b);
  const yMin = yearsSorted.length? yearsSorted[0] : new Date().getFullYear();
  const yMax = yearsSorted.length? yearsSorted[yearsSorted.length-1] : new Date().getFullYear();
  const sliderDiv = document.createElement('div'); document.getElementById('yearSlider').appendChild(sliderDiv);
  noUiSlider.create(sliderDiv, { start:[yMin,yMax], connect:true, step:1, range:{min:yMin,max:yMax}, tooltips:[true,true], format:{ to: v => Math.round(v), from: v => Number(v) } });
  sliderDiv.noUiSlider.on('update', function(vals){ yearMinEl.textContent=Math.round(vals[0]); yearMaxEl.textContent=Math.round(vals[1]); });

  function preferDefaultParam(){
    if(PARAMS && PARAMS.length){
      const p = PARAMS.indexOf('WQI') !== -1 ? 'WQI' : PARAMS[0];
      tomParam.setValue([p]);
    }
  }
  preferDefaultParam();

  // Initialize map
  function initializeMap() {
    if (map) {
      map.remove();
    }

    map = L.map('mapContainer').setView([28.6139, 77.2090], 10);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors'
    }).addTo(map);

    return map;
  }

  // Render map with data
  function renderMap(rows, selectedParams) {
    if (!HAS_COORDINATES) {
      document.getElementById('noMapMessage').style.display = 'block';
      document.getElementById('mapContainer').style.display = 'none';
      return;
    }

    document.getElementById('noMapMessage').style.display = 'none';
    document.getElementById('mapContainer').style.display = 'block';

    if (!map) {
      initializeMap();
    }

    // Clear existing markers
    map.eachLayer(function(layer) {
      if (layer instanceof L.Marker) {
        map.removeLayer(layer);
      }
    });

    // Group data by location
    const locationData = {};
    rows.forEach(row => {
      const loc = row.Location;
      if (!loc || !LOCATION_COORDS[loc]) return;

      if (!locationData[loc]) {
        locationData[loc] = {
          coords: LOCATION_COORDS[loc],
          measurements: []
        };
      }

      const measurement = {
        date: row.Date,
        year: row.Year,
        month: row.Month
      };

      selectedParams.forEach(param => {
        const val = getDisplayValue(row[param]);
        if (val !== null) {
          measurement[param] = val;
        }
      });

      locationData[loc].measurements.push(measurement);
    });

    // Add markers for each location
    Object.keys(locationData).forEach(locationName => {
      const locData = locationData[locationName];
      const coords = locData.coords;

      // Calculate averages for selected parameters
      const paramAverages = {};
      selectedParams.forEach(param => {
        const values = locData.measurements
          .map(m => getAnalysisValue(m[param], param))
          .filter(v => v !== null);

        if (values.length > 0) {
          paramAverages[param] = {
            avg: values.reduce((a, b) => a + b, 0) / values.length,
            count: values.length,
            min: Math.min(...values),
            max: Math.max(...values)
          };
        }
      });

      // Determine marker color based on WQI if available
      let markerColor = '#3388ff'; // default blue
      if (paramAverages.WQI) {
        const wqi = paramAverages.WQI.avg;
        if (wqi < 50) markerColor = '#059669';
        else if (wqi < 100) markerColor = '#0891b2';
        else if (wqi < 200) markerColor = '#f59e0b';
        else if (wqi < 300) markerColor = '#ef4444';
        else markerColor = '#7c2d12';
      }

      // Create custom icon
      const icon = L.divIcon({
        className: 'custom-marker',
        html: `<div style="background-color: ${markerColor}; width: 20px; height: 20px; border-radius: 50%; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3);"></div>`,
        iconSize: [20, 20],
        iconAnchor: [10, 10]
      });

      // Create popup content
      let popupContent = `<div class="popup-content">
      <h4>${locationName}</h4>
      <div style="font-size: 11px; color: #666; margin-bottom: 8px;">
    📍 Lat: ${coords.lat.toFixed(6)}, Long: ${coords.lng.toFixed(6)}
     </div>
        <table>`;

      if (Object.keys(paramAverages).length > 0) {
        Object.keys(paramAverages).forEach(param => {
          const data = paramAverages[param];
          popupContent += `
            <tr>
              <td class="param-name">${param}:</td>
              <td>${data.avg.toFixed(2)} (avg)</td>
            </tr>
            <tr>
              <td></td>
              <td style="font-size: 11px; color: #666;">
                Min: ${data.min.toFixed(2)}, Max: ${data.max.toFixed(2)}<br>
                ${data.count} measurements
              </td>
            </tr>`;
        });
      } else {
        popupContent += `<tr><td colspan="2">No data for selected parameters</td></tr>`;
      }

      popupContent += `</table>
        <div style="margin-top: 8px; font-size: 11px; color: #666;">
          Total measurements: ${locData.measurements.length}
        </div>
      </div>`;

      // Add marker to map
      const marker = L.marker([coords.lat, coords.lng], { icon: icon })
        .bindPopup(popupContent)
        .addTo(map);
    });

    // Fit map bounds to show all markers
    const allCoords = Object.values(locationData).map(d => d.coords);
    if (allCoords.length > 0) {
      const latLngs = allCoords.map(c => [c.lat, c.lng]);
      const bounds = L.latLngBounds(latLngs);
      map.fitBounds(bounds, { padding: [20, 20] });
    }

    // Refresh map size
    setTimeout(() => {
      map.invalidateSize();
    }, 100);
  }

  // Add WQI Yearly Chart Function
  function renderWQIYearlyAvg(containerId, rows) {
    const wqiData = {};
    const zeroData = {};

    for(const r of rows){
        const year = r.Year;
        const wqi = r["WQI"];

        if(!year || wqi === null || wqi === undefined) continue;

        const wqiNum = Number(wqi);
        if(!Number.isFinite(wqiNum)) continue;

        if (wqiNum === 0) {
            zeroData[year] = (zeroData[year] || 0) + 1;
            continue;
        }

        wqiData[year] = wqiData[year] || [];
        wqiData[year].push(wqiNum);
    }

    const years = Object.keys(wqiData).map(y => parseInt(y)).sort();
    const avgWQI = years.map(year => {
        const values = wqiData[year];
        return values.reduce((a,b) => a+b, 0) / values.length;
    });

    const colors = avgWQI.map(wqi => {
        if (wqi < 50) return '#059669';
        else if (wqi < 100) return '#0891b2';
        else if (wqi < 200) return '#f59e0b';
        else if (wqi < 300) return '#ef4444';
        else return '#7c2d12';
    });

    const shapes = [
        { type: 'rect', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: 0, y1: 50, 
          fillcolor: '#059669' + '22', line: {width: 0}, layer: 'below' },
        { type: 'rect', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: 50, y1: 100, 
          fillcolor: '#0891b2' + '22', line: {width: 0}, layer: 'below' },
        { type: 'rect', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: 100, y1: 200, 
          fillcolor: '#f59e0b' + '22', line: {width: 0}, layer: 'below' },
        { type: 'rect', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: 200, y1: 300, 
          fillcolor: '#ef4444' + '22', line: {width: 0}, layer: 'below' }
    ];

    const annotations = [];
    Object.keys(zeroData).forEach(year => {
        const count = zeroData[year];
        annotations.push({
            x: parseInt(year),
            y: 0,
            text: `0 (${count})`,
            showarrow: true,
            arrowhead: 2,
            arrowcolor: '#9ca3af',
            font: { color: '#9ca3af', size: 11 },
            bgcolor: 'rgba(255,255,255,0.8)',
            bordercolor: '#9ca3af'
        });
    });

    const layout = {
        title: 'Average WQI by Year (excluding 0 values)',
        margin: { t:50, l:60, r:40, b:80 },
        xaxis: { title: 'Year', tickmode: 'array', tickvals: years },
        yaxis: { title: 'Average WQI', range: [0, Math.max(...avgWQI) * 1.1] },
        autosize: true,
        shapes: shapes,
        annotations: annotations
    };

    const trace = {
        x: years,
        y: avgWQI,
        type: 'scatter',
        mode: 'lines+markers',
        marker: { color: colors, size: 8, line: { color: 'white', width: 2 } },
        line: { color: '#1f2937', width: 3 },
        name: 'Average WQI'
    };

    Plotly.react(containerId, [trace], layout, {responsive: true});
  }

  // Updated yearly performance analysis - excludes 0 from WQI
  function generateYearlyPerformanceAnalysis(rows, param) {
    const yearlyData = {};

    rows.forEach(r => {
      const year = r.Year;
      const val = getAnalysisValue(r[param], param);

      if (val !== null && year) {
        if (!yearlyData[year]) yearlyData[year] = [];
        yearlyData[year].push(val);
      }
    });

    const years = Object.keys(yearlyData).map(y => parseInt(y)).sort();
    if (years.length < 2) return null;

    const yearlyAverages = {};
    years.forEach(year => {
      const values = yearlyData[year];
      yearlyAverages[year] = values.reduce((sum, val) => sum + val, 0) / values.length;
    });

    const firstYear = years[0];
    const lastYear = years[years.length - 1];
    const firstAvg = yearlyAverages[firstYear];
    const lastAvg = yearlyAverages[lastYear];
    const overallChange = ((lastAvg - firstAvg) / firstAvg) * 100;

    let bestYear = firstYear, worstYear = firstYear;
    let bestAvg = firstAvg, worstAvg = firstAvg;

    years.forEach(year => {
      const avg = yearlyAverages[year];
      if (param === 'WQI') {
        if (avg < bestAvg) { bestAvg = avg; bestYear = year; }
        if (avg > worstAvg) { worstAvg = avg; worstYear = year; }
      } else if (param.includes('DO_mg_L')) {
        if (avg > bestAvg) { bestAvg = avg; bestYear = year; }
        if (avg < worstAvg) { worstAvg = avg; worstYear = year; }
      } else {
        if (avg < bestAvg) { bestAvg = avg; bestYear = year; }
        if (avg > worstAvg) { worstAvg = avg; worstYear = year; }
      }
    });

    let trendText = '';
    let trendClass = '';

    if (Math.abs(overallChange) < 5) {
      trendText = `${param} levels remained relatively stable from ${firstYear} to ${lastYear} (${overallChange.toFixed(1)}% change)`;
      trendClass = '';
    } else {
      let isImproving = false;
      if (param === 'WQI') {
        isImproving = overallChange < 0;
      } else if (param.includes('DO_mg_L')) {
        isImproving = overallChange > 0;
      } else {
        isImproving = overallChange < 0;
      }

      if (isImproving) {
        if (Math.abs(overallChange) > 20) {
          trendText = `Significant improvement in ${param} from ${firstYear} to ${lastYear} (${Math.abs(overallChange).toFixed(1)}% ${overallChange > 0 ? 'increase' : 'decrease'})`;
          trendClass = 'positive-insight';
        } else {
          trendText = `Moderate improvement in ${param} from ${firstYear} to ${lastYear} (${Math.abs(overallChange).toFixed(1)}% ${overallChange > 0 ? 'increase' : 'decrease'})`;
          trendClass = 'positive-insight';
        }
      } else {
        if (Math.abs(overallChange) > 20) {
          trendText = `Significant deterioration in ${param} from ${firstYear} to ${lastYear} (${Math.abs(overallChange).toFixed(1)}% ${overallChange > 0 ? 'increase' : 'decrease'})`;
          trendClass = 'critical-insight';
        } else {
          trendText = `Moderate deterioration in ${param} from ${firstYear} to ${lastYear} (${Math.abs(overallChange).toFixed(1)}% ${overallChange > 0 ? 'increase' : 'decrease'})`;
          trendClass = 'warning-insight';
        }
      }
    }

    if (bestYear !== worstYear) {
      trendText += ` • Best: ${bestYear} (${bestAvg.toFixed(2)}), Worst: ${worstYear} (${worstAvg.toFixed(2)})`;
    }

    return { text: trendText, class: trendClass, years, yearlyAverages };
  }

  // Updated temporal trend analysis - excludes 0 from WQI
  function generateTemporalTrendAnalysis(rows, param) {
    const timeSeriesData = rows
      .filter(r => r.Date && getAnalysisValue(r[param], param) !== null)
      .map(r => ({ date: new Date(r.Date), value: getAnalysisValue(r[param], param) }))
      .sort((a, b) => a.date - b.date);

    if (timeSeriesData.length < 6) return null;

    const splitPoint = Math.floor(timeSeriesData.length * 0.6);
    const earlyPeriod = timeSeriesData.slice(0, splitPoint);
    const recentPeriod = timeSeriesData.slice(splitPoint);

    const earlyAvg = earlyPeriod.reduce((sum, d) => sum + d.value, 0) / earlyPeriod.length;
    const recentAvg = recentPeriod.reduce((sum, d) => sum + d.value, 0) / recentPeriod.length;

    const trendChange = ((recentAvg - earlyAvg) / earlyAvg) * 100;

    let trendText = '';
    let trendClass = '';

    if (Math.abs(trendChange) < 5) {
      trendText = `${param} levels remain stable over time (${trendChange.toFixed(1)}% change)`;
      trendClass = '';
    } else {
      let isImproving = false;
      if (param === 'WQI') {
        isImproving = trendChange < 0;
      } else if (param.includes('DO_mg_L')) {
        isImproving = trendChange > 0;
      } else {
        isImproving = trendChange < 0;
      }

      const earlyStart = earlyPeriod[0].date;
      const earlyEnd = earlyPeriod[earlyPeriod.length - 1].date;
      const recentStart = recentPeriod[0].date;
      const recentEnd = recentPeriod[recentPeriod.length - 1].date;

      const formatDate = (date) => date.toLocaleDateString('en-US', { year: 'numeric', month: 'short' });

      if (isImproving) {
        trendText = `${param} shows improving trend - ${Math.abs(trendChange).toFixed(1)}% ${trendChange > 0 ? 'increase' : 'decrease'} from early period (${formatDate(earlyStart)} - ${formatDate(earlyEnd)}) to recent period (${formatDate(recentStart)} - ${formatDate(recentEnd)})`;
        trendClass = 'positive-insight';
      } else {
        trendText = `${param} shows concerning trend - ${Math.abs(trendChange).toFixed(1)}% ${trendChange > 0 ? 'increase' : 'decrease'} from early period (${formatDate(earlyStart)} - ${formatDate(earlyEnd)}) to recent period (${formatDate(recentStart)} - ${formatDate(recentEnd)})`;
        trendClass = 'warning-insight';
      }
    }

    return { text: trendText, class: trendClass };
  }

  // Updated insights generation - excludes 0 from WQI
  function generateInsights(rows, params) {
    const insights = [];

    if (!rows.length || !params.length) {
      return ['<div class="insight-box">Select data to view insights</div>'];
    }

    const uniqueLocations = [...new Set(rows.map(r => r.Location))];
    const userAddedCount = rows.filter(r => r.UserAdded).length;
    const yearRange = [...new Set(rows.map(r => r.Year).filter(y => y))];
    const minYear = Math.min(...yearRange);
    const maxYear = Math.max(...yearRange);

    let coverageText = `Data spans <strong>${maxYear - minYear + 1} years</strong> (${minYear}-${maxYear}) across <strong>${uniqueLocations.length} locations</strong> with <strong>${rows.length} measurements</strong>`;
    if (userAddedCount > 0) {
      coverageText += ` (including ${userAddedCount} user-added points)`;
    }
    insights.push(`<div class="insight-box">${coverageText}</div>`);

    if (params.length === 1 && yearRange.length >= 2) {
      const param = params[0];
      const yearlyAnalysis = generateYearlyPerformanceAnalysis(rows, param);

      if (yearlyAnalysis) {
        insights.push(`<div class="insight-box ${yearlyAnalysis.class}"><strong>Yearly Performance:</strong> ${yearlyAnalysis.text}</div>`);
      }

      const temporalTrend = generateTemporalTrendAnalysis(rows, param);
      if (temporalTrend) {
        insights.push(`<div class="insight-box ${temporalTrend.class}">${temporalTrend.text}</div>`);
      }
    }

    // Compliance analysis - excludes 0 from WQI
    if (params.length === 1) {
      const param = params[0];
      const values = rows.map(r => getAnalysisValue(r[param], param)).filter(v => v !== null);

      if (values.length > 0) {
        let compliantCount = 0;

        values.forEach(val => {
          let isCompliant = true;

          if (param === 'pH') {
            isCompliant = val >= 6.5 && val <= 8.5;
          } else if (param.includes('DO_mg_L')) {
            isCompliant = val >= 5;
          } else if (param.includes('BOD_mg_L') || param.includes('COD_mg_L')) {
            isCompliant = val <= 3;
          } else if (param.includes('Coliform')) {
            isCompliant = val <= 500;
          } else if (param === 'WQI') {
            isCompliant = val < 100;
          }

          if (isCompliant) compliantCount++;
        });

        const complianceRate = (compliantCount / values.length) * 100;
        let complianceClass = '';

        if (complianceRate >= 80) {
          complianceClass = 'positive-insight';
        } else if (complianceRate >= 60) {
          complianceClass = 'warning-insight';
        } else {
          complianceClass = 'critical-insight';
        }

        insights.push(`<div class="insight-box ${complianceClass}"><strong>Compliance Rate:</strong> ${complianceRate.toFixed(1)}% of valid measurements meet quality standards for ${param}</div>`);
      }
    }

    return insights.slice(0, 7);
  }

  // Updated groupSeries function
  function groupSeries(rows, param, monthly=false){
    const byLoc = {};

    for(const r of rows){
      if(!r.Date) continue;
      const loc = r.Location || 'Unknown';
      const dt = new Date(r.Date);
      if(isNaN(dt)) continue;
      const val = getDisplayValue(r[param]);
      const rowObj = { date: dt, value: val, originalRow: r };

      if(!monthly) {
        byLoc[loc] = byLoc[loc] || []; 
        byLoc[loc].push(rowObj);
      } else {
        const key = dt.getFullYear() + '-' + String(dt.getMonth()+1).padStart(2,'0');
        byLoc[loc] = byLoc[loc] || {}; 
        byLoc[loc][key] = byLoc[loc][key] || []; 
        // For monthly averages, exclude 0 from WQI analysis
        const monthVal = getAnalysisValue(r[param], param);
        if (monthVal !== null) {
          byLoc[loc][key].push(monthVal);
        }
      }
    }

    if(monthly){
      const out = {};
      for(const loc of Object.keys(byLoc)){
        const monthMap = byLoc[loc];
        const points = [];
        const keys = Object.keys(monthMap).sort();
        for(const k of keys){
          const vals = monthMap[k].filter(v => Number.isFinite(v));
          if(!vals.length) continue;
          const avg = vals.reduce((a,b)=>a+b,0)/vals.length;
          const [y,m] = k.split('-').map(x=>parseInt(x,10));
          const d = new Date(y, m-1, 1);
          points.push({ date: d, value: avg });
        }
        points.sort((a,b)=>a.date - b.date);
        out[loc] = points;
      }
      return out;
    } else {
      for(const loc of Object.keys(byLoc)){
        byLoc[loc].sort((a,b)=>a.date - b.date);
      }
      return byLoc;
    }
  }

  function chooseScatterType(pointsCount){
    return pointsCount > 1200 ? 'scattergl' : 'scatter';
  }

  function renderTimeSeriesPerLocation(containerId, rows, param){
    const monthly = document.getElementById('monthlyAvgToggle').checked;
    const series = groupSeries(rows, param, monthly);
    const traces = [];
    let globalMin = Infinity, globalMax = -Infinity, pointsCount = 0;

    const isColiform = param.toLowerCase().includes('coliform');
    const scaleFactor = isColiform ? 10000 : 1;
    const scaleLabel = isColiform ? ' (x10,000)' : '';

    for(const [loc, arr] of Object.entries(series)){
      const x = arr.map(pt => pt.date.toISOString());
      const y = arr.map(pt => {
        if (pt.value === null || !Number.isFinite(pt.value)) return null;
        return isColiform ? pt.value / scaleFactor : pt.value;
      });
      if(x.length === 0) continue;
      for(const v of y) if(Number.isFinite(v)){ globalMin = Math.min(globalMin, v); globalMax = Math.max(globalMax, v); }
      pointsCount += x.length;
      const type = chooseScatterType(x.length);
      traces.push({ x, y, mode:'lines+markers', type: type, name: loc, connectgaps: false });
    }
    if(!isFinite(globalMin)) { globalMin = 0; globalMax = 1; }

    const stdKey = STANDARDS[param] ? param : null;
    const shapes = []; const annotations = [];
    if(stdKey && STANDARDS[stdKey]){
      const bands = STANDARDS[stdKey].slice().sort((a,b)=>a.min - b.min);
      const margin = Math.max((globalMax - globalMin) * 0.08, 1);
      for(const b of bands){
        if(!isFinite(b.min) || !isFinite(b.max)) continue;
        let bandMin = b.min, bandMax = b.max;

        if(isColiform) {
          bandMin = bandMin / scaleFactor;
          bandMax = bandMax / scaleFactor;
        }

        if(bandMax < (globalMin - margin) && bandMin < (globalMin - margin)) continue;
        if(bandMin > (globalMax + margin) && bandMax > (globalMax + margin)) continue;
        const visMin = Math.max(bandMin, globalMin - margin);
        const visMax = Math.min(bandMax, globalMax + margin);
        if(visMax <= visMin) continue;
        const alpha = '22';
        const fill = (b.color || '#cccccc') + alpha;
        shapes.push({ type:'rect', xref:'paper', x0:0, x1:1, yref:'y', y0:visMin, y1:visMax, fillcolor: fill, line:{width:0}, layer:'below' });
        shapes.push({ type:'line', xref:'paper', x0:0, x1:1, yref:'y', y0:Math.max(bandMin, globalMin - margin), y1:Math.max(bandMin, globalMin - margin), line:{dash:'dash', color:(b.color||'#666'), width:1}, layer:'below' });
        annotations.push({ xref:'paper', x:0.99, y: Math.min(visMax, Math.max(visMin, (bandMin + bandMax)/2)), xanchor:'right', text:b.label, showarrow:false, font:{size:11, color:(b.color||'#000')}, bgcolor:'rgba(255,255,255,0.6)', borderpad:4 });
      }
    }

    const layout = {
      title: param + scaleLabel + ' over time (lines = locations)',
      margin: { t:48, l:60, r:40, b:200 },
      legend: { orientation:'h', y:-0.45, x: 0.5, xanchor: 'center', font: { size: 10 } },
      autosize: true,
      xaxis: { automargin:true, tickangle:-45, tickformat: monthly ? '%b %Y' : '%b %Y', showgrid: false },
      yaxis: { automargin:true, title: param + scaleLabel },
      shapes: shapes,
      annotations: annotations
    };

    Plotly.react(containerId, traces, layout, {responsive:true});
  }

  function renderBarAvg(containerId, rows, param){
    const isColiform = param.toLowerCase().includes('coliform');
    const scaleFactor = isColiform ? 10000 : 1;
    const scaleLabel = isColiform ? ' (x10,000)' : '';

    const map = {};
    for(const r of rows){
      const loc = r.Location || 'Unknown';
      const v = getAnalysisValue(r[param], param);
      if(v === null) continue;
      map[loc] = map[loc] || []; 
      map[loc].push(isColiform ? v / scaleFactor : v);
    }
    const locs = Object.keys(map);
    const vals = locs.map(l => map[l].reduce((a,b)=>a+b,0)/map[l].length);
    const layout = { 
      margin:{t:36, l:48, r:12, b:140}, 
      xaxis:{tickangle:-45}, 
      yaxis:{title: param + scaleLabel},
      autosize:true, 
      title:'Average ' + param + scaleLabel + ' by Location (excluding invalid data)' 
    };
    Plotly.react(containerId, [{ x: locs, y: vals, type:'bar' }], layout, {responsive:true});
  }

  function renderChartsForParams(rows, params){
    const container = document.getElementById('chartsContainer'); 
    container.innerHTML = '';
    const fragment = document.createDocumentFragment();
    const blocks = [];

    const hasWQI = params.includes('WQI');

    if (hasWQI) {
        const wqiYearlyBlock = document.createElement('div');
        wqiYearlyBlock.className = 'card param-block';
        wqiYearlyBlock.innerHTML = `
            <div class="param-title">WQI Yearly Trends</div>
            <div class="quality-criteria"><strong>Quality Assessment:</strong> Excellent (<50), Good (50-100), Poor (100-200), Very Poor (200-300), Unsuitable (>300)</div>
            <div id="wqi_yearly" style="height:400px; margin-bottom:18px;"></div>
        `;
        fragment.appendChild(wqiYearlyBlock);
    }

    for(const p of params){
        const pid = sanitizeId(p);
        const block = document.createElement('div'); 
        block.className = 'card param-block';

        const qualityRange = QUALITY_RANGES[p] || `${p} `;

        block.innerHTML = '<div class="param-title">' + p + '</div>' +
                          '<div class="quality-criteria"><strong>Quality Criteria (C Class):</strong> ' + qualityRange + '</div>' +
                          '<div id="time_' + pid + '" style="height:440px; margin-bottom:18px;"></div>' +
                          '<div id="bar_' + pid + '" style="height:320px; margin-top:10px;"></div>';
        fragment.appendChild(block);
        blocks.push({ p, pid });
    }

    container.appendChild(fragment);

    requestAnimationFrame(()=>{
        if (hasWQI) {
            try {
                renderWQIYearlyAvg('wqi_yearly', rows);
            } catch(err) {
                console.error('Error rendering WQI yearly chart', err);
            }
        }

        for(const pb of blocks){
            try{
                renderTimeSeriesPerLocation('time_' + pb.pid, rows, pb.p);
                renderBarAvg('bar_' + pb.pid, rows, pb.p);
            }catch(err){
                console.error('Error rendering param', pb.p, err);
            }
        }
    });
  }

  function filterData(){
    const selectedLocs = getTomValues(tomLoc);
    const selectedMonths = getTomValues(tomMonth);
    const selectedParams = getTomValues(tomParam);
    const yrs = sliderDiv.noUiSlider.get().map(v=> Math.round(Number(v))); 
    const [selYmin, selYmax] = yrs;

    let rows = (DATA||[]).slice();

    for (const userPoint of userAddedData) {
      const completeRow = {
        Date: userPoint.Date,
        Location: userPoint.Location,
        Year: userPoint.Year,
        Month: userPoint.Month,
        UserAdded: true
      };
      for (const param of PARAMS) {
        completeRow[param] = userPoint[param] || null;
      }
      rows.push(completeRow);
    }

    if(selectedLocs.length) rows = rows.filter(r => r.Location && selectedLocs.includes(String(r.Location)));
    if(selectedMonths.length) rows = rows.filter(r => r.Month && selectedMonths.includes(String(r.Month)));
    rows = rows.filter(r => { 
      if(r.Year===null||r.Year===undefined) return false; 
      const y=Number(r.Year); 
      if(isNaN(y)) return false; 
      return y>=selYmin && y<=selYmax; 
    });
    const chosenParams = selectedParams.length ? selectedParams : (PARAMS.length ? [PARAMS[0]] : []);
    return { rows, chosenParams };
  }

  // Updated KPI rendering to exclude 0 from WQI
  function renderKPIs(rows, params){
    const area = document.getElementById('kpisArea'); 
    area.innerHTML='';
    if(params.length >=6) document.body.classList.add('compact'); 
    else document.body.classList.remove('compact');
    if(!params || !params.length){ 
      area.innerHTML = '<div class="kpi">No parameter</div>'; 
      return; 
    }
    if(params.length === 1){
      const p = params[0];
      const vals = rows.map(r => getAnalysisValue(r[p], p)).filter(v => v !== null);
      if(!vals.length){ 
        area.innerHTML = '<div class="kpi">No valid values</div>'; 
        return; 
      }
      const avg = vals.reduce((a,b)=>a+b,0)/vals.length;
      area.innerHTML = '<div class="kpi"><div style="font-size:12px;color:#666">' + p + ' Avg</div><div style="font-weight:700">' + avg.toFixed(2) + '</div></div>' +
                       '<div class="kpi"><div style="font-size:12px;color:#666">Min</div><div style="font-weight:700">' + Math.min(...vals).toFixed(2) + '</div></div>' +
                       '<div class="kpi"><div style="font-size:12px;color:#666">Max</div><div style="font-weight:700">' + Math.max(...vals).toFixed(2) + '</div></div>' +
                       '<div class="kpi"><div style="font-size:12px;color:#666">Valid Count</div><div style="font-weight:700">' + vals.length + '</div></div>';
    } else {
      area.innerHTML = '<div class="kpi"><div style="font-size:12px;color:#666">Params</div><div style="font-weight:700">' + params.length + '</div></div>' +
                       '<div class="kpi"><div style="font-size:12px;color:#666">Rows</div><div style="font-weight:700">' + rows.length + '</div></div>';
    }
  }

  // Sidebar and UI controls
  const sidebar = document.getElementById('sidebar');
  const hideBtn = document.getElementById('hideBtn');
  const floatingToggle = document.getElementById('sidebarToggle');
  const mainEl = document.querySelector('.main');

  function setSidebarVisible(visible){
    if(visible){
      sidebar.classList.remove('hidden'); 
      floatingToggle.classList.add('hidden'); 
      mainEl.classList.remove('fullwidth');
    } else {
      sidebar.classList.add('hidden'); 
      floatingToggle.classList.remove('hidden'); 
      mainEl.classList.add('fullwidth');
    }
    setTimeout(()=>{ 
      document.querySelectorAll('.plotly-graph-div').forEach(g=>{ 
        try{ Plotly.Plots.resize(g);}catch(e){} 
      });
      if (map) map.invalidateSize();
    }, 150);
  }
  setSidebarVisible(true);
  hideBtn.addEventListener('click', ()=> setSidebarVisible(false));
  floatingToggle.addEventListener('click', ()=> setSidebarVisible(true));

  document.getElementById('resetBtn').addEventListener('click', function(){
    tomLoc.clear(); tomMonth.clear(); tomParam.clear(); preferDefaultParam(); sliderDiv.noUiSlider.set([yMin,yMax]); scheduleRender();
  });
  document.getElementById('applyReset').addEventListener('click', function(){
    tomLoc.clear(); tomMonth.clear(); tomParam.clear(); preferDefaultParam(); sliderDiv.noUiSlider.set([yMin,yMax]); scheduleRender();
  });

  function selectAllTomBulk(ts, arr){
    try{
      const vals = (arr||[]).map(v => String(v));
      if(typeof ts.setValue === 'function') ts.setValue(vals);
      else { ts.clear(); for(const v of vals) ts.addItem(v); }
    } catch(e){ console.warn('selectAllTomBulk error', e); }
  }
  function clearTomBulk(ts){ try{ if(typeof ts.clear === 'function') ts.clear(); else if(typeof ts.setValue === 'function') ts.setValue([]); }catch(e){} }

  document.getElementById('selectAllLocations').addEventListener('click', ()=>{ selectAllTomBulk(tomLoc, LOCS); scheduleRender(); });
  document.getElementById('clearLocations').addEventListener('click', ()=>{ clearTomBulk(tomLoc); scheduleRender(); });
  document.getElementById('selectAllMonths').addEventListener('click', ()=>{ selectAllTomBulk(tomMonth, MONTHS); scheduleRender(); });
  document.getElementById('clearMonths').addEventListener('click', ()=>{ clearTomBulk(tomMonth); scheduleRender(); });
  document.getElementById('selectAllParams').addEventListener('click', ()=>{ selectAllTomBulk(tomParam, PARAMS); scheduleRender(); });
  document.getElementById('clearParams').addEventListener('click', ()=>{ clearTomBulk(tomParam); preferDefaultParam(); scheduleRender(); });

  function downloadCSV(rows){
    if(!rows || !rows.length){ alert("No rows to download."); return; }
    const keys = Object.keys(rows[0]);
    const csvRows = [keys.join(",")];
    for(const r of rows){
      const line = keys.map(k=> { const v = r[k] === null || r[k] === undefined ? "" : String(r[k]).replace(/"/g,'""'); return `"${v}"`; }).join(",");
      csvRows.push(line);
    }
    const blob = new Blob([csvRows.join("\\n")], {type:'text/csv;charset=utf-8;'});
    const url = URL.createObjectURL(blob); 
    const a=document.createElement('a'); 
    a.href=url; 
    a.download='yamuna_filtered.csv'; 
    document.body.appendChild(a); 
    a.click(); 
    a.remove(); 
    URL.revokeObjectURL(url);
  }
  document.getElementById('downloadCsv').addEventListener('click', function(){ const {rows} = filterData(); downloadCSV(rows); });

  function addDataPoint() {
    const date = document.getElementById('inputDate').value;
    const location = document.getElementById('inputLocation').value;
    const parameter = document.getElementById('inputParameter').value;
    const value = parseFloat(document.getElementById('inputValue').value);

    if (!date || !location || !parameter || isNaN(value)) {
      alert('Please fill in all fields with valid data.');
      return;
    }

    const newPoint = {
      Date: date,
      Location: location,
      [parameter]: value,
      Year: new Date(date).getFullYear(),
      Month: new Date(date).toLocaleString('default', { month: 'long' }),
      UserAdded: true
    };

    userAddedData.push(newPoint);
    clearForm();
    scheduleRender();
    alert(`Data point added successfully: ${parameter} = ${value} at ${location} on ${date}`);
  }

  function clearForm() {
    document.getElementById('inputDate').value = '';
    document.getElementById('inputLocation').value = '';
    document.getElementById('inputParameter').value = '';
    document.getElementById('inputValue').value = '';
  }

  document.getElementById('addDataBtn').addEventListener('click', addDataPoint);
  document.getElementById('clearFormBtn').addEventListener('click', clearForm);

  // FIXED: View switching function
  function switchView(view) {
    currentView = view;
    const chartsBtn = document.getElementById('chartsViewBtn');
    const mapBtn = document.getElementById('mapViewBtn');
    const chartsContainer = document.getElementById('chartsContainer');
    const mapContainer = document.getElementById('mapContainer');
    const noMapMessage = document.getElementById('noMapMessage');

    if (view === 'charts') {
      chartsBtn.classList.add('active');
      mapBtn.classList.remove('active');
      chartsContainer.style.display = 'block';
      mapContainer.style.display = 'none';
      noMapMessage.style.display = 'none';

      setTimeout(() => {
        document.querySelectorAll('.plotly-graph-div').forEach(g => {
          try { Plotly.Plots.resize(g); } catch(e) {}
        });
      }, 100);
    } else if (view === 'map') {
      chartsBtn.classList.remove('active');
      mapBtn.classList.add('active');
      chartsContainer.style.display = 'none';

      if (!HAS_COORDINATES) {
        noMapMessage.style.display = 'block';
        mapContainer.style.display = 'none';
      } else {
        noMapMessage.style.display = 'none';
        mapContainer.style.display = 'block';

        // Render map with current data
        const { rows, chosenParams } = filterData();
        renderMap(rows, chosenParams);
      }
    }
  }

  document.getElementById('chartsViewBtn').addEventListener('click', () => switchView('charts'));
  document.getElementById('mapViewBtn').addEventListener('click', () => switchView('map'));

  let renderTimer_js = null;
  function scheduleRender(ms = 200){
    if(renderTimer_js) clearTimeout(renderTimer_js);
    renderTimer_js = setTimeout(()=>{ renderAll(); renderTimer_js = null; }, ms);
  }

  function renderAll(){
    const { rows, chosenParams } = filterData();
    document.getElementById('recCount').textContent = rows.length;
    renderKPIs(rows, chosenParams);
    renderInsights(rows, chosenParams);

    if (currentView === 'charts') {
      renderChartsForParams(rows, chosenParams);
    } else if (currentView === 'map') {
      renderMap(rows, chosenParams);
    }
  }

  function renderInsights(rows, params) {
    const insights = generateInsights(rows, params);
    document.getElementById('insightsArea').innerHTML = insights.join('');
  }

  tomLoc.on('change', ()=> scheduleRender());
  tomMonth.on('change', ()=> scheduleRender());
  tomParam.on('change', ()=> scheduleRender());
  sliderDiv.noUiSlider.on('change', ()=> scheduleRender());
  document.getElementById('monthlyAvgToggle').addEventListener('change', ()=> scheduleRender());

  scheduleRender(250);
  window.refreshDashboard = function(){ scheduleRender(0); };
});
</script>
</body>
</html>'''

    # replace placeholders safely
    out_html = html_template.replace("__DATA_JSON__", data_json)
    out_html = out_html.replace("__MONTHS_JSON__", months_json)
    out_html = out_html.replace("__PARAMS_JSON__", params_json)
    out_html = out_html.replace("__LOCS_JSON__", locs_json)
    out_html = out_html.replace("__YEARS_JSON__", years_json)
    out_html = out_html.replace("__COORDS_JSON__", coords_json)

    out_path.write_text(out_html, encoding="utf-8")
    print("Wrote dashboard to:", out_path)
    return out_path


# ----------------------- MAIN -----------------------
def main():
    xlsx = locate_input_file()
    print("Reading:", xlsx)
    df = read_excel_of_interest(xlsx)
    df = normalize_dataframe(df)

    if df is None or df.empty:
        print("No usable data found in the Excel. Exiting.")
        sys.exit(1)

    locations, months, years = prepare_lists_from_df(df)
    numeric_params = get_numeric_params(df)
    if not numeric_params:
        print("No numeric parameters found. Exiting.")
        sys.exit(1)

    has_coords, location_coords = check_coordinates_availability(df)

    if has_coords:
        print(f"Found coordinates for {len(location_coords)} locations")
        for loc, coords in list(location_coords.items())[:5]:
            print(f"  {loc}: {coords['lat']:.4f}, {coords['lng']:.4f}")
        if len(location_coords) > 5:
            print(f"  ... and {len(location_coords) - 5} more locations")
    else:
        print("No latitude/longitude coordinates found in the Excel file")

    rows = prepare_json_rows(df)

    print("DEBUG: locations:", locations[:10])
    print("DEBUG: months:", months[:12])
    print("DEBUG: years:", years[:10])
    print("DEBUG: numeric params:", numeric_params[:20])

    out_path = Path(__file__).resolve().parent / OUTPUT_HTML
    build_html(rows, months, numeric_params, locations, years, location_coords, out_path)

    try:
        webbrowser.open(out_path.resolve().as_uri())
    except Exception:
        print("Open the file manually:", out_path)


if __name__ == "__main__":
    main()
