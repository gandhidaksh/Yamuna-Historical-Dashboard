import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from datetime import datetime
import warnings

warnings.filterwarnings('ignore')

# Page configuration
st.set_page_config(
    page_title="🌊 Yamuna Water Quality Dashboard",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 100%);
        padding: 2rem;
        border-radius: 10px;
        margin-bottom: 2rem;
        color: white;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown("""
<div class="main-header">
    <h1>🌊 Yamuna Water Quality Monitoring Dashboard</h1>
    <p>Comprehensive analysis of water quality parameters across monitoring stations</p>
</div>
""", unsafe_allow_html=True)


# Sample data function
@st.cache_data
def load_sample_data():
    sample_data = {
        'Year': [2020, 2020, 2020, 2021, 2021, 2022, 2022, 2023, 2023, 2024] * 4,
        'Month': ['January', 'February', 'March', 'January', 'February', 'January', 'February', 'January', 'February',
                  'March'] * 4,
        'Location': ['Palla'] * 10 + ['ITO Bridge'] * 10 + ['Nizamuddin Bridge'] * 10 + ['Kudesia Ghat'] * 10,
        'WQI': [65, 58, 72, 63, 59, 61, 55, 58, 52, 66] + [35, 42, 48, 38, 41, 33, 36, 31, 28, 38] + [28, 32, 38, 31,
                                                                                                      29, 26, 30, 24,
                                                                                                      22, 29] + [45, 40,
                                                                                                                 52, 42,
                                                                                                                 38, 35,
                                                                                                                 41, 33,
                                                                                                                 30,
                                                                                                                 44],
        'DO_mg_L': [7.2, 6.8, 8.1, 7.0, 6.5, 6.8, 6.2, 6.5, 5.9, 7.1] + [2.1, 3.2, 4.1, 2.5, 3.0, 1.9, 2.8, 1.5, 1.2,
                                                                         2.3] + [1.8, 2.3, 2.8, 2.0, 1.9, 1.6, 2.1, 1.2,
                                                                                 0.9, 1.7] + [3.5, 3.8, 4.2, 3.2, 3.6,
                                                                                              2.9, 3.4, 2.8, 2.5, 3.1],
        'pH': [7.8, 7.5, 7.9, 7.7, 7.4, 7.6, 7.3, 7.5, 7.2, 7.7] + [7.2, 7.4, 7.6, 7.1, 7.3, 7.0, 7.2, 6.9, 6.8,
                                                                    7.1] + [7.1, 7.3, 7.4, 7.0, 7.1, 6.9, 7.1, 6.8, 6.7,
                                                                            7.0] + [7.4, 7.2, 7.8, 7.3, 7.5, 7.1, 7.4,
                                                                                    6.9, 6.8, 7.3],
        'BOD_mg_L': [4, 5, 3, 4.2, 5.1, 4.5, 5.3, 4.8, 5.6, 4.1] + [15, 12, 8, 16, 13, 18, 14, 20, 22, 17] + [18, 16,
                                                                                                              13, 19,
                                                                                                              17, 21,
                                                                                                              18, 24,
                                                                                                              26,
                                                                                                              20] + [8,
                                                                                                                     9,
                                                                                                                     6,
                                                                                                                     8.5,
                                                                                                                     10,
                                                                                                                     9.2,
                                                                                                                     11,
                                                                                                                     8.8,
                                                                                                                     12,
                                                                                                                     7.5],
        'COD_mg_L': [25, 28, 22, 26, 29, 27, 31, 29, 33, 26] + [45, 38, 32, 48, 41, 52, 44, 58, 65, 50] + [52, 48, 42,
                                                                                                           55, 51, 58,
                                                                                                           53, 68, 72,
                                                                                                           60] + [35,
                                                                                                                  32,
                                                                                                                  28,
                                                                                                                  36,
                                                                                                                  38,
                                                                                                                  34,
                                                                                                                  40,
                                                                                                                  37,
                                                                                                                  42,
                                                                                                                  33],
        'TSS_mg_L': [45, 52, 38, 47, 54, 49, 56, 52, 59, 46] + [85, 78, 65, 88, 81, 92, 85, 98, 105, 90] + [95, 88, 78,
                                                                                                            98, 91, 102,
                                                                                                            95, 115,
                                                                                                            125,
                                                                                                            105] + [65,
                                                                                                                    68,
                                                                                                                    58,
                                                                                                                    67,
                                                                                                                    72,
                                                                                                                    64,
                                                                                                                    75,
                                                                                                                    69,
                                                                                                                    78,
                                                                                                                    62],
        'Total_Coliform': [1200, 1500, 900, 1300, 1600, 1400, 1700, 1500, 1800, 1250] + [8500, 7200, 6100, 9000, 7800,
                                                                                         9500, 8200, 10200, 11500,
                                                                                         9200] + [12000, 10500, 9200,
                                                                                                  12800, 11200, 13500,
                                                                                                  11800, 15200, 16800,
                                                                                                  13800] + [4500, 4800,
                                                                                                            3900, 5200,
                                                                                                            5800, 4900,
                                                                                                            6100, 5500,
                                                                                                            6800, 4600]
    }

    df = pd.DataFrame(sample_data)
    df['Date'] = pd.to_datetime(df['Year'].astype(str) + '-' + df['Month'] + '-01')
    return df


