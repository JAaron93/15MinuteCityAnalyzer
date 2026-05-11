import logging
import os

import pandas as pd
import streamlit as st
from streamlit_folium import folium_static

from src.dashboard.data_loader import load_geoparquet
from src.dashboard.filters import apply_all_filters
from src.dashboard.map_renderer import create_choropleth_map
from src.dashboard.metrics import calculate_equity_metrics

# Constants
def get_city_median_income_fallback() -> float:
    """
    Get city median income fallback value from environment variable.
    
    Reads CITY_MEDIAN_INCOME_FALLBACK or CITY_MEDIAN_INCOME_DEFAULT env var.
    Defaults to 100000 if unset or invalid.
    
    Expected format: numeric value (e.g., "100000" or "75000.50")
    """
    fallback_env = os.environ.get('CITY_MEDIAN_INCOME_FALLBACK') or os.environ.get('CITY_MEDIAN_INCOME_DEFAULT')
    if fallback_env is not None:
        try:
            return float(fallback_env)
        except ValueError:
            logger.warning(f"Invalid CITY_MEDIAN_INCOME_FALLBACK value: '{fallback_env}'. Using default: 100000")
    # Default value represents a reasonable median income for many US cities
    return 100000.0

# Get the fallback value (can be overridden by environment variable)
CITY_MEDIAN_INCOME_FALLBACK = get_city_median_income_fallback()

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page Configuration
st.set_page_config(
    page_title="15-Minute City & Transit Equity Analyzer",
    page_icon="🏙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for Premium Look
st.markdown(
    """
    <style>
    .main {
        background-color: #f8f9fa;
    }
    .stMetric {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .footer {
        background-color: white;
        color: #6c757d;
        text-align: center;
        padding: 10px;
        font-size: 0.8rem;
        border-top: 1px solid #dee2e6;
        margin-top: 50px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Application Header
st.title("🏙️ 15-Minute City & Transit Equity Analyzer")
st.markdown("""
    This interactive dashboard evaluates urban accessibility and transit equity.
    It measures the ability of residents to access essential amenities within a
    15-minute walk and highlights disparities across different income levels.
""")

# Load Data
DATA_PATH = "data/processed/processed_equity_data.parquet"

try:
    gdf = load_geoparquet(DATA_PATH)

    # Sidebar Controls
    st.sidebar.header("🗺️ Map Controls")

    # Layer Toggle
    map_layer = st.sidebar.radio(
        "Select Map Layer", ["Accessibility Score", "Median Income"], index=0
    )
    metric_col = (
        "accessibility_score" if map_layer == "Accessibility Score" else "median_income"
    )

    st.sidebar.markdown("---")
    st.sidebar.header("🔍 Filters")

    # Income Slider
    city_median_income = gdf["median_income"].median()
    if pd.isna(city_median_income) or city_median_income <= 0:
        logger.warning(f"Invalid city median income detected: {city_median_income}. Using fallback value: {CITY_MEDIAN_INCOME_FALLBACK}")
        city_median_income = CITY_MEDIAN_INCOME_FALLBACK  # fallback for missing/invalid data
    # default_threshold = 50% of city median, clamped to [0, 200k]
    default_income_threshold = min(max(city_median_income * 0.5, 0), 200000)

    income_threshold = st.sidebar.slider(
        "Max Median Income ($)",
        min_value=0,
        max_value=200000,
        value=int(default_income_threshold),
        step=5000,
        help=(
            f"Focus on areas with income below this value. "
            f"City Median: ${city_median_income:,.0f}"
        ),
    )

    # Score Range Slider
    score_range = st.sidebar.slider(
        "Accessibility Score Range", min_value=0, max_value=100, value=(0, 100), step=5
    )

    if st.sidebar.button("Reset Filters"):
        st.rerun()

    # Apply Filters
    filtered_gdf = apply_all_filters(gdf, income_threshold, score_range)

    # Calculate Metrics
    metrics = calculate_equity_metrics(filtered_gdf, income_threshold=income_threshold)

    # Layout: Top Row Metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Block Groups", f"{metrics.get('total_block_groups', 0)}")
    with col2:
        st.metric("Total Population", f"{metrics.get('total_population', 0):,.0f}")
    with col3:
        st.metric(
            "Low Access Pop %",
            f"{metrics.get('pct_pop_low_access', 0.0):.1f}%",
        )
    with col4:
        st.metric(
            "Low Income/Access %",
            f"{metrics.get('pct_low_income_low_access', 0.0):.1f}%",
        )

    # Main Map View
    st.subheader(f"Interactive Map: {map_layer}")
    if not filtered_gdf.empty:
        m = create_choropleth_map(filtered_gdf, metric=metric_col)
        folium_static(m, width=1200, height=600)
    else:
        st.warning("No data matches the selected filters. Please adjust your criteria.")

    # Bottom Row: Additional Analysis
    st.markdown("---")
    st.subheader("📊 Equity Analysis")

    c1, c2 = st.columns([1, 2])

    with c1:
        st.write("### Accessibility by Income Quartile")
        if metrics["avg_score_by_quartile"]:
            quartile_df = pd.DataFrame.from_dict(
                metrics["avg_score_by_quartile"], orient="index", columns=["Avg Score"]
            ).reset_index()
            quartile_df.columns = ["Quartile", "Avg Score"]
            st.bar_chart(quartile_df, x="Quartile", y="Avg Score")
        else:
            st.info("Insufficient data for quartile analysis.")

    with c2:
        st.write("### Score Distribution")
        st.write("Distribution of accessibility scores across the filtered areas.")
        if not filtered_gdf.empty:
            try:
                # Bin continuous scores into 10 ranges (e.g., 0-10, 10-20)
                # for clearer distribution visualization
                bins = pd.cut(filtered_gdf["accessibility_score"], bins=10)
                hist_data = bins.value_counts().sort_index()
                # Use string labels for the intervals to ensure proper display on the x-axis
                hist_data.index = hist_data.index.astype(str)
                st.bar_chart(hist_data)
            except ValueError:
                st.info("Insufficient variance in scores for distribution chart.")
        else:
            st.info("No data available for score distribution.")

except FileNotFoundError:
    st.error("⚠️ Processed data not found.")
    st.markdown("""
        The dashboard cannot load the required data file.
        Please run the data processing pipeline first to generate
        `data/processed/processed_equity_data.parquet`.

        ```bash
        # Example command to run the pipeline (if implemented as a script)
        python pipeline.py
        ```
    """)
except Exception as e:
    st.error(f"❌ An error occurred: {str(e)}")
    logger.exception("Dashboard error")

# Footer
st.markdown(
    """
    <div class="footer">
        Data Sources: U.S. Census Bureau ACS 5-Year Estimates (2021) & OpenStreetMap.
        Built with Streamlit, Folium, and GeoPandas.
        &copy; 2026 Transit Equity Project. Licensed under ODbL.
    </div>
    """,
    unsafe_allow_html=True,
)
