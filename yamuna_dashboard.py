"""
Yamuna Plotly Dashboard - Enhanced Version with Detailed WQI Calculation Table
==============================================================================
ENHANCED FEATURE: Interactive WQI calculation table showing step-by-step computation

Features:
- Interactive water quality visualization with charts and maps
- Detailed WQI calculation breakdown table on hover
- Step-by-step calculation showing formulas and values
- Real-time data filtering and analysis
- User data entry capability
- Export functionality
- WQI classification with updated boundaries

Usage:
    python yamuna_dashboard_enhanced_wqi.py

Requirements:
    - pandas
    - numpy
    - Place 'Yamuna Report V4.0.xlsx' next to this script
"""

from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import sys
import json
import webbrowser
import datetime
import logging

try:
    import pandas as pd
    import numpy as np
except ImportError as e:
    print(f"Error: Required package not found. Please install: pip install pandas numpy openpyxl")
    sys.exit(1)

# Configuration
DEFAULT_EXCEL = "Yamuna Report V4.0.xlsx"
OUTPUT_HTML = "yamuna_dashboard_wqi_enhanced.html"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DataProcessor:
    """Handles data reading, normalization, and preparation"""

    @staticmethod
    def locate_input_file() -> Path:
        """Locate Excel file in script directory"""
        base = Path(__file__).resolve().parent
        candidate = base / DEFAULT_EXCEL

        if candidate.exists():
            logger.info(f"Found Excel file: {candidate}")
            return candidate

        # Try current working directory
        cwd_candidate = Path.cwd() / DEFAULT_EXCEL
        if cwd_candidate.exists():
            logger.info(f"Found Excel file in current directory: {cwd_candidate}")
            return cwd_candidate

        # Look for any Excel file in the directory
        for pattern in ["*.xlsx", "*.xls"]:
            excel_files = list(base.glob(pattern))
            if excel_files:
                logger.info(f"Found Excel file: {excel_files[0]}")
                return excel_files[0]

            excel_files = list(Path.cwd().glob(pattern))
            if excel_files:
                logger.info(f"Found Excel file: {excel_files[0]}")
                return excel_files[0]

        logger.error(f"Excel file not found! Please place '{DEFAULT_EXCEL}' in the same directory as this script.")
        logger.error(f"Searched in: {base} and {Path.cwd()}")
        sys.exit(1)

    @staticmethod
    def read_excel_file(path: Path) -> pd.DataFrame:
        """Read Excel file with error handling"""
        try:
            df = pd.read_excel(path, sheet_name="Working Sheet")
        except ValueError:
            logger.warning("'Working Sheet' not found, using default sheet")
            df = pd.read_excel(path)
        except Exception as e:
            logger.error(f"Error reading Excel file: {e}")
            sys.exit(1)

        df = df.replace(['*', '* ', ' *', '**', 'NA', 'N/A', 'n/a', '#', '-', '--','Nil', 'nil', 'NIL'], np.nan)
        return df

    @staticmethod
    def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        """Normalize and clean DataFrame"""
        df = df.copy()
        df.columns = df.columns.astype(str).str.strip()
        df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
        df = df.dropna(axis=1, how="all")

        column_mappings = {
            "TSS(mg/L)": "TSS_mg_L",
            "Total_Coliform_MPN_100ml": "Total_Coliform",
            "Faecal_Coliform_MPN_100ml": "Faecal_Coliform",
            "Surfactant (mg/L)": "Surfactant_mg_L",
            "COD (mg/l)": "COD_mg_L",
            "BOD (mg/l)": "BOD_mg_L",
            "DO (mg/l)": "DO_mg_L",
        }

        for old_name, new_name in column_mappings.items():
            if old_name in df.columns and new_name not in df.columns:
                df = df.rename(columns={old_name: new_name})

        df = DataProcessor._ensure_essential_columns(df)
        df = DataProcessor._process_temporal_columns(df)
        df = DataProcessor._convert_numeric_columns(df)
        df = DataProcessor._clean_data(df)
        return df.reset_index(drop=True)

    @staticmethod
    def _ensure_essential_columns(df: pd.DataFrame) -> pd.DataFrame:
        """Ensure Year, Location, Lat, Long columns exist"""
        if "Year" not in df.columns:
            year_candidates = [c for c in df.columns if c.lower().strip() == "year"]
            if year_candidates:
                df = df.rename(columns={year_candidates[0]: "Year"})

        if "Location" not in df.columns:
            location_candidates = [
                c for c in df.columns
                if any(keyword in c.lower() for keyword in ["location", "site", "station"])
            ]
            if location_candidates:
                df = df.rename(columns={location_candidates[0]: "Location"})

        lat_cols = [c for c in df.columns if c.lower() in ['lat', 'latitude']]
        if lat_cols:
            df = df.rename(columns={lat_cols[0]: "Lat"})

        lon_cols = [c for c in df.columns if c.lower() in ['long', 'lon', 'longitude']]
        if lon_cols:
            df = df.rename(columns={lon_cols[0]: "Long"})

        return df

    @staticmethod
    def _process_temporal_columns(df: pd.DataFrame) -> pd.DataFrame:
        """Process Date, Year, Month columns"""
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

        if "Date" not in df.columns and {"Year", "Month"}.issubset(df.columns):
            month_map = {
                month: i for i, month in enumerate(
                    ["January", "February", "March", "April", "May", "June",
                     "July", "August", "September", "October", "November", "December"],
                    start=1
                )
            }
            df["Month"] = df["Month"].astype(str).str.strip()
            df["Month_Num"] = df["Month"].map(lambda v: month_map.get(v) if isinstance(v, str) else v)
            df["Date"] = pd.to_datetime(
                df["Year"].astype(str) + "-" + df["Month_Num"].astype(str) + "-01",
                errors="coerce"
            )

        if "Month" not in df.columns and "Date" in df.columns:
            df["Month"] = df["Date"].dt.strftime("%B")

        if "Year" in df.columns:
            df["Year"] = pd.to_numeric(df["Year"], errors="coerce").astype("Int64")

        return df

    @staticmethod
    def _convert_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
        """Convert columns to numeric types where applicable"""
        for col in ["Lat", "Long"]:
            if col in df.columns:
                df[col] = df[col].replace(['*', '* ', ' *'], np.nan)
                df[col] = pd.to_numeric(df[col], errors="coerce")

        essential_cols = {"Year", "Month", "Location", "Date", "Month_Num", "Lat", "Long"}
        for col in [c for c in df.columns if c not in essential_cols]:
            df[col] = df[col].replace(['*', '* ', ' *', '**', 'NA', 'N/A', 'n/a', '#', '-', '--', ''], np.nan)
            df[col] = pd.to_numeric(df[col], errors="coerce")
        # Also treat 'Nil', 'nil', 'NIL' as NaN
        df[col] = df[col].replace(['Nil', 'nil', 'NIL'], np.nan)
        return df

    @staticmethod
    def _clean_data(df: pd.DataFrame) -> pd.DataFrame:
        """Clean and filter data"""
        if "Date" in df.columns and "Location" in df.columns:
            df = df.dropna(subset=["Date", "Location"], how="any")

        numeric_cols = df.select_dtypes(include=[np.number]).columns
        if len(numeric_cols) > 0:
            df = df[df[numeric_cols].notna().any(axis=1)]

        if len(df) > 0:
            first_row = df.iloc[0]
            if any(
                    isinstance(val, str) and
                    any(keyword in str(val).lower() for keyword in ["weight", "ideal range"])
                    for val in first_row.values
            ):
                df = df.iloc[1:].reset_index(drop=True)

        if "WQI" in df.columns:
            df.loc[df["WQI"] == 0, "WQI"] = np.nan
            logger.info(f"Replaced 0 values in WQI column with NaN")

        return df

    @staticmethod
    def get_numeric_parameters(df: pd.DataFrame) -> List[str]:
        """Extract numeric parameter names from DataFrame"""
        essential_cols = {"Year", "Month", "Location", "Date", "Month_Num", "Lat", "Long"}
        candidates = [c for c in df.columns if c not in essential_cols]

        numeric_params = []
        for col in candidates:
            if pd.api.types.is_numeric_dtype(df[col]):
                if df[col].dropna().apply(lambda v: np.isfinite(v)).any():
                    numeric_params.append(col)

        if not numeric_params:
            fallback_params = [
                "WQI", "pH", "DO_mg_L", "BOD_mg_L", "COD_mg_L",
                "TSS_mg_L", "Total_Coliform"
            ]
            numeric_params = [p for p in fallback_params if p in df.columns]

        return numeric_params

    @staticmethod
    def prepare_json_data(df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Convert DataFrame to JSON-safe format"""

        def convert_value(v):
            if pd.isna(v):
                return None
            if isinstance(v, (np.floating, float)) and not np.isfinite(v):
                return None
            if isinstance(v, (pd.Timestamp, datetime.datetime, np.datetime64)):
                try:
                    return pd.to_datetime(v).isoformat()
                except Exception:
                    return str(v)
            if isinstance(v, np.integer):
                return int(v)
            if isinstance(v, np.floating):
                if np.isnan(v):
                    return None
                return float(v)
            if isinstance(v, str) and v.strip() in ['*', 'NA', 'N/A', '#', '']:
                return None
            return v

        rows = df.to_dict(orient="records")
        return [{k: convert_value(v) for k, v in row.items()} for row in rows]

    @staticmethod
    def extract_metadata(df: pd.DataFrame) -> Tuple[List[str], List[str], List[int]]:
        """Extract locations, months, and years from DataFrame"""

        def get_unique_values(series):
            values = []
            for v in series.dropna().unique():
                if v is None:
                    continue
                s = str(v).strip()
                if s and s.lower() != "nan":
                    values.append(s)
            seen = set()
            return [x for x in values if not (x in seen or seen.add(x))]

        locations = get_unique_values(df["Location"]) if "Location" in df.columns else []

        month_order = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        months_in_data = get_unique_values(df["Month"]) if "Month" in df.columns else []
        months = [m for m in month_order if m in months_in_data] or month_order

        years = []
        if "Year" in df.columns:
            try:
                year_values = df["Year"].dropna().unique()
                years = sorted([int(y) for y in year_values])
            except Exception:
                pass

        if not years and "Date" in df.columns:
            years = sorted(list({
                int(d.year) for d in pd.to_datetime(df["Date"].dropna())
            }))

        if not locations:
            locations = ["No location found"]
        if not years:
            current_year = datetime.datetime.now().year
            years = list(range(current_year - 4, current_year + 1))

        return locations, months, years

    @staticmethod
    def check_coordinates(df: pd.DataFrame) -> Tuple[bool, Dict[str, Dict[str, float]]]:
        """Check if coordinates are available and extract them"""
        if "Lat" not in df.columns or "Long" not in df.columns:
            return False, {}

        location_coords = {}
        for _, row in df.iterrows():
            location = row.get("Location")
            lat = row.get("Lat")
            lng = row.get("Long")

            if location and pd.notna(lat) and pd.notna(lng):
                if location not in location_coords:
                    location_coords[location] = {
                        "lat": float(lat),
                        "lng": float(lng)
                    }

        return len(location_coords) > 0, location_coords


class HTMLGenerator:
    """Generates the HTML dashboard"""

    @staticmethod
    def generate_dashboard(
            data_rows: List[Dict],
            months: List[str],
            params: List[str],
            locations: List[str],
            years: List[int],
            location_coords: Dict[str, Dict[str, float]],
            output_path: Path
    ) -> Path:
        """Generate complete HTML dashboard"""

        def safe_json_dump(obj):
            json_str = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
            return json_str.replace("</script>", "<\\/script>")

        data_json = safe_json_dump(data_rows)
        months_json = safe_json_dump(months)
        params_json = safe_json_dump(params)
        locations_json = safe_json_dump(locations)
        years_json = safe_json_dump(years)
        coords_json = safe_json_dump(location_coords)

        html_content = HTMLGenerator._get_html_template()

        html_content = html_content.replace("__DATA_JSON__", data_json)
        html_content = html_content.replace("__MONTHS_JSON__", months_json)
        html_content = html_content.replace("__PARAMS_JSON__", params_json)
        html_content = html_content.replace("__LOCS_JSON__", locations_json)
        html_content = html_content.replace("__YEARS_JSON__", years_json)
        html_content = html_content.replace("__COORDS_JSON__", coords_json)

        output_path.write_text(html_content, encoding="utf-8")
        logger.info(f"Dashboard written to: {output_path}")

        return output_path

    @staticmethod
    def _get_html_template() -> str:
        """Return the complete HTML template with enhanced WQI calculation table"""
        return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Yamuna Water Quality - Enhanced WQI Calculator Dashboard</title>

<link href="https://cdn.jsdelivr.net/npm/tom-select/dist/css/tom-select.default.min.css" rel="stylesheet" />
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />

<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/tom-select/dist/js/tom-select.complete.min.js"></script>
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

.wqi-breakdown-panel {
  background: linear-gradient(135deg, #fef9c3, #fef3c7);
  border: 3px solid #eab308;
  border-radius: 12px;
  padding: 20px;
  margin-top: 20px;
  box-shadow: 0 8px 16px rgba(234, 179, 8, 0.25);
  display: block;
  transition: all 0.3s ease;
}
.wqi-breakdown-panel.updated {
  animation: highlight 0.5s ease;
}
@keyframes highlight {
  0% { box-shadow: 0 8px 16px rgba(234, 179, 8, 0.25); }
  50% { box-shadow: 0 12px 24px rgba(234, 179, 8, 0.5), 0 0 20px rgba(234, 179, 8, 0.3); }
  100% { box-shadow: 0 8px 16px rgba(234, 179, 8, 0.25); }
}
.wqi-breakdown-title {
  font-size: 18px;
  font-weight: 700;
  color: #78350f;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;   /* ← NEW VALUE */
  padding-bottom: 12px;
  border-bottom: 2px solid #eab308;
}
.wqi-breakdown-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}
.wqi-summary-item {
  background: white;
  padding: 14px;
  border-radius: 8px;
  box-shadow: 0 2px 6px rgba(0,0,0,0.06);
  border-left: 4px solid #eab308;
}
.wqi-summary-label {
  font-size: 12px;
  color: #78716c;
  margin-bottom: 6px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.wqi-summary-value {
  font-size: 20px;
  font-weight: 700;
  color: #78350f;
}

/* Enhanced calculation table */
.wqi-calculation-section {
  background: white;
  border-radius: 10px;
  padding: 16px;
  margin-bottom: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.calc-section-title {
  font-size: 15px;
  font-weight: 700;
  color: #78350f;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 2px solid #fef3c7;
}
.wqi-breakdown-table {
  background: white;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}
.wqi-breakdown-table table {
  width: 100%;
  border-collapse: collapse;
}
.wqi-breakdown-table th {
  background: #fef3c7;
  color: #78350f;
  font-weight: 600;
  text-align: left;
  padding: 12px;
  font-size: 14px;
  border-bottom: 2px solid #eab308;
}
.wqi-breakdown-table td {
  padding: 12px;
  border-bottom: 1px solid #fafaf9;
  font-size: 14px;
}
.wqi-breakdown-table tr:last-child td {
  border-bottom: none;
}
.wqi-breakdown-table tr:hover {
  background: #fefce8;
}
.param-badge {
  display: inline-block;
  padding: 6px 10px;
  border-radius: 6px;
  font-weight: 700;
  font-size: 12px;
  letter-spacing: 0.5px;
}
.param-badge-pH { background: #dbeafe; color: #1e40af; }
.param-badge-BOD { background: #fed7aa; color: #9a3412; }
.param-badge-DO { background: #dcfce7; color: #166534; }
.formula-display {
  background: #fafaf9;
  padding: 10px 12px;
  border-radius: 6px;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  color: #57534e;
  border-left: 3px solid #eab308;
  margin: 8px 0;
  overflow-x: auto;
}
.calculation-step {
  background: #fafaf9;
  padding: 12px;
  border-radius: 6px;
  margin: 8px 0;
  border-left: 3px solid #14b8a6;
}
.step-label {
  font-size: 11px;
  font-weight: 600;
  color: #0f766e;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}
.step-value {
  font-size: 14px;
  font-weight: 700;
  color: #115e59;
}
.final-wqi-result {
  background: linear-gradient(135deg, #14b8a6, #06b6d4);
  color: white;
  padding: 16px;
  border-radius: 8px;
  text-align: center;
  font-size: 18px;
  font-weight: 700;
  margin-top: 16px;
  box-shadow: 0 4px 12px rgba(20, 184, 166, 0.3);
}
.contribution-bar {
  height: 26px;
  background: linear-gradient(90deg, #eab308, #fbbf24);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding-right: 10px;
  color: #78350f;
  font-weight: 700;
  font-size: 12px;
  box-shadow: 0 2px 4px rgba(234, 179, 8, 0.2);
}
.interpretation-box {
  background: white;
  border: 2px solid #14b8a6;
  border-radius: 8px;
  padding: 14px;
  margin-top: 16px;
  font-size: 13px;
  color: #0f172a;
  line-height: 1.6;
}
.interpretation-box strong {
  color: #0f766e;
}
.no-breakdown-message {
  background: #fef3c7;
  padding: 24px;
  text-align: center;
  border-radius: 8px;
  color: #78350f;
  font-size: 14px;
}
/* Collapsible WQI Breakdown Styles */
.wqi-collapse-btn {
  background: #eab308;
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.2s ease;
}
.wqi-collapse-btn:hover {
  background: #ca8a04;
  transform: translateY(-1px);
  box-shadow: 0 2px 6px rgba(234, 179, 8, 0.3);
}
.wqi-collapse-btn:active {
  transform: translateY(0);
}
.wqi-collapse-icon {
  transition: transform 0.3s ease;
  font-size: 12px;
}
.wqi-collapse-icon.collapsed {
  transform: rotate(-90deg);
}
.wqi-breakdown-content {
  max-height: 5000px;
  overflow: hidden;
  transition: max-height 0.4s ease, opacity 0.3s ease;
  opacity: 1;
}
.wqi-breakdown-content.collapsed {
  max-height: 0;
  opacity: 0;
}
/* ============================================
   WQI COMPARISON TOOL STYLES - START
   ============================================ */

/* Main comparison tool container */
.comparison-tool {
  background: linear-gradient(135deg, #e0f2fe, #dbeafe);
  border: 2px solid #0284c7;
  border-radius: 12px;
  padding: 20px;
  margin-top: 20px;
  margin-bottom: 20px;
}

/* Header styling with collapse button */
.comparison-header {
  font-size: 18px;
  font-weight: 700;
  color: #0c4a6e;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

/* Collapse button */
.comparison-collapse-btn {
  background: #0284c7;
  color: white;
  border: none;
  padding: 6px 14px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.2s ease;
}

.comparison-collapse-btn:hover {
  background: #0369a1;
  transform: translateY(-1px);
}

.comparison-collapse-icon {
  transition: transform 0.3s ease;
  font-size: 11px;
}

.comparison-collapse-icon.collapsed {
  transform: rotate(-90deg);
}

/* Collapsible content wrapper */
.comparison-content {
  max-height: 3000px;
  overflow: hidden;
  transition: max-height 0.4s ease, opacity 0.3s ease;
  opacity: 1;
}

.comparison-content.collapsed {
  max-height: 0;
  opacity: 0;
}

/* Grid for two point selectors */
.comparison-selectors {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-bottom: 20px;
}
/* Grid for two point selectors */
.comparison-selectors {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-bottom: 20px;
}

/* Individual point selector card */
.point-selector {
  background: white;
  padding: 16px;
  border-radius: 8px;
  box-shadow: 0 2px 6px rgba(0,0,0,0.06);
  border-left: 4px solid #0284c7;
}

.point-selector h4 {
  margin: 0 0 12px 0;
  color: #0c4a6e;
  font-size: 14px;
  font-weight: 600;
}

.point-selector select {
  width: 100%;
  padding: 8px;
  margin-bottom: 10px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 13px;
}

/* Info box showing selected point details */
.point-info {
  background: #f0f9ff;
  padding: 10px;
  border-radius: 6px;
  margin-top: 10px;
  font-size: 12px;
  min-height: 80px;
}

.point-info .label {
  color: #64748b;
  font-weight: 600;
  margin-bottom: 4px;
}

.point-info .value {
  font-size: 20px;
  font-weight: 700;
  color: #0284c7;
}

/* Compare button */
.compare-btn {
  background: linear-gradient(135deg, #0284c7, #0369a1);
  color: white;
  border: none;
  padding: 12px 24px;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  font-size: 14px;
  width: 100%;
  transition: all 0.2s;
  margin-top: 10px;
}

.compare-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(2, 132, 199, 0.3);
}

.compare-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
  transform: none;
}

/* Results container */
.comparison-results {
  background: white;
  border-radius: 10px;
  padding: 20px;
  margin-top: 20px;
  display: none;
  animation: slideIn 0.3s ease;
}

@keyframes slideIn {
  from { opacity: 0; transform: translateY(-10px); }
  to { opacity: 1; transform: translateY(0); }
}

.results-header {
  font-size: 16px;
  font-weight: 700;
  color: #0c4a6e;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 2px solid #e0f2fe;
}

/* Summary cards showing WQI values */
.wqi-change-summary {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}

.change-card {
  background: #f8fafc;
  padding: 14px;
  border-radius: 8px;
  text-align: center;
  border: 2px solid #e2e8f0;
}

.change-card.positive {
  border-color: #10b981;
  background: #ecfdf5;
}

.change-card.negative {
  border-color: #ef4444;
  background: #fef2f2;
}

.change-card .label {
  font-size: 11px;
  color: #64748b;
  font-weight: 600;
  text-transform: uppercase;
  margin-bottom: 6px;
}

.change-card .value {
  font-size: 24px;
  font-weight: 700;
  color: #0f172a;
}

.change-card.positive .value {
  color: #10b981;
}

.change-card.negative .value {
  color: #ef4444;
}

/* Parameter contributions section */
.parameter-contributions {
  background: #fafafa;
  border-radius: 8px;
  padding: 16px;
  margin-top: 16px;
}

.contribution-item {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  padding: 12px;
  background: white;
  border-radius: 6px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

.contribution-rank {
  font-size: 20px;
  font-weight: 700;
  color: #0284c7;
  min-width: 40px;
}

.contribution-details {
  flex: 1;
  margin: 0 16px;
}

.contribution-param {
  font-weight: 700;
  color: #0f172a;
  font-size: 14px;
  margin-bottom: 4px;
}

.contribution-change {
  font-size: 12px;
  color: #64748b;
}

.contribution-bar-container {
  flex: 2;
  position: relative;
}

.contribution-bar {
  height: 28px;
  background: linear-gradient(90deg, #0284c7, #0ea5e9);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding-right: 10px;
  color: white;
  font-weight: 700;
  font-size: 13px;
  box-shadow: 0 2px 4px rgba(2, 132, 199, 0.2);
  transition: all 0.3s;
}

.contribution-bar:hover {
  transform: scaleX(1.02);
  box-shadow: 0 3px 8px rgba(2, 132, 199, 0.3);
}

/* Interpretation text box */
.interpretation-text {
  background: linear-gradient(135deg, #fef3c7, #fde68a);
  border-left: 4px solid #f59e0b;
  padding: 14px;
  border-radius: 8px;
  margin-top: 16px;
  font-size: 13px;
  line-height: 1.6;
  color: #78350f;
}

/* ============================================
   WQI COMPARISON TOOL STYLES - END
   ============================================ */
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
<div class="header"><h1>🌊 Yamuna Water Quality - WQI Calculator Dashboard</h1></div>
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
          <button id="selectAllLocations" class="small-btn">All</button>
          <button id="clearLocations" class="small-btn">Clear</button>
        </div>
      </div>
      <select id="selLocation" multiple placeholder="Choose locations..."></select>

      <div class="select-label" style="margin-top:12px;">
        <div>Years</div>
        <div style="display:flex; gap:6px;">
          <button id="selectAllYears" class="small-btn">All</button>
          <button id="clearYears" class="small-btn">Clear</button>
        </div>
      </div>
      <select id="selYear" multiple placeholder="Choose years..."></select>

      <div class="select-label" style="margin-top:12px;">
        <div>Months</div>
        <div style="display:flex; gap:6px;">
          <button id="selectAllMonths" class="small-btn">All</button>
          <button id="clearMonths" class="small-btn">Clear</button>
        </div>
      </div>
      <select id="selMonth" multiple placeholder="Choose months..."></select>

      <div class="select-label" style="margin-top:12px;">
        <div>Parameters</div>
        <div style="display:flex; gap:6px;">
          <button id="selectAllParams" class="small-btn">All</button>
          <button id="clearParams" class="small-btn">Clear</button>
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

      <div class="footer-note">💡 Hover over WQI chart points - calculation details appear below the chart</div>
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
      <div class="view-toggle">
        <button id="chartsViewBtn" class="active">📊 Charts View</button>
        <button id="mapViewBtn">🗺️ Map View</button>
      </div>

      <div id="chartsContainer" class="charts-grid"></div>
      <div id="mapContainer" style="display:none;"></div>
      <div id="noMapMessage" style="display:none;" class="no-coords-message">
        <strong>No Location Coordinates Available</strong><br>
        The Excel file does not contain latitude and longitude data.
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

  let map = null;
  let currentView = 'charts';

  // WQI Calculation Functions
  function calculateWQIBreakdown(pH, BOD, DO) {
    if (pH === null || BOD === null || DO === null) {
      return null;
    }

    // Standards (Si)
    const S_pH = 8.5;
    const S_BOD = 3;
    const S_DO = 5;

    // Ideal values (Ii)
    const I_pH = 7;
    const I_BOD = 0;
    const I_DO = 14.6;

    // Calculate Qi (sub-index) for each parameter
    const Qi_pH = pH >= 7 
      ? ((pH - 7) / (S_pH - 7)) * 100
      : ((7 - pH) / (7 - 6.5)) * 100;

    const Qi_BOD = ((BOD - I_BOD) / (S_BOD - I_BOD)) * 100;

    const Qi_DO = Math.max(0, ((I_DO - DO) / (I_DO - S_DO)) * 100);

    // Calculate k (constant of proportionality)
    const k = 1 / (1/S_pH + 1/S_BOD + 1/S_DO);

    // Calculate weights (Wi)
    const w_pH = k / S_pH;
    const w_BOD = k / S_BOD;
    const w_DO = k / S_DO;

    // Calculate weighted contributions
    const contrib_pH = Qi_pH * w_pH;
    const contrib_BOD = Qi_BOD * w_BOD;
    const contrib_DO = Qi_DO * w_DO;

    // Calculate final WQI
    const WQI = contrib_pH + contrib_BOD + contrib_DO;

    return {
      WQI: WQI,
      k: k,
      parameters: [
        {
          name: 'pH',
          measured: pH,
          standard: S_pH,
          ideal: I_pH,
          Qi: Qi_pH,
          Qi_formula: pH >= 7 ? `((${pH.toFixed(2)} - 7) / (${S_pH} - 7)) × 100` : `((7 - ${pH.toFixed(2)}) / (7 - 6.5)) × 100`,
          weight: w_pH,
          weight_formula: `${k.toFixed(4)} / ${S_pH}`,
          contribution: contrib_pH,
          contrib_formula: `${Qi_pH.toFixed(2)} × ${w_pH.toFixed(4)}`,
          contributionPercent: (contrib_pH / WQI) * 100
        },
        {
          name: 'BOD',
          measured: BOD,
          standard: S_BOD,
          ideal: I_BOD,
          Qi: Qi_BOD,
          Qi_formula: `((${BOD.toFixed(2)} - ${I_BOD}) / (${S_BOD} - ${I_BOD})) × 100`,
          weight: w_BOD,
          weight_formula: `${k.toFixed(4)} / ${S_BOD}`,
          contribution: contrib_BOD,
          contrib_formula: `${Qi_BOD.toFixed(2)} × ${w_BOD.toFixed(4)}`,
          contributionPercent: (contrib_BOD / WQI) * 100
        },
        {
          name: 'DO',
          measured: DO,
          standard: S_DO,
          ideal: I_DO,
          Qi: Qi_DO,
          Qi_formula: `max(0, ((${I_DO} - ${DO.toFixed(2)}) / (${I_DO} - ${S_DO})) × 100)`,
          weight: w_DO,
          weight_formula: `${k.toFixed(4)} / ${S_DO}`,
          contribution: contrib_DO,
          contrib_formula: `${Qi_DO.toFixed(2)} × ${w_DO.toFixed(4)}`,
          contributionPercent: (contrib_DO / WQI) * 100
        }
      ]
    };
  }
// Collapsible breakdown state and toggle function
  let isBreakdownCollapsed = false;

  function toggleBreakdownCollapse() {
    isBreakdownCollapsed = !isBreakdownCollapsed;
    const content = document.querySelector('.wqi-breakdown-content');
    const icon = document.querySelector('.wqi-collapse-icon');
    const btn = document.querySelector('.wqi-collapse-btn');
    
    if (content && icon && btn) {
      if (isBreakdownCollapsed) {
        content.classList.add('collapsed');
        icon.classList.add('collapsed');
        btn.innerHTML = '<span class="wqi-collapse-icon collapsed">▼</span> Show Details';
      } else {
        content.classList.remove('collapsed');
        icon.classList.remove('collapsed');
        btn.innerHTML = '<span class="wqi-collapse-icon">▼</span> Hide Details';
      }
    }
  }

  window.toggleBreakdownCollapse = toggleBreakdownCollapse;
  function renderWQIBreakdownPanel(breakdown, location, date) {
    if (!breakdown) {
      return '<div style="padding:20px; text-align:center; color:#78716c; font-size:14px;">Calculation details will appear here when you hover over a data point</div>';
    }
        // Sort parameters by contribution (descending) to show worst offenders first
    const sortedParams = [...breakdown.parameters].sort((a, b) => b.contribution - a.contribution);

    let html = '<div class="wqi-breakdown-title">';
    html += '<span>🧮 WQI Calculation Breakdown</span>';
    html += '<button class="wqi-collapse-btn" onclick="toggleBreakdownCollapse()">';
    html += '<span class="wqi-collapse-icon">▼</span> Hide Details';
    html += '</button>';
    html += '</div>';

    // Summary section
    html += '<div class="wqi-breakdown-summary">';
    html += '<div class="wqi-summary-item">';
    html += '<div class="wqi-summary-label">Location</div>';
    html += `<div class="wqi-summary-value">${location || 'N/A'}</div>`;
    html += '</div>';
    html += '<div class="wqi-summary-item">';
    html += '<div class="wqi-summary-label">Date</div>';
    html += `<div class="wqi-summary-value">${date ? new Date(date).toLocaleDateString() : 'N/A'}</div>`;
    html += '</div>';
    html += '<div class="wqi-summary-item">';
    html += '<div class="wqi-summary-label">Final WQI</div>';
    html += `<div class="wqi-summary-value">${breakdown.WQI.toFixed(2)}</div>`;
    html += '</div>';
    html += '</div>';
    html += '<div class="wqi-breakdown-content">';  // ← ADD THIS LINE
    // Step 1: Constants
    html += '<div class="wqi-calculation-section">';
    html += '<div class="calc-section-title">Step 1: Calculate Constant (k)</div>';
    html += '<div class="formula-display">';
    html += `k = 1 / (1/S<sub>pH</sub> + 1/S<sub>BOD</sub> + 1/S<sub>DO</sub>)<br>`;
    html += `k = 1 / (1/8.5 + 1/3 + 1/5) = ${breakdown.k.toFixed(4)}`;
    html += '</div>';
    html += '</div>';

    // Step 2: Measured Values
    html += '<div class="wqi-calculation-section">';
    html += '<div class="calc-section-title">Step 2: Measured Values</div>';
    html += '<div class="wqi-breakdown-table"><table>';
    html += '<thead><tr>';
    html += '<th>Parameter</th><th>Measured</th><th>Standard (Si)</th><th>Ideal (Ii)</th>';
    html += '</tr></thead><tbody>';
    sortedParams.forEach(param => {
      const badgeClass = `param-badge-${param.name}`;
      html += '<tr>';
      html += `<td><span class="param-badge ${badgeClass}">${param.name}</span></td>`;
      html += `<td><strong>${param.measured.toFixed(2)}</strong></td>`;
      html += `<td>${param.standard}</td>`;
      html += `<td>${param.ideal}</td>`;
      html += '</tr>';
    });
    html += '</tbody></table></div>';
    html += '</div>';

    // Step 3: Sub-indices (Qi)
    html += '<div class="wqi-calculation-section">';
    html += '<div class="calc-section-title">Step 3: Calculate Sub-indices (Qi)</div>';
    html += '<div class="wqi-breakdown-table"><table>';
    html += '<thead><tr>';
    html += '<th>Parameter</th><th>Qi Formula</th><th>Qi Value</th>';
    html += '</tr></thead><tbody>';
    sortedParams.forEach(param => {
      const badgeClass = `param-badge-${param.name}`;
      html += '<tr>';
      html += `<td><span class="param-badge ${badgeClass}">${param.name}</span></td>`;
      html += `<td><div class="formula-display" style="margin:4px 0;">${param.Qi_formula}</div></td>`;
      html += `<td><strong>${param.Qi.toFixed(2)}</strong></td>`;
      html += '</tr>';
    });
    html += '</tbody></table></div>';
    html += '</div>';

    // Step 4: Weights (Wi)
    html += '<div class="wqi-calculation-section">';
    html += '<div class="calc-section-title">Step 4: Calculate Weights (Wi)</div>';
    html += '<div class="wqi-breakdown-table"><table>';
    html += '<thead><tr>';
    html += '<th>Parameter</th><th>Weight Formula</th><th>Weight (Wi)</th>';
    html += '</tr></thead><tbody>';
    sortedParams.forEach(param => {
      const badgeClass = `param-badge-${param.name}`;
      html += '<tr>';
      html += `<td><span class="param-badge ${badgeClass}">${param.name}</span></td>`;
      html += `<td><div class="formula-display" style="margin:4px 0;">${param.weight_formula}</div></td>`;
      html += `<td><strong>${param.weight.toFixed(4)}</strong></td>`;
      html += '</tr>';
    });
    html += '</tbody></table></div>';
    html += '</div>';

    // Step 5: Contributions
html += '<div class="wqi-calculation-section">';
html += '<div class="calc-section-title">Step 5: Calculate Weighted Contributions</div>';
html += '<div class="wqi-breakdown-table"><table>';
html += '<thead><tr>';
html += '<th>Parameter</th><th>Contribution Formula</th><th>Contribution</th><th>% Impact</th>';
html += '</tr></thead><tbody>';
sortedParams.forEach(param => {
  const badgeClass = `param-badge-${param.name}`;
  html += '<tr>';
  html += `<td><span class="param-badge ${badgeClass}">${param.name}</span></td>`;
  html += `<td><div class="formula-display" style="margin:4px 0;">${param.contrib_formula}</div></td>`;
  html += `<td><strong>${param.contribution.toFixed(2)}</strong></td>`;
  html += `<td><div style="display: inline-block; padding: 8px 16px; background: #e0f2fe; border: 2px solid #0284c7; border-radius: 8px; font-size: 13px; font-weight: 700; color: #0284c7;">${param.contributionPercent.toFixed(1)}%</div></td>`;
  html += '</tr>';
});
html += '</tbody></table></div>';
html += '</div>';

    // Final WQI Calculation
    html += '<div class="wqi-calculation-section">';
    html += '<div class="calc-section-title">Step 6: Final WQI Calculation</div>';
    html += '<div class="formula-display">';
    html += `WQI = `;
    sortedParams.forEach((param, idx) => {
      html += `${param.contribution.toFixed(2)}`;
      if (idx < sortedParams.length - 1) html += ' + ';
    });
    html += ` = ${breakdown.WQI.toFixed(2)}`;
    html += '</div>';
    html += `<div class="final-wqi-result">Final WQI = ${breakdown.WQI.toFixed(2)}</div>`;
    html += '</div>';

    // Interpretation
    const worst = sortedParams[0];
    html += `<div class="interpretation-box">`;
    html += `<strong>💡 Interpretation:</strong><br><br>`;
    html += `<strong>${worst.name}</strong> is the primary factor affecting water quality, contributing <strong>${worst.contributionPercent.toFixed(1)}%</strong> to the WQI. `;
    if (worst.Qi > 100) {
      html += `The measured value (<strong>${worst.measured.toFixed(2)}</strong>) significantly exceeds the standard (<strong>${worst.standard}</strong>), indicating poor water quality for this parameter.`;
    } else if (worst.Qi > 50) {
      html += `The measured value (<strong>${worst.measured.toFixed(2)}</strong>) is approaching concerning levels relative to the standard (<strong>${worst.standard}</strong>).`;
    } else {
      html += `The measured value (<strong>${worst.measured.toFixed(2)}</strong>) is within acceptable limits.`;
    }
    html += '<br><br>';

    // WQI Classification
    let wqiClass = '';
    if (breakdown.WQI < 50) wqiClass = '✅ <strong>Excellent (Class A)</strong> - Water quality is excellent';
    else if (breakdown.WQI < 100) wqiClass = '👍 <strong>Good (Class B)</strong> - Water quality is good';
    else if (breakdown.WQI < 200) wqiClass = '⚠️ <strong>Poor (Class C)</strong> - Water quality is poor';
    else if (breakdown.WQI < 300) wqiClass = '❌ <strong>Very Poor (Class D)</strong> - Water quality is very poor';
    else wqiClass = '🚫 <strong>Unsuitable (Class E)</strong> - Water is unsuitable for use';

    html += `<strong>Water Quality Classification:</strong> ${wqiClass}`;
    html += '</div>';
    html += '</div>';  // ← ADD THIS LINE (closes wqi-breakdown-content)
    return html;
  }

  function getAnalysisValue(val, param) {
    if(typeof val === 'string' && (val.trim() === '*' || val.trim() === '')) return null;
    const num = Number(val);
    if (!Number.isFinite(num)) return null;
    if (param === 'WQI' && num === 0) return null;
    return num;
  }

  function getDisplayValue(val) {
    if(typeof val === 'string' && (val.trim() === '*' || val.trim() === '')) return null;
    const num = Number(val);
    return Number.isFinite(num) ? num : null;
  }
function isNilValue(val) {
  if (val === null || val === undefined) return true;
  if (typeof val === 'string') {
    const trimmed = val.trim().toLowerCase();
    return trimmed === '' || trimmed === '*' || trimmed === 'nil' || 
           trimmed === 'na' || trimmed === 'n/a' || trimmed === '#' || 
           trimmed === '-' || trimmed === '--';
  }
  return false;
}
  function getWQIValue(val) {
    if(typeof val === 'string' && (val.trim() === '*' || val.trim() === '')) return null;
    const num = Number(val);
    if (!Number.isFinite(num) || num === 0) return null;
    return num;
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
  safeAddOptions(document.getElementById('selYear'), YEARS);
  safeAddOptions(document.getElementById('selParam'), PARAMS);
  
  const tomLoc = new TomSelect('#selLocation', { plugins:['remove_button'], create:false, placeholder:'Choose locations...', hideSelected:true });
  const tomMonth = new TomSelect('#selMonth', { plugins:['remove_button'], create:false, placeholder:'Choose months...', hideSelected:true });
  const tomYear = new TomSelect('#selYear', { plugins:['remove_button'], create:false, placeholder:'Choose years...', hideSelected:true });
  const tomParam = new TomSelect('#selParam', { plugins:['remove_button'], create:false, placeholder:'Choose parameters...', hideSelected:true });

  function preferDefaultParam(){
    if(PARAMS && PARAMS.length){
      const p = PARAMS.indexOf('WQI') !== -1 ? 'WQI' : PARAMS[0];
      tomParam.setValue([p]);
    }
  }
  preferDefaultParam();

  function initializeMap() {
    if (map) map.remove();
    map = L.map('mapContainer').setView([28.6139, 77.2090], 10);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors'
    }).addTo(map);
    return map;
  }

  function renderMap(rows, selectedParams) {
    if (!HAS_COORDINATES) {
      document.getElementById('noMapMessage').style.display = 'block';
      document.getElementById('mapContainer').style.display = 'none';
      return;
    }

    document.getElementById('noMapMessage').style.display = 'none';
    document.getElementById('mapContainer').style.display = 'block';

    if (!map) initializeMap();

    map.eachLayer(function(layer) {
      if (layer instanceof L.Marker) map.removeLayer(layer);
    });

    const locationData = {};
    rows.forEach(row => {
      const loc = row.Location;
      if (!loc || !LOCATION_COORDS[loc]) return;

      if (!locationData[loc]) {
        locationData[loc] = { coords: LOCATION_COORDS[loc], measurements: [] };
      }

      const measurement = { date: row.Date, year: row.Year, month: row.Month };
      selectedParams.forEach(param => {
        const val = getDisplayValue(row[param]);
        if (val !== null) measurement[param] = val;
      });

      locationData[loc].measurements.push(measurement);
    });

    Object.keys(locationData).forEach(locationName => {
      const locData = locationData[locationName];
      const coords = locData.coords;

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

      let markerColor = '#3388ff';
      if (paramAverages.WQI) {
        const wqi = paramAverages.WQI.avg;
        if (wqi < 50) markerColor = '#059669';
        else if (wqi < 100) markerColor = '#0891b2';
        else if (wqi < 200) markerColor = '#f59e0b';
        else if (wqi < 300) markerColor = '#ef4444';
        else markerColor = '#7c2d12';
      }

      const icon = L.divIcon({
        className: 'custom-marker',
        html: `<div style="background-color: ${markerColor}; width: 20px; height: 20px; border-radius: 50%; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3);"></div>`,
        iconSize: [20, 20],
        iconAnchor: [10, 10]
      });

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

      L.marker([coords.lat, coords.lng], { icon: icon })
        .bindPopup(popupContent)
        .addTo(map);
    });

    const allCoords = Object.values(locationData).map(d => d.coords);
    if (allCoords.length > 0) {
      const bounds = L.latLngBounds(allCoords.map(c => [c.lat, c.lng]));
      map.fitBounds(bounds, { padding: [20, 20] });
    }

    setTimeout(() => map.invalidateSize(), 100);
  }

  function renderWQIYearlyAvg(containerId, rows) {
    const wqiData = {}, zeroData = {};

    for(const r of rows){
        const year = r.Year;
        const wqi = r["WQI"];
        if(!year || wqi === null || wqi === undefined) continue;

        if(typeof wqi === 'string' && (wqi.trim() === '*' || wqi.trim() === '')) continue;

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
    if(years.length === 0) {
        document.getElementById(containerId).innerHTML = '<div style="padding:20px;text-align:center;color:#666;">No valid WQI data available for the selected filters</div>';
        return;
    }
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
        { type: 'rect', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: 0, y1: 50, fillcolor: '#059669' + '80', line: {width: 0}, layer: 'below' },
        { type: 'rect', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: 50, y1: 100, fillcolor: '#0891b2' + '80', line: {width: 0}, layer: 'below' },
        { type: 'rect', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: 100, y1: 200, fillcolor: '#f59e0b' + '80', line: {width: 0}, layer: 'below' },
        { type: 'rect', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: 200, y1: 300, fillcolor: '#ef4444' + '80', line: {width: 0}, layer: 'below' },
        // ADD THIS LINE - Deep red background for above 300
        { type: 'rect', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: 300, y1: 10000, fillcolor: '#7f1d1d' + '80', line: {width: 0}, layer: 'below' },
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
        yaxis: { title: 'Average WQI', range: [0, Math.max(...avgWQI) * 1.1], dtick: 50 },
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

    let trendText = '', trendClass = '';

    if (Math.abs(overallChange) < 5) {
      trendText = `${param} levels remained relatively stable from ${firstYear} to ${lastYear} (${overallChange.toFixed(1)}% change)`;
    } else {
      let isImproving = false;
      if (param === 'WQI') isImproving = overallChange < 0;
      else if (param.includes('DO_mg_L')) isImproving = overallChange > 0;
      else isImproving = overallChange < 0;

      if (isImproving) {
        trendText = Math.abs(overallChange) > 20 
          ? `Significant improvement in ${param} from ${firstYear} to ${lastYear} (${Math.abs(overallChange).toFixed(1)}% ${overallChange > 0 ? 'increase' : 'decrease'})`
          : `Moderate improvement in ${param} from ${firstYear} to ${lastYear} (${Math.abs(overallChange).toFixed(1)}% ${overallChange > 0 ? 'increase' : 'decrease'})`;
        trendClass = 'positive-insight';
      } else {
        trendText = Math.abs(overallChange) > 20
          ? `Significant deterioration in ${param} from ${firstYear} to ${lastYear} (${Math.abs(overallChange).toFixed(1)}% ${overallChange > 0 ? 'increase' : 'decrease'})`
          : `Moderate deterioration in ${param} from ${firstYear} to ${lastYear} (${Math.abs(overallChange).toFixed(1)}% ${overallChange > 0 ? 'increase' : 'decrease'})`;
        trendClass = overallChange > 20 ? 'critical-insight' : 'warning-insight';
      }
    }

    if (bestYear !== worstYear) {
      trendText += ` • Best: ${bestYear} (${bestAvg.toFixed(2)}), Worst: ${worstYear} (${worstAvg.toFixed(2)})`;
    }

    return { text: trendText, class: trendClass, years, yearlyAverages };
  }

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

    let trendText = '', trendClass = '';

    if (Math.abs(trendChange) < 5) {
      trendText = `${param} levels remain stable over time (${trendChange.toFixed(1)}% change)`;
    } else {
      let isImproving = false;
      if (param === 'WQI') isImproving = trendChange < 0;
      else if (param.includes('DO_mg_L')) isImproving = trendChange > 0;
      else isImproving = trendChange < 0;

      const formatDate = (date) => date.toLocaleDateString('en-US', { year: 'numeric', month: 'short' });
      const earlyStart = earlyPeriod[0].date;
      const earlyEnd = earlyPeriod[earlyPeriod.length - 1].date;
      const recentStart = recentPeriod[0].date;
      const recentEnd = recentPeriod[recentPeriod.length - 1].date;

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

  function generateInsights(rows, params) {
    const insights = [];

    if (!rows.length || !params.length) {
      return ['<div class="insight-box">Select data to view insights</div>'];
    }

    const uniqueLocations = [...new Set(rows.map(r => r.Location))];
    const yearRange = [...new Set(rows.map(r => r.Year).filter(y => y))];
    const minYear = Math.min(...yearRange);
    const maxYear = Math.max(...yearRange);

    let coverageText = `Data spans <strong>${maxYear - minYear + 1} years</strong> (${minYear}-${maxYear}) across <strong>${uniqueLocations.length} locations</strong> with <strong>${rows.length} measurements</strong>`;
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

    if (params.length === 1) {
      const param = params[0];
      const values = rows.map(r => getAnalysisValue(r[param], param)).filter(v => v !== null);

      if (values.length > 0) {
        let compliantCount = 0;

        values.forEach(val => {
          let isCompliant = true;
          if (param === 'pH') isCompliant = val >= 6.5 && val <= 8.5;
          else if (param.includes('DO_mg_L')) isCompliant = val >= 5;
          else if (param.includes('BOD_mg_L') || param.includes('COD_mg_L')) isCompliant = val <= 3;
          else if (param.includes('Coliform')) isCompliant = val <= 500;
          else if (param === 'WQI') isCompliant = val < 100;
          if (isCompliant) compliantCount++;
        });

        const complianceRate = (compliantCount / values.length) * 100;
        let complianceClass = complianceRate >= 80 ? 'positive-insight' : complianceRate >= 60 ? 'warning-insight' : 'critical-insight';

        insights.push(`<div class="insight-box ${complianceClass}"><strong>Compliance Rate:</strong> ${complianceRate.toFixed(1)}% of valid measurements meet quality standards for ${param}</div>`);
      }
    }

    return insights.slice(0, 7);
  }

  function groupSeries(rows, param, monthly=false){
    const byLoc = {};
    const isWQI = param === 'WQI';

    for(const r of rows){
      if(!r.Date) continue;
      const loc = r.Location || 'Unknown';
      const dt = new Date(r.Date);
      if(isNaN(dt)) continue;

      const val = isWQI ? getWQIValue(r[param]) : getDisplayValue(r[param]);
      const rowObj = { date: dt, value: val, originalRow: r };

      if(!monthly) {
        byLoc[loc] = byLoc[loc] || []; 
        byLoc[loc].push(rowObj);
      } else {
        const key = dt.getFullYear() + '-' + String(dt.getMonth()+1).padStart(2,'0');
        byLoc[loc] = byLoc[loc] || {}; 
        byLoc[loc][key] = byLoc[loc][key] || []; 
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
      const validPoints = arr.filter(pt => pt.value !== null && Number.isFinite(pt.value));

      if(validPoints.length === 0) continue;

      const x = validPoints.map(pt => pt.date.toISOString());
      const y = validPoints.map(pt => isColiform ? pt.value / scaleFactor : pt.value);

      // Store original row data for hover
      const customdata = validPoints.map(pt => pt.originalRow);

      for(const v of y) { 
        globalMin = Math.min(globalMin, v); 
        globalMax = Math.max(globalMax, v); 
      }
      pointsCount += x.length;
      const type = chooseScatterType(x.length);
      traces.push({ 
        x, 
        y, 
        mode:'lines+markers', 
        type: type, 
        name: loc, 
        connectgaps: false,
        customdata: customdata,
        hovertemplate: '<b>%{fullData.name}</b><br>' + param + ': %{y:.2f}<extra></extra>',
        hoverinfo: 'y+name'
      });
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
        const alpha = '50';
        const fill = (b.color || '#cccccc') + alpha;
        shapes.push({ type:'rect', xref:'paper', x0:0, x1:1, yref:'y', y0:visMin, y1:visMax, fillcolor: fill, line:{width:0}, layer:'below' });
        shapes.push({ type:'line', xref:'paper', x0:0, x1:1, yref:'y', y0:Math.max(bandMin, globalMin - margin), y1:Math.max(bandMin, globalMin - margin), line:{dash:'dash', color:(b.color||'#666'), width:1}, layer:'below' });
        annotations.push({ xref:'paper', x:0.99, y: Math.min(visMax, Math.max(visMin, (bandMin + bandMax)/2)), xanchor:'right', text:b.label, showarrow:false, font:{size:11, color:(b.color||'#000')}, bgcolor:'rgba(255,255,255,0.6)', borderpad:4 });
      }
    }

    const layout = {
      title: param + scaleLabel + ' over time (lines = locations)',
      margin: { t:48, l:60, r:40, b:150 },
      legend: { orientation:'h', y:-0.25, x: 0.5, xanchor: 'center', font: { size: 10 } },
      autosize: true,
      xaxis: { automargin:true, tickangle:-45, tickformat: monthly ? '%b %Y' : '%b %Y', showgrid: false },
      yaxis: { automargin:true, title: param + scaleLabel },
      shapes: shapes,
      annotations: annotations,
      hovermode: 'closest'
    };

    Plotly.react(containerId, traces, layout, {responsive:true});

    // Add hover event listener for WQI breakdown
    if (param === 'WQI') {
      const plotDiv = document.getElementById(containerId);

      // Ensure breakdown panel exists
      let breakdownPanel = document.getElementById('wqi_breakdown_panel');
      if (!breakdownPanel) {
        console.log('Creating WQI breakdown panel');
        breakdownPanel = document.createElement('div');
        breakdownPanel.id = 'wqi_breakdown_panel';
        breakdownPanel.className = 'wqi-breakdown-panel';
        breakdownPanel.style.display = 'none';
        plotDiv.parentElement.appendChild(breakdownPanel);
      }

      plotDiv.on('plotly_hover', function(data) {
        console.log('=== WQI HOVER EVENT v2.0 ===');
        const point = data.points[0];
        if (point && point.customdata) {
          const row = point.customdata;
          console.log('Available columns:', Object.keys(row));

          // Find pH, BOD, DO columns by exact matching
          let pH_value = null, BOD_value = null, DO_value = null;

          // Match pH (avoiding Phosphate)
          const phCol = Object.keys(row).find(k => {
            const lower = k.toLowerCase();
            return lower.includes('ph') && !lower.includes('phosph');
          });
          if (phCol) {
            pH_value = row[phCol];
            console.log('✓ Found pH:', phCol, '=', pH_value);
          } else {
            console.log('✗ pH column not found');
          }

          // Match BOD
          const bodCol = Object.keys(row).find(k => k.toLowerCase().includes('bod'));
          if (bodCol) {
            BOD_value = row[bodCol];
            console.log('✓ Found BOD:', bodCol, '=', BOD_value);
          } else {
            console.log('✗ BOD column not found');
          }

          // Match DO (looking for DO_mg)
          const doCol = Object.keys(row).find(k => k.toLowerCase().includes('do_mg'));
          if (doCol) {
            DO_value = row[doCol];
            console.log('✓ Found DO:', doCol, '=', DO_value);
          } else {
            console.log('✗ DO column not found');
          }

          const pH = getDisplayValue(pH_value);
          const BOD = getDisplayValue(BOD_value);
          const DO = getDisplayValue(DO_value);

          console.log('Processed values:', { pH, BOD, DO });

          if (pH !== null && BOD !== null && DO !== null) {
            console.log('✓✓✓ ALL PARAMETERS FOUND - Calculating breakdown');
            try {
              const breakdown = calculateWQIBreakdown(pH, BOD, DO);
              const breakdownHTML = renderWQIBreakdownPanel(breakdown, row.Location, row.Date);

              let panel = document.getElementById('wqi_breakdown_panel');
              if (panel) {
                panel.innerHTML = breakdownHTML;
                panel.style.display = 'block';
                panel.classList.remove('updated');
                void panel.offsetWidth;
                panel.classList.add('updated');
                isBreakdownCollapsed = false;  // ← ADD THIS LINE       
                console.log('✓ Breakdown panel updated successfully');
              }
            } catch (error) {
              console.error('Error calculating breakdown:', error);
            }
          } else {
            console.log('✗✗✗ Missing parameters - cannot calculate');
            let panel = document.getElementById('wqi_breakdown_panel');
            if (panel) {
              panel.style.display = 'none';
            }
          }
        }
      });
    }
  }

  function renderBarAvg(containerId, rows, param){
    const isColiform = param.toLowerCase().includes('coliform');
    const isWQI = param === 'WQI';
    const scaleFactor = isColiform ? 10000 : 1;
    const scaleLabel = isColiform ? ' (x10,000)' : '';

    const map = {};
    for(const r of rows){
      const loc = r.Location || 'Unknown';
      const v = getAnalysisValue(r[param], param);
      if(v === null) continue;
      if(isWQI && v === 0) continue;
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
    <div id="wqi_yearly" style="height:400px; margin-bottom:18px; border: 3px solid #cbd5e1; border-radius: 10px; padding: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08);"></div>
`;
        fragment.appendChild(wqiYearlyBlock);
    }

    for(const p of params){
    const pid = sanitizeId(p);
    const block = document.createElement('div'); 
    block.className = 'card param-block';
    const qualityRange = QUALITY_RANGES[p] || `${p} `;

    let blockHTML = '<div class="param-title">' + p + '</div>' +
                   '<div class="quality-criteria"><strong>Quality Criteria (C Class):</strong> ' + qualityRange + '</div>';

    if (p === 'WQI') {
      blockHTML += '<div style="background:#fef3c7; padding:10px 14px; margin-bottom:14px; border-radius:8px; font-size:13px; color:#78350f; border-left:4px solid #eab308; line-height: 1.6;">' +
                  '<strong>🧮 Interactive WQI Calculator:</strong> Hover your mouse over any data point in the chart below. The detailed calculation breakdown will appear in the panel below the chart, showing formulas, sub-indices, weights, and contributions for pH, BOD, and DO parameters.' +
                  '</div>';
    }

   blockHTML += '<div id="time_' + pid + '" style="height:800px; margin-bottom:18px; border: 3px solid #cbd5e1; border-radius: 10px; padding: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08);"></div>';

    // Add breakdown panel and comparison tool for WQI
    if (p === 'WQI') {
      blockHTML += '<div id="wqi_breakdown_panel" class="wqi-breakdown-panel" style="display:none;"></div>';
      
      // Add WQI Comparison Tool
      blockHTML += `
        <div class="comparison-tool">
          <div class="comparison-header">
            <span>📊 WQI Change Analysis - Compare Two Data Points</span>
            <button class="comparison-collapse-btn" onclick="toggleComparisonCollapse()">
              <span class="comparison-collapse-icon">▼</span> Hide
            </button>
          </div>
          
          <div class="comparison-content">
            <div class="comparison-selectors">
              <div class="point-selector">
                <h4>📍 Point 1 (Earlier)</h4>
                <select id="compare_point1_location">
                  <option value="">Select Location...</option>
                </select>
                <select id="compare_point1_year">
                  <option value="">Select Year...</option>
                </select>
                <select id="compare_point1_month">
                  <option value="">Select Month...</option>
                </select>
                <div class="point-info" id="point1_info">
                  <div class="label">Select a data point above</div>
                </div>
              </div>
              
              <div class="point-selector">
                <h4>📍 Point 2 (Later)</h4>
                <select id="compare_point2_location">
                  <option value="">Select Location...</option>
                </select>
                <select id="compare_point2_year">
                  <option value="">Select Year...</option>
                </select>
                <select id="compare_point2_month">
                  <option value="">Select Month...</option>
                </select>
                <div class="point-info" id="point2_info">
                  <div class="label">Select a data point above</div>
                </div>
              </div>
            </div>
            
            <button id="compareBtn" class="compare-btn" disabled>
              🔍 Compare & Analyze WQI Change
            </button>
            
            <div id="comparisonResults" class="comparison-results"></div>
          </div>
        </div>
      `;
    }

    blockHTML += '<div id="bar_' + pid + '" style="height:320px; margin-top:10px;"></div>';

    block.innerHTML = blockHTML;
    fragment.appendChild(block);
    blocks.push({ p, pid });
}
     
    container.appendChild(fragment);

    requestAnimationFrame(()=>{
        if (hasWQI) {
            try { renderWQIYearlyAvg('wqi_yearly', rows); }
            catch(err) { console.error('Error rendering WQI yearly chart', err); }
        }

        for(const pb of blocks){
            try{
                renderTimeSeriesPerLocation('time_' + pb.pid, rows, pb.p);
                renderBarAvg('bar_' + pb.pid, rows, pb.p);
            }catch(err){ console.error('Error rendering param', pb.p, err); }
        }
    });
  }

  function filterData(){
    const selectedLocs = getTomValues(tomLoc);
    const selectedMonths = getTomValues(tomMonth);
    const selectedYears = getTomValues(tomYear);
    const selectedParams = getTomValues(tomParam);

    let rows = (DATA||[]).slice();

    if(selectedLocs.length) rows = rows.filter(r => r.Location && selectedLocs.includes(String(r.Location)));
    if(selectedMonths.length) rows = rows.filter(r => r.Month && selectedMonths.includes(String(r.Month)));
    if(selectedYears.length) rows = rows.filter(r => r.Year && selectedYears.includes(String(r.Year)));

    const chosenParams = selectedParams.length ? selectedParams : (PARAMS.length ? [PARAMS[0]] : []);
    return { rows, chosenParams };
  }

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
    tomLoc.clear(); tomMonth.clear(); tomYear.clear(); tomParam.clear(); preferDefaultParam(); scheduleRender();
  });
  document.getElementById('applyReset').addEventListener('click', function(){
    tomLoc.clear(); tomMonth.clear(); tomYear.clear(); tomParam.clear(); preferDefaultParam(); scheduleRender();
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
  document.getElementById('selectAllYears').addEventListener('click', ()=>{ selectAllTomBulk(tomYear, YEARS); scheduleRender(); });
  document.getElementById('clearYears').addEventListener('click', ()=>{ clearTomBulk(tomYear); scheduleRender(); });
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
    
    // Initialize comparison tool after WQI charts are rendered
    setTimeout(() => {
      if (chosenParams.includes('WQI')) {
        initializeComparisonTool();
      }
    }, 300);
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
  tomYear.on('change', ()=> scheduleRender());
  tomParam.on('change', ()=> scheduleRender());
  document.getElementById('monthlyAvgToggle').addEventListener('change', ()=> scheduleRender());
 
  let selectedPoint1 = null;
  let selectedPoint2 = null;

  function initializeComparisonTool() {
  console.log('Initializing WQI Comparison Tool...');
  
  // Check if comparison tool exists in DOM
  const point1Location = document.getElementById('compare_point1_location');
  if (!point1Location) {
    console.log('Comparison tool not in DOM yet, will retry...');
    return;
  }
  
  // Populate dropdowns with data
  const locations = LOCS;
  const years = YEARS;
  const months = MONTHS;
  
  populateComparisonDropdown('compare_point1_location', locations);
  populateComparisonDropdown('compare_point2_location', locations);
  populateComparisonDropdown('compare_point1_year', years);
  populateComparisonDropdown('compare_point2_year', years);
  populateComparisonDropdown('compare_point1_month', months);
  populateComparisonDropdown('compare_point2_month', months);
  
  // Add event listeners for Point 1
  document.getElementById('compare_point1_location').addEventListener('change', () => updateComparisonPoint(1));
  document.getElementById('compare_point1_year').addEventListener('change', () => updateComparisonPoint(1));
  document.getElementById('compare_point1_month').addEventListener('change', () => updateComparisonPoint(1));
  
  // Add event listeners for Point 2
  document.getElementById('compare_point2_location').addEventListener('change', () => updateComparisonPoint(2));
  document.getElementById('compare_point2_year').addEventListener('change', () => updateComparisonPoint(2));
  document.getElementById('compare_point2_month').addEventListener('change', () => updateComparisonPoint(2));
  
  // Add compare button listener
  document.getElementById('compareBtn').addEventListener('click', performWQIComparison);
  
  console.log('WQI Comparison Tool initialized successfully!');
}
    
    function populateComparisonDropdown(id, values) {
    const select = document.getElementById(id);
    const firstOption = select.querySelector('option');
    select.innerHTML = '';
    select.appendChild(firstOption);
    
    values.forEach(val => {
      const option = document.createElement('option');
      option.value = val;
      option.textContent = val;
      select.appendChild(option);
    });
  }

  function updateComparisonPoint(pointNum) {
    const location = document.getElementById(`compare_point${pointNum}_location`).value;
    const year = document.getElementById(`compare_point${pointNum}_year`).value;
    const month = document.getElementById(`compare_point${pointNum}_month`).value;
    
    if (!location || !year || !month) {
      if (pointNum === 1) selectedPoint1 = null;
      else selectedPoint2 = null;
      updateCompareButtonState();
      return;
    }
    
    // Find matching data point in DATA array
    const dataPoint = DATA.find(row => 
      row.Location === location && 
      row.Year == year && 
      row.Month === month
    );
    
    if (dataPoint) {
      // Extract pH, BOD, DO columns
      const phCol = Object.keys(dataPoint).find(k => {
        const lower = k.toLowerCase();
        return lower.includes('ph') && !lower.includes('phosph');
      });
      const bodCol = Object.keys(dataPoint).find(k => k.toLowerCase().includes('bod'));
      const doCol = Object.keys(dataPoint).find(k => k.toLowerCase().includes('do_mg'));
      
      // Check if any value is Nil in the source data
const pH_raw = dataPoint[phCol];
const BOD_raw = dataPoint[bodCol];
const DO_raw = dataPoint[doCol];

const pH_isNil = isNilValue(pH_raw);
const BOD_isNil = isNilValue(BOD_raw);
const DO_isNil = isNilValue(DO_raw);

if (pH_isNil || BOD_isNil || DO_isNil) {
  const missingParams = [];
  if (pH_isNil) missingParams.push('pH');
  if (BOD_isNil) missingParams.push('BOD');
  if (DO_isNil) missingParams.push('DO');
  
  const infoDiv = document.getElementById(`point${pointNum}_info`);
  infoDiv.innerHTML = `
    <div class="label" style="color:#dc2626;">Data Incomplete</div>
    <div style="font-size:12px; color:#991b1b; margin-top:8px;">
      ⚠️ Nil values: ${missingParams.join(', ')}<br>
      WQI: N/A
    </div>
  `;
  
  if (pointNum === 1) selectedPoint1 = null;
  else selectedPoint2 = null;
  updateCompareButtonState();
  return;
}

// Now get the numeric values (we know they're not Nil)
const pH = getDisplayValue(pH_raw);
const BOD = getDisplayValue(BOD_raw);
const DO = getDisplayValue(DO_raw);
const WQI = getWQIValue(dataPoint.WQI);
      
      if (pH !== null && BOD !== null && DO !== null) {
        const breakdown = calculateWQIBreakdown(pH, BOD, DO);
        
        const point = {
          location, year, month,
          pH, BOD, DO, WQI,
          breakdown,
          date: dataPoint.Date
        };
        
        if (pointNum === 1) selectedPoint1 = point;
        else selectedPoint2 = point;
        
        // Update display
        const infoDiv = document.getElementById(`point${pointNum}_info`);
        infoDiv.innerHTML = `
          <div class="label">WQI Value</div>
          <div class="value">${breakdown.WQI.toFixed(2)}</div>
          <div style="margin-top:8px; font-size:11px; color:#64748b;">
            📌 pH: ${pH.toFixed(2)} | BOD: ${BOD.toFixed(2)} | DO: ${DO.toFixed(2)}
          </div>
        `;
        
        console.log(`Point ${pointNum} selected:`, point);
      } else {
        alert(`⚠️ Missing required parameters (pH, BOD, DO) for ${location} in ${month} ${year}`);
        if (pointNum === 1) selectedPoint1 = null;
        else selectedPoint2 = null;
      }
    } else {
      alert(`⚠️ No data found for ${location} in ${month} ${year}`);
      if (pointNum === 1) selectedPoint1 = null;
      else selectedPoint2 = null;
    }
    
    updateCompareButtonState();
  }

  function updateCompareButtonState() {
    const btn = document.getElementById('compareBtn');
    btn.disabled = !selectedPoint1 || !selectedPoint2;
    
    if (selectedPoint1 && selectedPoint2) {
      btn.textContent = '🔍 Compare & Analyze WQI Change';
    } else {
      btn.textContent = '🔍 Select both points to compare';
    }
  }
function calculateStreeterPhelps(BOD1, DO1, BOD2, DO2, tempDays = 1) {
    // Streeter-Phelps Model Parameters
    const k1 = 0.1;  // Deoxygenation rate constant (day^-1) - typical for polluted rivers
    const k2 = 0.4;  // Reaeration rate constant (day^-1) - typical for flowing rivers
    const DOsat = 9.0;  // Saturated DO at 20°C (mg/L)
    
    // Initial deficit at Point 1
    const D1 = DOsat - DO1;
    
    // BOD remaining after time t
    const Lt = BOD1 * Math.exp(-k1 * tempDays);
    
    // Calculate deficit at Point 2 using Streeter-Phelps
    const Dt = (k1 * BOD1 / (k2 - k1)) * (Math.exp(-k1 * tempDays) - Math.exp(-k2 * tempDays)) + D1 * Math.exp(-k2 * tempDays);
    
    // Predicted DO at Point 2
    const DO2_predicted = DOsat - Dt;
    
    // Critical deficit and time
    const tc = (1 / (k2 - k1)) * Math.log((k2 / k1) * (1 - ((k2 - k1) * D1) / (k1 * BOD1)));
    const Dc = (k1 * BOD1 / k2) * Math.exp(-k1 * tc);
    
    return {
      k1, k2, DOsat,
      initialDeficit: D1,
      currentDeficit: DOsat - DO2,
      predictedDeficit: Dt,
      predictedDO: DO2_predicted,
      actualDO: DO2,
      criticalTime: tc > 0 ? tc : null,
      criticalDeficit: tc > 0 ? Dc : null,
      BODremaining: Lt,
      deoxygenationRate: k1 * BOD1,
      rearationRate: k2 * D1
    };
  }
  function performWQIComparison() {
    if (!selectedPoint1 || !selectedPoint2) return;
    
    const p1 = selectedPoint1;
    const p2 = selectedPoint2;
    
    console.log('Performing comparison between:', p1, p2);
    
    // Calculate WQI change
    const wqiChange = p2.breakdown.WQI - p1.breakdown.WQI;
    const wqiChangePercent = ((wqiChange / p1.breakdown.WQI) * 100);
    
    // Calculate parameter contributions to change
    const contributions = [];
    
    p1.breakdown.parameters.forEach((param1, idx) => {
      const param2 = p2.breakdown.parameters[idx];
      const contributionChange = param2.contribution - param1.contribution;
      const percentOfTotalChange = (contributionChange / Math.abs(wqiChange)) * 100;
      
      contributions.push({
        name: param1.name,
        point1Value: param1.measured,
        point2Value: param2.measured,
        point1Contribution: param1.contribution,
        point2Contribution: param2.contribution,
        contributionChange: contributionChange,
        percentOfChange: Math.abs(percentOfTotalChange),
        valueChange: param2.measured - param1.measured,
        valueChangePercent: ((param2.measured - param1.measured) / param1.measured) * 100
      });
    });
    
    // Sort by impact on change (descending)
    contributions.sort((a, b) => Math.abs(b.percentOfChange) - Math.abs(a.percentOfChange));
    
    console.log('Contributions calculated:', contributions);
    
    // Render results
    renderWQIComparisonResults(p1, p2, wqiChange, wqiChangePercent, contributions);
  }

  function renderWQIComparisonResults(p1, p2, wqiChange, wqiChangePercent, contributions) {
    const resultsDiv = document.getElementById('comparisonResults');
    const changeDirection = wqiChange > 0 ? 'negative' : 'positive';
    const changeVerb = wqiChange > 0 ? 'increased (worsened)' : 'decreased (improved)';
    const changeIcon = wqiChange > 0 ? '📈' : '📉';
    // Calculate Streeter-Phelps for DO analysis
    const spModel = calculateStreeterPhelps(p1.BOD, p1.DO, p2.BOD, p2.DO);
    let html = `
      <div class="results-header">
        ${changeIcon} WQI Comparison Results
      </div>
      
      <div class="wqi-change-summary">
        <div class="change-card">
          <div class="label">Point 1 (Earlier)</div>
          <div class="value">${p1.breakdown.WQI.toFixed(2)}</div>
          <div style="font-size:11px; color:#64748b; margin-top:4px;">
            📅 ${p1.month} ${p1.year}<br>📍 ${p1.location}
          </div>
        </div>
        
        <div class="change-card ${changeDirection}">
          <div class="label">WQI Change</div>
          <div class="value">${wqiChange > 0 ? '+' : ''}${wqiChange.toFixed(2)}</div>
          <div style="font-size:11px; margin-top:4px;">
            ${wqiChangePercent > 0 ? '+' : ''}${wqiChangePercent.toFixed(1)}%
          </div>
        </div>
        
        <div class="change-card">
          <div class="label">Point 2 (Later)</div>
          <div class="value">${p2.breakdown.WQI.toFixed(2)}</div>
          <div style="font-size:11px; color:#64748b; margin-top:4px;">
            📅 ${p2.month} ${p2.year}<br>📍 ${p2.location}
          </div>
        </div>
      </div>
      
      <div class="parameter-contributions">
        <h4 style="margin:0 0 16px 0; color:#0c4a6e; font-size:15px;">
          🔍 Parameter Contributions to WQI Change
        </h4>
    `;
    contributions.forEach((contrib, idx) => {
      const sign = contrib.valueChange > 0 ? '+' : '';
      const arrowIcon = contrib.valueChange > 0 ? '↗️' : '↘️';
      
      html += `
        <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 14px; padding: 12px; background: white; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
          <div style="font-size: 24px; font-weight: 700; color: #0284c7; min-width: 50px; text-align: center;">#${idx + 1}</div>
          
          <div style="min-width: 200px;">
            <div style="font-weight: 700; color: #0f172a; font-size: 16px; margin-bottom: 4px;">${contrib.name}</div>
            <div style="font-size: 12px; color: #64748b; line-height: 1.5; white-space: nowrap;">
              ${arrowIcon} ${contrib.point1Value.toFixed(2)} → ${contrib.point2Value.toFixed(2)} (${sign}${contrib.valueChange.toFixed(2)}, ${sign}${contrib.valueChangePercent.toFixed(1)}%)
            </div>
          </div>
          
          <div style="flex: 1;">
            <div style="display: inline-block; padding: 10px 20px; background: #e0f2fe; border: 2px solid #0284c7; border-radius: 8px; font-size: 14px; font-weight: 700; color: #0284c7;">
              ${contrib.percentOfChange.toFixed(1)}% of change
            </div>
          </div>
        </div>
      `;
    });
    
    html += '</div>';
    
    // ========================================
    // STREETER-PHELPS ANALYSIS SECTION
    // ========================================
    html += `
      <div class="wqi-calculation-section" style="background: linear-gradient(135deg, #e0f2fe, #dbeafe); border: 2px solid #0284c7; margin-top: 20px;">
        <div class="calc-section-title" style="color: #0c4a6e; font-size: 16px;">
          🌊 Streeter-Phelps Dissolved Oxygen Model
        </div>
        
        <div style="background: white; padding: 14px; border-radius: 8px; margin-bottom: 12px;">
          <div style="font-size: 13px; color: #475569; margin-bottom: 12px; line-height: 1.6;">
            The Streeter-Phelps equation models how dissolved oxygen (DO) changes due to the competing processes of 
            <strong>deoxygenation</strong> (oxygen consumption from BOD) and <strong>reaeration</strong> (oxygen absorption from atmosphere).
          </div>
          
          <div class="formula-display" style="background: #f8fafc; padding: 12px; border-radius: 6px; margin: 12px 0;">
  <strong style="font-size: 15px;">Streeter-Phelps Equation:</strong><br>
  <span style="font-size: 15px;">D<sub>t</sub> = (k₁ × L₀)/(k₂ - k₁) × [e<sup>-k₁t</sup> - e<sup>-k₂t</sup>] + D₀ × e<sup>-k₂t</sup></span><br><br>
  <span style="font-size: 14px; color: #64748b;">
    where: D<sub>t</sub> = DO deficit at time t, k₁ = deoxygenation rate, k₂ = reaeration rate, L₀ = initial BOD
  </span>
</div>
        </div>
        
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px;">
          <div style="background: white; padding: 12px; border-radius: 8px;">
            <div style="font-size: 11px; color: #64748b; font-weight: 600; margin-bottom: 6px;">MODEL PARAMETERS</div>
            <div style="font-size: 13px; line-height: 1.8;">
              <strong>k₁</strong> (Deoxygenation): ${spModel.k1.toFixed(2)} day⁻¹<br>
              <strong>k₂</strong> (Reaeration): ${spModel.k2.toFixed(2)} day⁻¹<br>
              <strong>DO<sub>sat</sub></strong>: ${spModel.DOsat.toFixed(1)} mg/L
            </div>
          </div>
          
          <div style="background: white; padding: 12px; border-radius: 8px;">
            <div style="font-size: 11px; color: #64748b; font-weight: 600; margin-bottom: 6px;">PROCESS RATES</div>
            <div style="font-size: 13px; line-height: 1.8;">
              <strong>Deoxygenation Rate:</strong> ${spModel.deoxygenationRate.toFixed(3)} mg/L/day<br>
              <strong>Reaeration Rate:</strong> ${spModel.rearationRate.toFixed(3)} mg/L/day<br>
              <strong>Net Effect:</strong> ${(spModel.rearationRate - spModel.deoxygenationRate).toFixed(3)} mg/L/day
            </div>
          </div>
        </div>
        
        <div style="background: white; padding: 14px; border-radius: 8px; margin-bottom: 12px;">
          <div style="font-size: 13px; font-weight: 600; color: #0c4a6e; margin-bottom: 10px;">
            📊 DO Deficit Analysis
          </div>
          <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;">
            <div style="background: #f0f9ff; padding: 10px; border-radius: 6px; border-left: 3px solid #0284c7;">
              <div style="font-size: 11px; color: #64748b;">Initial Deficit (Point 1)</div>
              <div style="font-size: 18px; font-weight: 700; color: #0284c7;">${spModel.initialDeficit.toFixed(2)} mg/L</div>
            </div>
            <div style="background: #fef3c7; padding: 10px; border-radius: 6px; border-left: 3px solid #f59e0b;">
              <div style="font-size: 11px; color: #64748b;">Predicted Deficit (Point 2)</div>
              <div style="font-size: 18px; font-weight: 700; color: #f59e0b;">${spModel.predictedDeficit.toFixed(2)} mg/L</div>
            </div>
            <div style="background: ${Math.abs(spModel.currentDeficit - spModel.predictedDeficit) > 1 ? '#fee2e2' : '#ecfdf5'}; padding: 10px; border-radius: 6px; border-left: 3px solid ${Math.abs(spModel.currentDeficit - spModel.predictedDeficit) > 1 ? '#ef4444' : '#10b981'};">
              <div style="font-size: 11px; color: #64748b;">Actual Deficit (Point 2)</div>
              <div style="font-size: 18px; font-weight: 700; color: ${Math.abs(spModel.currentDeficit - spModel.predictedDeficit) > 1 ? '#ef4444' : '#10b981'};">${spModel.currentDeficit.toFixed(2)} mg/L</div>
            </div>
          </div>
        </div>
        
        ${spModel.criticalTime && spModel.criticalTime > 0 && spModel.criticalTime < 10 ? `
        <div style="background: #fef2f2; padding: 12px; border-radius: 8px; border-left: 4px solid #ef4444; margin-bottom: 12px;">
          <div style="font-size: 13px; font-weight: 600; color: #991b1b; margin-bottom: 6px;">
            ⚠️ Critical Oxygen Sag Point
          </div>
          <div style="font-size: 12px; color: #7f1d1d; line-height: 1.6;">
            <strong>Critical Time:</strong> ${spModel.criticalTime.toFixed(2)} days<br>
            <strong>Maximum Deficit:</strong> ${spModel.criticalDeficit.toFixed(2)} mg/L<br>
            <strong>Minimum DO:</strong> ${(spModel.DOsat - spModel.criticalDeficit).toFixed(2)} mg/L
          </div>
        </div>
        ` : ''}
        
        <div class="interpretation-box" style="background: linear-gradient(135deg, #e0f2fe, #dbeafe); border-color: #0284c7;">
          <strong>🔬 Streeter-Phelps Interpretation:</strong><br><br>
          
          <strong>Observed Changes:</strong><br>
          • DO: ${p1.DO.toFixed(2)} → ${p2.DO.toFixed(2)} mg/L (${p2.DO > p1.DO ? '+' : ''}${(p2.DO - p1.DO).toFixed(2)} mg/L)<br>
          • BOD: ${p1.BOD.toFixed(2)} → ${p2.BOD.toFixed(2)} mg/L (${p2.BOD > p1.BOD ? '+' : ''}${(p2.BOD - p1.BOD).toFixed(2)} mg/L)<br><br>
          
          <strong>Model Prediction vs Reality:</strong><br>
          The Streeter-Phelps model predicted DO of <strong>${spModel.predictedDO.toFixed(2)} mg/L</strong> at Point 2, 
          but actual measured DO is <strong>${spModel.actualDO.toFixed(2)} mg/L</strong> 
          (difference: <strong>${Math.abs(spModel.actualDO - spModel.predictedDO).toFixed(2)} mg/L</strong>).<br><br>
          
         ${(() => {
            const bodChange = p2.BOD - p1.BOD;
            const bodChangePercent = ((bodChange / p1.BOD) * 100);
            const doChange = p2.DO - p1.DO;
            
            if (bodChange > p1.BOD * 0.5) {
              return `<span style="color: #dc2626;">⚠️ <strong>BOD increased dramatically (${bodChangePercent.toFixed(0)}%)</strong> between measurement points<br><br>
              
              <strong>Why didn't DO increase despite positive net rates at both points?</strong><br><br>
              
              The Streeter-Phelps model calculates <strong>instantaneous rates at each measurement point</strong>, but doesn't account for 
              <strong>pollution added between the points</strong>. Here's what happened:<br><br>
              
              1️⃣ <strong>At Point 1:</strong> Water is recovering (net +${(spModel.rearationRate - spModel.deoxygenationRate).toFixed(3)} mg/L/day). 
              As this water flows downstream, DO <em>should</em> increase.<br><br>
              
              2️⃣ <strong>Between Points:</strong> <strong style="color:#991b1b;">NEW POLLUTION SOURCE</strong> added ${bodChange.toFixed(2)} mg/L of BOD. 
              This fresh organic load immediately consumed oxygen, offsetting any recovery from Point 1.<br><br>
              
              3️⃣ <strong>At Point 2:</strong> The "snapshot" rates show recovery potential (net +${((spModel.k2 * (spModel.DOsat - p2.DO)) - (spModel.k1 * p2.BOD)).toFixed(3)} mg/L/day), 
              but this only tells us what's happening <em>right now at Point 2</em> - it doesn't reflect the oxygen already consumed by the pollution spike.<br><br>
              
              <strong>Bottom Line:</strong> The oxygen consumed by the ${bodChange.toFixed(2)} mg/L BOD increase between points 
              <strong>canceled out</strong> the natural reaeration that occurred. Think of it as: the river was healing (+${(spModel.rearationRate - spModel.deoxygenationRate).toFixed(1)} mg/L/day at Point 1), 
              but then got a fresh wound (new pollution) that consumed all the healing progress.</span>`;
            }
            
            if (spModel.actualDO < spModel.predictedDO - 0.5) {
              return `<span style="color: #dc2626;">⚠️ <strong>Actual DO is significantly LOWER than predicted</strong> - This indicates:<br>
              • Additional oxygen-consuming pollutants not accounted for in the model<br>
              • Reaeration rate may be overestimated (actual k₂ < ${spModel.k2})<br>
              • Possible sediment oxygen demand or other oxygen sinks<br>
              • The river's self-purification capacity is insufficient</span>`;
            } else if (spModel.actualDO > spModel.predictedDO + 0.5) {
              return `<span style="color: #059669;">✓ <strong>Actual DO is HIGHER than predicted</strong> - This suggests:<br>
              • Stronger reaeration than modeled (actual k₂ > ${spModel.k2})<br>
              • Possible algal photosynthesis contributing oxygen<br>
              • Less oxygen consumption than expected<br>
              • River is recovering better than the model predicts</span>`;
            } else {
              return `<span style="color: #059669;">✓ <strong>Good model agreement</strong> - The Streeter-Phelps model accurately represents oxygen dynamics between these points.</span>`;
            }
          })()}<br><br>
          
          <strong>Process Analysis Comparison:</strong><br>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 8px;">
            <div style="background: #f0f9ff; padding: 10px; border-radius: 6px; border-left: 3px solid #0284c7;">
              <div style="font-weight: 600; margin-bottom: 6px;">📍 Point 1 Rates</div>
              • Deoxygenation: <strong>${spModel.deoxygenationRate.toFixed(3)} mg/L/day</strong><br>
              • Reaeration: <strong>${spModel.rearationRate.toFixed(3)} mg/L/day</strong><br>
              • Net: <strong>${(spModel.rearationRate - spModel.deoxygenationRate).toFixed(3)} mg/L/day</strong>
              ${spModel.rearationRate > spModel.deoxygenationRate ? ' ✓' : ' ✗'}
            </div>
            
            <div style="background: ${p2.BOD > p1.BOD ? '#fef2f2' : '#ecfdf5'}; padding: 10px; border-radius: 6px; border-left: 3px solid ${p2.BOD > p1.BOD ? '#ef4444' : '#10b981'};">
              <div style="font-weight: 600; margin-bottom: 6px;">📍 Point 2 Rates (calculated)</div>
              • Deoxygenation: <strong>${(spModel.k1 * p2.BOD).toFixed(3)} mg/L/day</strong><br>
              • Reaeration: <strong>${(spModel.k2 * (spModel.DOsat - p2.DO)).toFixed(3)} mg/L/day</strong><br>
              • Net: <strong>${((spModel.k2 * (spModel.DOsat - p2.DO)) - (spModel.k1 * p2.BOD)).toFixed(3)} mg/L/day</strong>
              ${(() => {
  const p2Net = (spModel.k2 * (spModel.DOsat - p2.DO)) - (spModel.k1 * p2.BOD);
  const actualDOChange = p2.DO - p1.DO;
  if (p2Net > 0.1 && actualDOChange > 0) return ' ✓';
  if (p2Net < -0.1) return ' ✗';
  if (p2Net > 0 && actualDOChange <= 0) return ' ⚠️';
  return '';
})()}
            </div>
          </div>
          <br>
          ${p2.BOD > p1.BOD * 1.5 
            ? `<span style="color: #dc2626;"><strong>⚠️ Critical Finding:</strong> Deoxygenation rate increased by 
               <strong>${(((spModel.k1 * p2.BOD) - spModel.deoxygenationRate) / spModel.deoxygenationRate * 100).toFixed(0)}%</strong> 
               at Point 2, overwhelming the reaeration capacity. This confirms new pollution entered between measurement points.</span><br>`
            : ''
          }
        </div>
      </div>
    `;
    
    // Interpretation
    const mainContributor = contributions[0];
    const mainContribSign = mainContributor.valueChange > 0 ? 'increased' : 'decreased';
    const mainContribImpact = mainContributor.valueChange > 0 ? 'worsening' : 'improving';
    
    html += `
      <div class="interpretation-text">
        <strong>💡 Key Findings:</strong><br><br>
        Between <strong>${p1.month} ${p1.year}</strong> and <strong>${p2.month} ${p2.year}</strong> ${p1.location === p2.location ? 'at <strong>' + p1.location + '</strong>' : 'comparing <strong>' + p1.location + '</strong> and <strong>' + p2.location + '</strong>'}, 
        the WQI ${changeVerb} by <strong>${Math.abs(wqiChange).toFixed(2)} points (${Math.abs(wqiChangePercent).toFixed(1)}%)</strong>.<br><br>
        
        <strong>${mainContributor.name}</strong> was the primary driver of this change, accounting for 
        <strong>${mainContributor.percentOfChange.toFixed(1)}%</strong> of the total WQI change. 
        ${mainContributor.name} ${mainContribSign} from <strong>${mainContributor.point1Value.toFixed(2)}</strong> to <strong>${mainContributor.point2Value.toFixed(2)}</strong>, 
        ${mainContribImpact} water quality.
        ${contributions.length > 1 ? `<br><br>The second most significant factor was <strong>${contributions[1].name}</strong>, 
        contributing <strong>${contributions[1].percentOfChange.toFixed(1)}%</strong> to the change.` : ''}
      </div>
    `;
    
    resultsDiv.innerHTML = html;
    resultsDiv.style.display = 'block';
    
    // Scroll to results smoothly
    resultsDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    
    console.log('Comparison results rendered successfully!');
  }

   // ==========================================
  // COMPARISON COLLAPSE TOGGLE
  // ==========================================
  let isComparisonCollapsed = false;

  window.toggleComparisonCollapse = function() {
    isComparisonCollapsed = !isComparisonCollapsed;
    const content = document.querySelector('.comparison-content');
    const icon = document.querySelector('.comparison-collapse-icon');
    const btn = document.querySelector('.comparison-collapse-btn');
    
    if (content && icon && btn) {
      if (isComparisonCollapsed) {
        content.classList.add('collapsed');
        icon.classList.add('collapsed');
        btn.innerHTML = '<span class="comparison-collapse-icon collapsed">▼</span> Show';
      } else {
        content.classList.remove('collapsed');
        icon.classList.remove('collapsed');
        btn.innerHTML = '<span class="comparison-collapse-icon">▼</span> Hide';
      }
    }
  };

  // Initialize comparison tool after charts are rendered
  setTimeout(() => {
    initializeComparisonTool();
    setTimeout(initializeComparisonTool, 1000);
  }, 500);

    scheduleRender(250);
  window.refreshDashboard = function(){ scheduleRender(0); };
});
</script>
</body>
</html>"""


def main():
    """Main execution function"""
    try:
        logger.info("Starting Yamuna Water Quality Dashboard Generator with Enhanced WQI Calculator")

        processor = DataProcessor()
        excel_path = processor.locate_input_file()
        logger.info(f"Processing file: {excel_path}")

        df = processor.read_excel_file(excel_path)
        logger.info(f"Read {len(df)} rows from Excel")

        df = processor.normalize_dataframe(df)
        logger.info(f"Normalized data: {len(df)} rows remaining")

        if df.empty:
            logger.error("No usable data found in Excel file")
            sys.exit(1)

        locations, months, years = processor.extract_metadata(df)
        logger.info(f"Found {len(locations)} locations, {len(years)} years")

        numeric_params = processor.get_numeric_parameters(df)
        logger.info(f"Found {len(numeric_params)} numeric parameters: {numeric_params}")

        if not numeric_params:
            logger.error("No numeric parameters found")
            sys.exit(1)

        has_coords, location_coords = processor.check_coordinates(df)
        if has_coords:
            logger.info(f"Found coordinates for {len(location_coords)} locations")
        else:
            logger.warning("No coordinate data found - map view will be disabled")

        data_rows = processor.prepare_json_data(df)

        output_path = Path(__file__).resolve().parent / OUTPUT_HTML
        HTMLGenerator.generate_dashboard(
            data_rows, months, numeric_params, locations,
            years, location_coords, output_path
        )

        try:
            webbrowser.open(output_path.resolve().as_uri())
            logger.info("Dashboard opened in browser")
        except Exception as e:
            logger.warning(f"Could not open browser: {e}")
            logger.info(f"Please open manually: {output_path}")

        logger.info("Enhanced WQI Calculator Dashboard generation complete!")
        logger.info("Hover over WQI data points to see detailed calculation breakdown!")

    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