# Load data function
@st.cache_data
def load_data(uploaded_file=None):
    if uploaded_file is not None:
        try:
            df = pd.read_excel(uploaded_file, sheet_name='Working Sheet')
            df.columns = df.columns.str.strip()

            year_col = 'Year' if 'Year' in df.columns else ' Year'
            df = df.dropna(subset=[year_col, 'Month', 'Location'])
            df['Year'] = pd.to_numeric(df[year_col], errors='coerce').astype('Int64')

            month_mapping = {
                'January': 1, 'February': 2, 'March': 3, 'April': 4, 'May': 5, 'June': 6,
                'July': 7, 'August': 8, 'September': 9, 'October': 10, 'November': 11, 'December': 12
            }

            df['Month_Num'] = df['Month'].map(month_mapping)
            df['Date'] = pd.to_datetime(df['Year'].astype(str) + '-' + df['Month_Num'].astype(str) + '-01',
                                        errors='coerce')

            numeric_cols = ['pH', 'TSS(mg/L)', 'COD_mg_L', 'BOD_mg_L', 'DO_mg_L',
                            'Total_Coliform_MPN_100ml', 'Faecal_Coliform_MPN_100ml',
                            'Phosphate_mg_L', 'Surfactant (mg/L)', 'Ammonical_Nitrogen_mg_L', 'WQI']

            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            column_mapping = {
                'pH': 'pH', 'TSS(mg/L)': 'TSS_mg_L', 'COD_mg_L': 'COD_mg_L',
                'BOD_mg_L': 'BOD_mg_L', 'DO_mg_L': 'DO_mg_L', 'WQI': 'WQI',
                'Total_Coliform_MPN_100ml': 'Total_Coliform',
                'Faecal_Coliform_MPN_100ml': 'Faecal_Coliform',
                'Phosphate_mg_L': 'Phosphate_mg_L',
                'Surfactant (mg/L)': 'Surfactant_mg_L',
                'Ammonical_Nitrogen_mg_L': 'Ammonical_Nitrogen_mg_L'
            }

            existing_columns = {k: v for k, v in column_mapping.items() if k in df.columns}
            df = df.rename(columns=existing_columns)

            df = df.dropna(subset=['Date', 'Year'])
            numeric_columns = df.select_dtypes(include=[np.number]).columns
            df = df[df[numeric_columns].notna().any(axis=1)]

            essential_cols = ['Year', 'Month', 'Location', 'Date']
            parameter_cols = [col for col in df.columns if col not in essential_cols and col != 'Month_Num']
            final_cols = essential_cols + parameter_cols
            df = df[final_cols]

            return df

        except Exception as e:
            st.error(f"Error reading file: {e}")
            return load_sample_data()
    else:
        return load_sample_data()


