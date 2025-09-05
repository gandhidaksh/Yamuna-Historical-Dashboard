# yamuna_dashboard.py
"""
Yamuna Plotly Dashboard (single-file)
- Place 'Yamuna Report V3.0.xlsx' next to this script, or pick it in the file dialog.
- Run: python yamuna_dashboard.py
- The script writes 'yamuna_dashboard.html' next to the script and attempts to open it in your browser.
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

    # Coerce numeric parameters where possible (non-essential)
    essential = {"Year", "Month", "Location", "Date", "Month_Num"}
    for c in [c for c in df.columns if c not in essential]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Drop rows with no Date or Location
    if "Date" in df.columns and "Location" in df.columns:
        df = df.dropna(subset=["Date", "Location"], how="any")

    # Drop rows with no numeric value at all (but keep those that have at least one numeric param)
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    if len(numeric_cols):
        df = df[df[numeric_cols].notna().any(axis=1)]

    df = df.reset_index(drop=True)
    return df


# ----------------------- Data -> JSON rows for embedding -----------------------
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
    essential = {"Year", "Month", "Location", "Date", "Month_Num"}
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


# ----------------------- HTML builder -----------------------
def build_html(data_rows, months, params, locations, years, out_path: Path):
    # helper to safely dump JSON and avoid closing script tag issues
    def dump_safe(obj):
        js = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        return js.replace("</script>", "<\\/script>")

    data_json = dump_safe(data_rows)
    months_json = dump_safe(months)
    params_json = dump_safe(params)
    locs_json = dump_safe(locations)
    years_json = dump_safe(years)

    # Full HTML template - replace placeholders below
    html_template = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Yamuna Water Quality - Enhanced Dashboard</title>

<link href="https://cdn.jsdelivr.net/npm/tom-select/dist/css/tom-select.default.min.css" rel="stylesheet" />
<link href="https://cdnjs.cloudflare.com/ajax/libs/noUiSlider/14.6.4/nouislider.min.css" rel="stylesheet" />

<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/tom-select/dist/js/tom-select.complete.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/noUiSlider/14.6.4/nouislider.min.js"></script>

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
.charts-grid{display:flex; flex-direction:column; gap:12px;}
.param-title{font-weight:700; margin-bottom:8px;}
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

    <div id="chartsContainer" class="charts-grid"></div>

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
  // embedded dataset and lists
  const DATA = __DATA_JSON__;
  const MONTHS = __MONTHS_JSON__;
  const PARAMS = __PARAMS_JSON__;
  const LOCS = __LOCS_JSON__;
  const YEARS = __YEARS_JSON__;

  // Standards (bands) - WQI, pH, DO, BOD, etc.
  const STANDARDS = {
    "WQI":[
      {min:91,max:100,color:'#059669',label:'Excellent'},
      {min:71,max:90,color:'#0891b2',label:'Good'},
      {min:51,max:70,color:'#f59e0b',label:'Fair'},
      {min:26,max:50,color:'#ef4444',label:'Poor'},
      {min:0,max:25,color:'#7c2d12',label:'Very Poor'}
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

  // small helpers
  function safeAddOptions(selectEl, arr) { selectEl.innerHTML=''; for(const v of arr){ const opt=document.createElement('option'); opt.value=v; opt.text=v; selectEl.appendChild(opt);} }
  function getTomValues(ts) { try{ const v = ts.getValue(); return Array.isArray(v)? v : (v? [v] : []); } catch(e){ return []; } }
  function sanitizeId(s) { return String(s).replace(/[^a-z0-9]/gi,'_'); }
  function periodMonthKey(d) { // returns YYYY-MM for grouping
    if(!d) return null; const dt = new Date(d); if(isNaN(dt)) return null;
    const y = dt.getFullYear(); const m = dt.getMonth()+1; return `${y}-${String(m).padStart(2,'0')}`; 
  }

  // populate selects
  safeAddOptions(document.getElementById('selLocation'), LOCS);
  safeAddOptions(document.getElementById('selMonth'), MONTHS);
  safeAddOptions(document.getElementById('selParam'), PARAMS);

  // init TomSelect
  const tomLoc = new TomSelect('#selLocation', { plugins:['remove_button'], create:false, placeholder:'Choose locations...', hideSelected:true });
  const tomMonth = new TomSelect('#selMonth', { plugins:['remove_button'], create:false, placeholder:'Choose months...', hideSelected:true });
  const tomParam = new TomSelect('#selParam', { plugins:['remove_button'], create:false, placeholder:'Choose parameters...', hideSelected:true });

  // year slider
  const yearMinEl = document.getElementById('yearMin'), yearMaxEl = document.getElementById('yearMax');
  const yearsSorted = (YEARS||[]).slice().sort((a,b)=>a-b);
  const yMin = yearsSorted.length? yearsSorted[0] : new Date().getFullYear();
  const yMax = yearsSorted.length? yearsSorted[yearsSorted.length-1] : new Date().getFullYear();
  const sliderDiv = document.createElement('div'); document.getElementById('yearSlider').appendChild(sliderDiv);
  noUiSlider.create(sliderDiv, { start:[yMin,yMax], connect:true, step:1, range:{min:yMin,max:yMax}, tooltips:[true,true], format:{ to: v => Math.round(v), from: v => Number(v) } });
  sliderDiv.noUiSlider.on('update', function(vals){ yearMinEl.textContent=Math.round(vals[0]); yearMaxEl.textContent=Math.round(vals[1]); });

  // prefer WQI default if present
  function preferDefaultParam(){
    if(PARAMS && PARAMS.length){
      const p = PARAMS.indexOf('WQI') !== -1 ? 'WQI' : PARAMS[0];
      tomParam.setValue([p]);
    }
  }
  preferDefaultParam();

  // sidebar hide/show
  const sidebar = document.getElementById('sidebar');
  const hideBtn = document.getElementById('hideBtn');
  const floatingToggle = document.getElementById('sidebarToggle');
  const mainEl = document.querySelector('.main');

  function setSidebarVisible(visible){
    if(visible){
      sidebar.classList.remove('hidden'); floatingToggle.classList.add('hidden'); mainEl.classList.remove('fullwidth');
    } else {
      sidebar.classList.add('hidden'); floatingToggle.classList.remove('hidden'); mainEl.classList.add('fullwidth');
    }
    // resize plots after animation
    setTimeout(()=>{ document.querySelectorAll('.plotly-graph-div').forEach(g=>{ try{ Plotly.Plots.resize(g);}catch(e){} }); }, 150);
  }
  setSidebarVisible(true);
  hideBtn.addEventListener('click', ()=> setSidebarVisible(false));
  floatingToggle.addEventListener('click', ()=> setSidebarVisible(true));
  // reset & clear
  document.getElementById('resetBtn').addEventListener('click', function(){
    tomLoc.clear(); tomMonth.clear(); tomParam.clear(); preferDefaultParam(); sliderDiv.noUiSlider.set([yMin,yMax]); scheduleRender();
  });
  document.getElementById('applyReset').addEventListener('click', function(){
    tomLoc.clear(); tomMonth.clear(); tomParam.clear(); preferDefaultParam(); sliderDiv.noUiSlider.set([yMin,yMax]); scheduleRender();
  });

  // select all / clear buttons
  function selectAllTomBulk(ts, arr){
    try{
      const vals = (arr||[]).map(v => String(v));
      if(typeof ts.setValue === 'function') ts.setValue(vals);
      else { ts.clear(); for(const v of vals) ts.addItem(v); }
    } catch(e){ console.warn('selectAllTomBulk error', e); }
  }
  function clearTomBulk(ts){ try{ if(typeof ts.clear === 'function') ts.clear(); else if(typeof ts.setValue === 'function') ts.setValue([]); }catch(e){} }
  document.getElementById('selectAllMonths').addEventListener('click', ()=>{ selectAllTomBulk(tomMonth, MONTHS); scheduleRender(); });
  document.getElementById('clearMonths').addEventListener('click', ()=>{ clearTomBulk(tomMonth); scheduleRender(); });
  document.getElementById('selectAllParams').addEventListener('click', ()=>{ selectAllTomBulk(tomParam, PARAMS); scheduleRender(); });
  document.getElementById('clearParams').addEventListener('click', ()=>{ clearTomBulk(tomParam); preferDefaultParam(); scheduleRender(); });

  // CSV download
  function downloadCSV(rows){
    if(!rows || !rows.length){ alert("No rows to download."); return; }
    const keys = Object.keys(rows[0]);
    const csvRows = [keys.join(",")];
    for(const r of rows){
      const line = keys.map(k=> { const v = r[k] === null || r[k] === undefined ? "" : String(r[k]).replace(/"/g,'""'); return `"${v}"`; }).join(",");
      csvRows.push(line);
    }
    const blob = new Blob([csvRows.join("\n")], {type:'text/csv;charset=utf-8;'});
    const url = URL.createObjectURL(blob); const a=document.createElement('a'); a.href=url; a.download='yamuna_filtered.csv'; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  }
  document.getElementById('downloadCsv').addEventListener('click', function(){ const {rows} = filterData(); downloadCSV(rows); });

  // Filtering function
  function filterData(){
    const selectedLocs = getTomValues(tomLoc);
    const selectedMonths = getTomValues(tomMonth);
    const selectedParams = getTomValues(tomParam);
    const yrs = sliderDiv.noUiSlider.get().map(v=> Math.round(Number(v))); const [selYmin, selYmax] = yrs;
    let rows = (DATA||[]).slice();
    if(selectedLocs.length) rows = rows.filter(r => r.Location && selectedLocs.includes(String(r.Location)));
    if(selectedMonths.length) rows = rows.filter(r => r.Month && selectedMonths.includes(String(r.Month)));
    rows = rows.filter(r => { if(r.Year===null||r.Year===undefined) return false; const y=Number(r.Year); if(isNaN(y)) return false; return y>=selYmin && y<=selYmax; });
    const chosenParams = selectedParams.length ? selectedParams : (PARAMS.length ? [PARAMS[0]] : []);
    return { rows, chosenParams };
  }

  // debounce rendering for speed
  let renderTimer_js = null;
  function scheduleRender(ms = 200){
    if(renderTimer_js) clearTimeout(renderTimer_js);
    renderTimer_js = setTimeout(()=>{ renderAll(); renderTimer_js = null; }, ms);
  }

  // attach change events
  tomLoc.on('change', ()=> scheduleRender());
  tomMonth.on('change', ()=> scheduleRender());
  tomParam.on('change', ()=> scheduleRender());
  sliderDiv.noUiSlider.on('change', ()=> scheduleRender());
  document.getElementById('monthlyAvgToggle').addEventListener('change', ()=> scheduleRender());

  // KPI & table rendering
  function renderKPIs(rows, params){
    const area = document.getElementById('kpisArea'); area.innerHTML='';
    if(params.length >=6) document.body.classList.add('compact'); else document.body.classList.remove('compact');
    if(!params || !params.length){ area.innerHTML = '<div class="kpi">No parameter</div>'; return; }
    if(params.length === 1){
      const p = params[0];
      const vals = rows.map(r => Number(r[p])).filter(v => Number.isFinite(v));
      if(!vals.length){ area.innerHTML = '<div class="kpi">No numeric values</div>'; return; }
      const avg = vals.reduce((a,b)=>a+b,0)/vals.length;
      area.innerHTML = '<div class="kpi"><div style="font-size:12px;color:#666">' + p + ' Avg</div><div style="font-weight:700">' + avg.toFixed(2) + '</div></div>' +
                       '<div class="kpi"><div style="font-size:12px;color:#666">Min</div><div style="font-weight:700">' + Math.min(...vals).toFixed(2) + '</div></div>' +
                       '<div class="kpi"><div style="font-size:12px;color:#666">Max</div><div style="font-weight:700">' + Math.max(...vals).toFixed(2) + '</div></div>' +
                       '<div class="kpi"><div style="font-size:12px;color:#666">Count</div><div style="font-weight:700">' + vals.length + '</div></div>';
    } else {
      area.innerHTML = '<div class="kpi"><div style="font-size:12px;color:#666">Params</div><div style="font-weight:700">' + params.length + '</div></div>' +
                       '<div class="kpi"><div style="font-size:12px;color:#666">Rows</div><div style="font-weight:700">' + rows.length + '</div></div>';
    }
  }

  // Table (multiple parameters selected)
  const MAX_TABLE_ROWS = 1000;
  function renderTable(rows, params){
    const container = document.getElementById('tableContainer');
    if(!params || params.length <= 1){ container.style.display = 'none'; return; }
    container.style.display = 'block';
    const headers = ['Date','Location','Year','Month'].concat(params);
    const head = '<table><thead><tr>' + headers.map(h => '<th>' + h + '</th>').join('') + '</tr></thead><tbody>';
    const rowsHtml = rows.slice(0,MAX_TABLE_ROWS).map(r => {
      const date = r.Date ? (new Date(r.Date)).toISOString().slice(0,10) : '';
      const month = r.Month ? String(r.Month) : (r.Date ? new Date(r.Date).toLocaleString('default',{month:'long'}) : '');
      const cells = [date, r.Location||'', r.Year||'', month].concat(params.map(p => (r[p]!==undefined && r[p]!==null) ? r[p] : ''));
      return '<tr>' + cells.map(c => '<td>' + c + '</td>').join('') + '</tr>';
    }).join('');
    let moreNote = '';
    if(rows.length > MAX_TABLE_ROWS) moreNote = `<div style="font-size:12px;color:#666;margin-top:6px;">Showing first ${MAX_TABLE_ROWS} rows. Download CSV for full data.</div>`;
    document.getElementById('tableWrap').innerHTML = head + rowsHtml + '</tbody></table>' + moreNote;
  }

  // Helpers for plotting: raw time series grouped by location, OR monthly averages
  function groupSeries(rows, param, monthly=false){
    // returns { loc: [{date:Date, value: Number}, ...], ... } OR monthly mapping to averaged points
    const byLoc = {};
    console.log(`Grouping ${rows.length} rows for parameter ${param}, monthly=${monthly}`);

    for(const r of rows){
      if(!r.Date) continue;
      const loc = r.Location || 'Unknown';
      const dt = new Date(r.Date);
      if(isNaN(dt)) continue;
      const val = Number(r[param]);

      // Debug logging for COD data
      if(param === 'COD_mg_L' && loc === 'ITO Bridge') {
        console.log(`COD data for ${loc}: Date=${r.Date}, Value=${val}, Month=${dt.getMonth()+1}, Year=${dt.getFullYear()}`);
      }

      const rowObj = { date: dt, value: Number.isFinite(val) ? val : null, originalRow: r };

      if(!monthly) {
        byLoc[loc] = byLoc[loc] || []; 
        byLoc[loc].push(rowObj);
      } else {
        // key by YYYY-MM for monthly averaging
        const key = dt.getFullYear() + '-' + String(dt.getMonth()+1).padStart(2,'0');
        byLoc[loc] = byLoc[loc] || {}; // mapping key -> list
        byLoc[loc][key] = byLoc[loc][key] || []; 
        byLoc[loc][key].push(rowObj.value);

        // Debug monthly grouping for COD
        if(param === 'COD_mg_L' && loc === 'ITO Bridge' && key === '2024-08') {
          console.log(`Monthly COD data for ${loc} ${key}:`, byLoc[loc][key]);
        }
      }
    }

    // convert monthly map into averaged arrays if monthly
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

          // Debug monthly averages for COD
          if(param === 'COD_mg_L' && loc === 'ITO Bridge' && k === '2024-08') {
            console.log(`Monthly average for ${loc} ${k}: values=${vals}, average=${avg}`);
          }
        }
        // sort by date
        points.sort((a,b)=>a.date - b.date);
        out[loc] = points;
      }
      return out;
    } else {
      // sort each loc by date
      for(const loc of Object.keys(byLoc)){
        byLoc[loc].sort((a,b)=>a.date - b.date);
      }
      return byLoc;
    }
  }

  function chooseScatterType(pointsCount){
    return pointsCount > 1200 ? 'scattergl' : 'scatter';
  }

  // Render time series with bands
  function renderTimeSeriesPerLocation(containerId, rows, param){
    const monthly = document.getElementById('monthlyAvgToggle').checked;
    const series = groupSeries(rows, param, monthly);
    const traces = [];
    let globalMin = Infinity, globalMax = -Infinity, pointsCount = 0;
    for(const [loc, arr] of Object.entries(series)){
      const x = arr.map(pt => pt.date.toISOString());
      const y = arr.map(pt => pt.value);
      if(x.length === 0) continue;
      for(const v of y) if(Number.isFinite(v)){ globalMin = Math.min(globalMin, v); globalMax = Math.max(globalMax, v); }
      pointsCount += x.length;
      const type = chooseScatterType(x.length);
      traces.push({ x, y, mode:'lines+markers', type: type, name: loc, connectgaps: false });
    }
    if(!isFinite(globalMin)) { globalMin = 0; globalMax = 1; }

    // Add standard bands if available, but skip sentinel ranges that would expand axis excessively
    const stdKey = STANDARDS[param] ? param : (STANDARDS[param.replace(/ /g,'_')] ? param.replace(/ /g,'_') : null);
    const shapes = []; const annotations = [];
    if(stdKey && STANDARDS[stdKey]){
      const bands = STANDARDS[stdKey].slice().sort((a,b)=>a.min - b.min);
      const margin = Math.max((globalMax - globalMin) * 0.08, 1);
      for(const b of bands){
        // skip sentinel extremes that are meaningless for plotting (e.g., -999 or very large 9999)
        if(!isFinite(b.min) || !isFinite(b.max)) continue;
        // if band is outside the data range by a wide margin, skip
        const bandMin = b.min, bandMax = b.max;
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
      title: param + ' over time (lines = locations)',
      margin: { t:48, l:60, r:40, b:200 },
      legend: { 
        orientation:'h', 
        y:-0.45,
        x: 0.5,
        xanchor: 'center',
        font: { size: 10 },
        itemsizing: 'constant',
        itemwidth: 30,
        tracegroupgap: 2,
        itemclick: 'toggleothers',
        itemdoubleclick: 'toggle'
      },
      autosize: true,
      // remove vertical gridlines (these were the vertical dashed lines the user saw)
      xaxis: { automargin:true, tickangle:-45, tickformat: monthly ? '%b %Y' : '%b %Y', showgrid: false },
      yaxis: { automargin:true },
      shapes: shapes,
      annotations: annotations
    };

    Plotly.react(containerId, traces, layout, {responsive:true});
  }

  function renderBarAvg(containerId, rows, param){
    // Check if this is a coliform parameter that needs scaling
    const isColiform = param.toLowerCase().includes('coliform');
    const scaleFactor = isColiform ? 10000 : 1;
    const scaleLabel = isColiform ? ' (x10,000)' : '';

    const map = {};
    for(const r of rows){
      const loc = r.Location || 'Unknown';
      const v = Number(r[param]);
      if(!Number.isFinite(v)) continue;
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
      title:'Average ' + param + scaleLabel + ' by Location' 
    };
    Plotly.react(containerId, [{ x: locs, y: vals, type:'bar' }], layout, {responsive:true});
  }

  function renderChartsForParams(rows, params){
    const container = document.getElementById('chartsContainer'); container.innerHTML = '';
    const fragment = document.createDocumentFragment();
    const blocks = [];
    for(const p of params){
      const pid = sanitizeId(p);
      const block = document.createElement('div'); block.className = 'card param-block';
      // give extra bottom space for each time-series chart so legend + x-ticks don't overlap
      // removed histogram section, keeping only time series and bar chart
      block.innerHTML = '<div class="param-title">' + p + '</div>' +
                        '<div id="time_' + pid + '" style="height:440px; margin-bottom:18px;"></div>' +
                        '<div id="bar_' + pid + '" style="height:320px; margin-top:10px;"></div>';
      fragment.appendChild(block);
      blocks.push({ p, pid });
    }
    container.appendChild(fragment);
    // render after DOM append
    requestAnimationFrame(()=>{
      for(const pb of blocks){
        try{
          renderTimeSeriesPerLocation('time_' + pb.pid, rows, pb.p);
          renderBarAvg('bar_' + pb.pid, rows, pb.p);
        }catch(err){
          console.error('Error rendering param', pb.p, err);
          const e = document.createElement('div'); e.textContent = 'Error rendering ' + pb.p; document.getElementById('chartsContainer').appendChild(e);
        }
      }
    });
  }

  function renderAll(){
    const { rows, chosenParams } = filterData();
    document.getElementById('recCount').textContent = rows.length;
    renderKPIs(rows, chosenParams);
    renderTable(rows, chosenParams);
    renderChartsForParams(rows, chosenParams);
  }

  // initial render scheduling
  scheduleRender(250);
  // expose quick refresh
  window.refreshDashboard = function(){ scheduleRender(0); };
});
</script>
</body>
</html>"""

    # replace placeholders safely
    out_html = html_template.replace("__DATA_JSON__", data_json)
    out_html = out_html.replace("__MONTHS_JSON__", months_json)
    out_html = out_html.replace("__PARAMS_JSON__", params_json)
    out_html = out_html.replace("__LOCS_JSON__", locs_json)
    out_html = out_html.replace("__YEARS_JSON__", years_json)

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

    rows = prepare_json_rows(df)

    print("DEBUG: locations:", locations[:10])
    print("DEBUG: months:", months[:12])
    print("DEBUG: years:", years[:10])
    print("DEBUG: numeric params:", numeric_params[:20])

    out_path = Path(__file__).resolve().parent / OUTPUT_HTML
    build_html(rows, months, numeric_params, locations, years, out_path)

    try:
        webbrowser.open(out_path.resolve().as_uri())
    except Exception:
        print("Open the file manually:", out_path)


if __name__ == "__main__":
    main()