# Quality standards
QUALITY_STANDARDS = {
    'WQI': {
        'Excellent': {'min': 91, 'max': 100, 'color': '#059669'},
        'Good': {'min': 71, 'max': 90, 'color': '#0891b2'},
        'Fair': {'min': 51, 'max': 70, 'color': '#ca8a04'},
        'Poor': {'min': 26, 'max': 50, 'color': '#dc2626'},
        'Very Poor': {'min': 0, 'max': 25, 'color': '#7c2d12'}
    },
    'DO_mg_L': {
        'Good': {'min': 5, 'max': 100, 'color': '#059669'},
        'Fair': {'min': 3, 'max': 4.9, 'color': '#ca8a04'},
        'Poor': {'min': 0, 'max': 2.9, 'color': '#dc2626'}
    },
    'pH': {
        'Good': {'min': 6.5, 'max': 8.5, 'color': '#059669'},
        'Fair': {'min': 6.0, 'max': 9.0, 'color': '#ca8a04'},
        'Poor': {'min': 0, 'max': 14, 'color': '#dc2626'}
    }
}


def get_quality_status(value, parameter):
    if pd.isna(value):
        return 'No Data', '#6b7280'

    if parameter in QUALITY_STANDARDS:
        for status, criteria in QUALITY_STANDARDS[parameter].items():
            if criteria['min'] <= value <= criteria['max']:
                return status, criteria['color']

    return 'Unknown', '#6b7280'


def calculate_trend(data, parameter):
    if len(data) < 4 or parameter not in data.columns:
        return None

    try:
        data_clean = data.copy()
        data_clean['Date'] = pd.to_datetime(data_clean['Date'], errors='coerce')
        data_clean = data_clean.dropna(subset=['Date'])

        data_sorted = data_clean.sort_values('Date')
        values = data_sorted[parameter].dropna()

        if len(values) < 4:
            return None

        mid_point = len(values) // 2
        first_half = values.iloc[:mid_point].mean()
        second_half = values.iloc[mid_point:].mean()

        if first_half != 0:
            change = ((second_half - first_half) / first_half) * 100

            if abs(change) > 10:
                if parameter in ['WQI', 'DO_mg_L']:
                    trend = 'Improving' if change > 0 else 'Degrading'
                elif parameter in ['BOD_mg_L', 'COD_mg_L']:
                    trend = 'Improving' if change < 0 else 'Degrading'
                else:
                    trend = 'Stable'
            else:
                trend = 'Stable'

            return {
                'change': round(change, 1),
                'trend': trend,
                'first_avg': round(first_half, 2),
                'second_avg': round(second_half, 2)
            }

    except Exception:
        return None

    return None


# Load data
st.sidebar.header("📁 Data Upload")
uploaded_file = st.sidebar.file_uploader("Upload your Excel file", type=['xlsx', 'xls'])
df = load_data(uploaded_file)

if df.empty:
    st.error("No data available.")
    st.stop()

st.sidebar.success(f"✅ Data loaded: {len(df)} records")

# Get available options
locations_all = sorted(df['Location'].unique().tolist())
years_all = sorted(df['Year'].unique().tolist(), reverse=True)
months_all = ['January', 'February', 'March', 'April', 'May', 'June',
              'July', 'August', 'September', 'October', 'November', 'December']
available_months = [month for month in months_all if month in df['Month'].unique()]
parameters = [col for col in df.columns if col not in ['Year', 'Month', 'Date', 'Location']]

parameter_labels = {
    'WQI': 'Water Quality Index',
    'pH': 'pH Level',
    'DO_mg_L': 'Dissolved Oxygen (mg/L)',
    'BOD_mg_L': 'BOD (mg/L)',
    'COD_mg_L': 'COD (mg/L)',
    'TSS_mg_L': 'Total Suspended Solids (mg/L)',
    'Total_Coliform': 'Total Coliform (MPN/100ml)',
    'Faecal_Coliform': 'Faecal Coliform (MPN/100ml)',
    'Phosphate_mg_L': 'Phosphate (mg/L)',
    'Surfactant_mg_L': 'Surfactant (mg/L)',
    'Ammonical_Nitrogen_mg_L': 'Ammonical Nitrogen (mg/L)'
}

# Enhanced Sidebar with Multi-select
st.sidebar.header("🔍 Advanced Filters")

# Location filter
st.sidebar.write("**📍 Locations**")
select_all_locations = st.sidebar.checkbox("Select All Locations")

if select_all_locations:
    selected_locations = st.sidebar.multiselect(
        "Choose locations:",
        options=locations_all,
        default=locations_all,
        help="Search by typing location name"
    )
else:
    selected_locations = st.sidebar.multiselect(
        "Choose locations:",
        options=locations_all,
        default=[locations_all[0]] if locations_all else [],
        help="Search by typing location name"
    )

# Year filter
st.sidebar.write("**📅 Years**")
select_all_years = st.sidebar.checkbox("Select All Years")

if select_all_years:
    selected_years = st.sidebar.multiselect(
        "Choose years:",
        options=years_all,
        default=years_all,
        help="Select multiple years for comparison"
    )
else:
    selected_years = st.sidebar.multiselect(
        "Choose years:",
        options=years_all,
        default=[years_all[0]] if years_all else [],
        help="Select multiple years for comparison"
    )

# Month filter
st.sidebar.write("**🗓️ Months**")
select_all_months = st.sidebar.checkbox("Select All Months")

if select_all_months:
    selected_months = st.sidebar.multiselect(
        "Choose months:",
        options=available_months,
        default=available_months,
        help="Select multiple months for seasonal analysis"
    )
else:
    selected_months = st.sidebar.multiselect(
        "Choose months:",
        options=available_months,
        default=[available_months[0]] if available_months else [],
        help="Select multiple months for seasonal analysis"
    )

# Parameter filter
st.sidebar.write("**📊 Parameters**")
select_all_parameters = st.sidebar.checkbox("Select All Parameters")

if select_all_parameters:
    selected_parameters = st.sidebar.multiselect(
        "Choose parameters:",
        options=parameters,
        default=parameters,
        format_func=lambda x: parameter_labels.get(x, x),
        help="Search by typing parameter name"
    )
else:
    selected_parameters = st.sidebar.multiselect(
        "Choose parameters:",
        options=parameters,
        default=['WQI'] if 'WQI' in parameters else [parameters[0]] if parameters else [],
        format_func=lambda x: parameter_labels.get(x, x),
        help="Search by typing parameter name"
    )

# Primary parameter
primary_parameter = st.sidebar.selectbox(
    "🎯 Primary Parameter (for detailed analysis):",
    options=selected_parameters if selected_parameters else parameters,
    format_func=lambda x: parameter_labels.get(x, x),
    help="Main parameter for trend analysis and insights"
) if selected_parameters else None

# Filter data
filtered_df = df.copy()

if selected_locations:
    filtered_df = filtered_df[filtered_df['Location'].isin(selected_locations)]

if selected_years:
    filtered_df = filtered_df[filtered_df['Year'].isin(selected_years)]

if selected_months:
    filtered_df = filtered_df[filtered_df['Month'].isin(selected_months)]

if selected_parameters:
    parameter_mask = filtered_df[selected_parameters].notna().any(axis=1)
    filtered_df = filtered_df[parameter_mask]

# Get primary parameter data
if primary_parameter:
    primary_param_data = filtered_df.dropna(subset=[primary_parameter])
else:
    primary_param_data = filtered_df

# Check for data availability
if len(filtered_df) == 0:
    st.warning("⚠️ No data available for the selected filters. Please adjust your selection.")
    st.stop()

# Display current selection info
st.sidebar.markdown("---")
st.sidebar.markdown("**📈 Current Selection:**")
st.sidebar.success(f"✅ **{len(filtered_df):,}** total records")
st.sidebar.info(f"📍 **{len(selected_locations)}** locations")
st.sidebar.info(f"📅 **{len(selected_years)}** years")
st.sidebar.info(f"📊 **{len(selected_parameters)}** parameters")

# Enhanced Metrics
if primary_parameter and len(primary_param_data) > 0:
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        avg_val = primary_param_data[primary_parameter].mean()
        st.metric("📊 Average", f"{avg_val:.2f}")

    with col2:
        min_val = primary_param_data[primary_parameter].min()
        st.metric("📉 Minimum", f"{min_val:.2f}")

    with col3:
        max_val = primary_param_data[primary_parameter].max()
        st.metric("📈 Maximum", f"{max_val:.2f}")

    with col4:
        count = len(primary_param_data)
        st.metric("📋 Records", f"{count:,}")

    with col5:
        trend_analysis = calculate_trend(primary_param_data, primary_parameter)
        if trend_analysis:
            st.metric("📊 Trend", f"{trend_analysis['change']}%", delta=trend_analysis['trend'])
        else:
            st.metric("📊 Trend", "N/A")

    # Multi-parameter overview
    if len(selected_parameters) > 1:
        st.markdown("### 📊 Multi-Parameter Overview")

        param_summary = []
        for param in selected_parameters:
            param_data = filtered_df[param].dropna()
            if len(param_data) > 0:
                param_summary.append({
                    'Parameter': parameter_labels.get(param, param),
                    'Records': len(param_data),
                    'Average': round(param_data.mean(), 2),
                    'Min': round(param_data.min(), 2),
                    'Max': round(param_data.max(), 2),
                    'Std Dev': round(param_data.std(), 2)
                })

        if param_summary:
            summary_df = pd.DataFrame(param_summary)
            st.dataframe(summary_df, use_container_width=True)

# Main analysis tabs
tab1, tab2, tab3, tab4 = st.tabs(["📈 Trends", "🔍 Analysis", "📊 Compare", "💡 Insights"])

with tab1:
    st.subheader("📈 Parameter Trends Analysis")

    if primary_parameter and len(primary_param_data) > 0:
        chart_type = st.radio("Chart Type:", ["Line Chart", "Bar Chart", "Area Chart", "Scatter Plot"], horizontal=True)

        plot_df = primary_param_data.copy()
        plot_df['Period'] = plot_df['Month'].str[:3] + ' ' + plot_df['Year'].astype(str)
        plot_df = plot_df.sort_values('Date')

        if chart_type == "Line Chart":
            fig = px.line(plot_df, x='Period', y=primary_parameter,
                          color='Location' if len(selected_locations) > 1 else None,
                          title=f"{parameter_labels.get(primary_parameter, primary_parameter)} Over Time")
        elif chart_type == "Bar Chart":
            fig = px.bar(plot_df, x='Period', y=primary_parameter,
                         color='Location' if len(selected_locations) > 1 else None,
                         title=f"{parameter_labels.get(primary_parameter, primary_parameter)} Over Time")
        elif chart_type == "Area Chart":
            fig = px.area(plot_df, x='Period', y=primary_parameter,
                          color='Location' if len(selected_locations) > 1 else None,
                          title=f"{parameter_labels.get(primary_parameter, primary_parameter)} Over Time")
        else:
            fig = px.scatter(plot_df, x='Period', y=primary_parameter,
                             color='Location' if len(selected_locations) > 1 else None,
                             title=f"{parameter_labels.get(primary_parameter, primary_parameter)} Over Time")

        # Add reference lines
        if primary_parameter == 'WQI':
            fig.add_hline(y=50, line_dash="dash", line_color="orange", annotation_text="Fair")
            fig.add_hline(y=70, line_dash="dash", line_color="blue", annotation_text="Good")
        elif primary_parameter == 'DO_mg_L':
            fig.add_hline(y=5, line_dash="dash", line_color="green", annotation_text="Safe Level")
        elif primary_parameter == 'pH':
            fig.add_hline(y=6.5, line_dash="dash", line_color="green", annotation_text="Lower Optimal")
            fig.add_hline(y=8.5, line_dash="dash", line_color="green", annotation_text="Upper Optimal")

        fig.update_layout(height=500)
        fig.update_xaxes(tickangle=45)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Please select a primary parameter and ensure data is available.")

with tab2:
    st.subheader("🔍 Detailed Analysis")

    if primary_parameter and len(filtered_df) > 0:
        col1, col2 = st.columns(2)

        with col1:
            st.write("**🗓️ Seasonal Patterns**")
            monthly_avg = filtered_df.groupby('Month')[primary_parameter].mean().reset_index()
            month_order = ['January', 'February', 'March', 'April', 'May', 'June',
                           'July', 'August', 'September', 'October', 'November', 'December']
            monthly_avg['Month'] = pd.Categorical(monthly_avg['Month'], categories=month_order, ordered=True)
            monthly_avg = monthly_avg.sort_values('Month')

            fig_monthly = px.bar(monthly_avg, x='Month', y=primary_parameter,
                                 title=f"Monthly Average - {parameter_labels.get(primary_parameter, primary_parameter)}",
                                 color=primary_parameter, color_continuous_scale='RdYlGn_r')
            fig_monthly.update_layout(height=400)
            fig_monthly.update_xaxes(tickangle=45)
            st.plotly_chart(fig_monthly, use_container_width=True)

        with col2:
            st.write("**📅 Yearly Trends**")
            yearly_avg = filtered_df.groupby('Year')[primary_parameter].mean().reset_index()

            fig_yearly = px.line(yearly_avg, x='Year', y=primary_parameter,
                                 title=f"Yearly Average - {parameter_labels.get(primary_parameter, primary_parameter)}",
                                 markers=True)
            fig_yearly.update_layout(height=400)
            st.plotly_chart(fig_yearly, use_container_width=True)

        # Distribution
        st.write("**📊 Value Distribution**")
        fig_hist = px.histogram(primary_param_data, x=primary_parameter, nbins=20,
                                title=f"Distribution of {parameter_labels.get(primary_parameter, primary_parameter)}",
                                color_discrete_sequence=['#3b82f6'])
        fig_hist.update_layout(height=400)
        st.plotly_chart(fig_hist, use_container_width=True)

with tab3:
    st.subheader("📊 Location Comparison")

    if primary_parameter and len(selected_locations) > 1:
        location_avg = filtered_df.groupby('Location')[primary_parameter].mean().sort_values(
            ascending=False).reset_index()
        location_avg['Location_Short'] = location_avg['Location'].str[:30] + '...'

        fig_comparison = px.bar(location_avg, x='Location_Short', y=primary_parameter,
                                title=f"Average {parameter_labels.get(primary_parameter, primary_parameter)} by Location",
                                color=primary_parameter, color_continuous_scale='RdYlGn_r')
        fig_comparison.update_layout(height=500)
        fig_comparison.update_xaxes(tickangle=45)
        st.plotly_chart(fig_comparison, use_container_width=True)
    else:
        st.info("Select multiple locations and a primary parameter for comparison.")

with tab4:
    st.subheader("💡 Water Quality Insights")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("### ⚠️ Areas of Concern")
        if primary_parameter:
            concern_locations = []
            for location in selected_locations:
                location_data = filtered_df[filtered_df['Location'] == location][primary_parameter].dropna()
                if len(location_data) > 0:
                    avg_val = location_data.mean()
                    if primary_parameter == 'WQI' and avg_val < 50:
                        concern_locations.append((location, avg_val))
                    elif primary_parameter == 'DO_mg_L' and avg_val < 3:
                        concern_locations.append((location, avg_val))

            if concern_locations:
                for location, value in concern_locations[:5]:
                    st.warning(f"📍 {location[:25]}...\n💔 {value:.1f}")
            else:
                st.success("✅ No critical areas identified!")

    with col2:
        st.markdown("### 📈 Trend Analysis")
        if primary_parameter:
            trend_analysis = calculate_trend(primary_param_data, primary_parameter)
            if trend_analysis:
                trend_emoji = "📈" if trend_analysis['trend'] == 'Improving' else "📉" if trend_analysis[
                                                                                            'trend'] == 'Degrading' else "🔄"
                st.info(
                    f"""{trend_emoji} **Trend:** {trend_analysis['trend']}\n\n📊 **Change:** {trend_analysis['change']}%\n\n📈 **First Half:** {trend_analysis['first_avg']}\n\n📊 **Second Half:** {trend_analysis['second_avg']}""")
            else:
                st.info("Not enough data for trend analysis.")

    with col3:
        st.markdown("### 🔬 Parameter Standards")
        if primary_parameter and primary_parameter in QUALITY_STANDARDS:
            for status, criteria in QUALITY_STANDARDS[primary_parameter].items():
                st.markdown(
                    f"""<div style="padding: 0.3rem; margin: 0.1rem 0; background: {criteria['color']}20; border-left: 3px solid {criteria['color']}; border-radius: 3px;"><strong style="color: {criteria['color']}">{status}</strong>: {criteria['min']}-{criteria['max']}</div>""",
                    unsafe_allow_html=True)
        else:
            st.info("No specific standards defined for this parameter")

# Footer
st.markdown("---")
st.markdown("### 📋 Data Summary")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("🗂️ Total Records", f"{len(df):,}")