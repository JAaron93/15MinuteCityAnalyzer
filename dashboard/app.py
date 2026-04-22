"""Streamlit Dashboard for 15-Minute City Accessibility Analysis."""

import sys
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

import pandas as pd
import plotly.express as px
import streamlit as st

from fifteen_minute_city import (
    create_accessibility_map,
    create_amenity_breakdown,
    create_equity_chart,
    create_summary_stats,
    load_processed_data,
    COLOR_PALETTE,
)

# Page configuration
st.set_page_config(
    page_title="15-Minute City Analyzer",
    page_icon="🏙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for styling
st.markdown(
    """
    <style>
    .metric-container {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 1rem;
    }
    .stMetric {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def main():
    """Main dashboard application."""
    st.title("🏙️ 15-Minute City Accessibility Analyzer")
    st.markdown(
        "Analyze urban accessibility and transit equity for any city. "
        "Data processed using OpenStreetMap and the Marimo data pipeline."
    )

    # Sidebar - Data Loading
    with st.sidebar:
        st.header("📁 Data Configuration")

        data_dir = st.text_input(
            "Processed data directory",
            value="data/processed",
            help="Directory containing parquet files from the Marimo notebook",
        )

        available_files = get_available_files(project_root / data_dir)
        data_file = st.selectbox(
            "Select data file",
            options=available_files,
            help="Choose a processed accessibility dataset",
        )

        st.divider()

        st.header("🎨 Visualization Settings")

        map_style = st.selectbox(
            "Map style",
            options=["carto-positron", "open-street-map", "carto-darkmatter"],
            index=0,
        )

        score_threshold = st.slider(
            "Minimum accessibility score to display",
            min_value=0,
            max_value=100,
            value=0,
            help="Filter out low-scoring areas",
        )

        st.divider()

        st.markdown(
            f"""
            **Legend:**
            - 🟢 {COLOR_PALETTE['high']} High accessibility (80-100)
            - 🟡 {COLOR_PALETTE['medium']} Medium accessibility (40-79)
            - 🔴 {COLOR_PALETTE['low']} Low accessibility (0-39)
            """
        )

    # Main content
    if not data_file:
        st.warning(
            "⚠️ No processed data files found. "
            "Please run the Marimo data processing notebook first:"
        )
        st.code("marimo edit notebooks/data_processing.py", language="bash")
        return

    # Load data
    with st.spinner("Loading accessibility data..."):
        df = load_processed_data(project_root / data_dir, data_file)

    if df is None or len(df) == 0:
        st.error("❌ Failed to load data or dataset is empty.")
        return

    # Apply filters
    if score_threshold > 0:
        df = df[df["overall_score"] >= score_threshold]

    # Summary metrics
    st.header("📊 Summary Statistics")
    stats = create_summary_stats(df)

    cols = st.columns(4)
    with cols[0]:
        st.metric(
            "Mean Accessibility",
            f"{stats['mean_score']:.1f}/100",
            delta=f"{stats['mean_score'] - 50:.1f}" if stats['mean_score'] > 50 else None,
        )
    with cols[1]:
        st.metric(
            "High Accessibility Areas",
            f"{stats['pct_high_accessibility']:.1f}%",
        )
    with cols[2]:
        st.metric(
            "Low Accessibility Areas",
            f"{stats['pct_low_accessibility']:.1f}%",
        )
    with cols[3]:
        st.metric(
            "Total Grid Points",
            f"{stats['total_points_analyzed']:,}",
        )

    # Main dashboard tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "🗺️ Accessibility Map",
        "📈 Distribution",
        "🏘️ Equity Analysis",
        "📋 Raw Data",
    ])

    with tab1:
        st.subheader("Interactive Accessibility Map")
        st.markdown(
            "Colored points represent accessibility scores at each location. "
            "Higher scores (green) indicate better 15-minute city compliance."
        )

        # Create the map
        fig = create_accessibility_map(df, center=None, zoom=12)

        # Update map style
        fig.update_layout(
            mapbox=dict(
                style=map_style,
            ),
            height=600,
        )

        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.subheader("Score Distribution")

        col1, col2 = st.columns(2)

        with col1:
            # Histogram
            fig_hist = px.histogram(
                df,
                x="overall_score",
                nbins=20,
                title="Distribution of Accessibility Scores",
                labels={"overall_score": "Accessibility Score"},
                color_discrete_sequence=[COLOR_PALETTE["high"]],
            )
            fig_hist.add_vline(
                x=80, line_dash="dash", line_color="green", annotation_text="Good"
            )
            fig_hist.add_vline(
                x=40, line_dash="dash", line_color="red", annotation_text="Poor"
            )
            st.plotly_chart(fig_hist, use_container_width=True)

        with col2:
            # Box plot by quartiles
            labels = ["Q1 (Lowest)", "Q2", "Q3", "Q4 (Highest)"]
            try:
                df["quartile"] = pd.qcut(df["overall_score"], 4, labels=labels)
            except ValueError:
                # Fallback if there are not enough unique values for 4 quantiles
                df["quartile"] = pd.cut(df["overall_score"], bins=4, labels=labels)
            
            fig_box = px.box(
                df,
                y="quartile",
                x="overall_score",
                color="quartile",
                title="Score Quartiles",
                labels={"overall_score": "Accessibility Score", "quartile": "Quartile"},
            )
            st.plotly_chart(fig_box, use_container_width=True)

        # Amenity breakdown
        st.subheader("Amenity Accessibility Breakdown")
        fig_amenities = create_amenity_breakdown(df)
        fig_amenities.update_layout(height=400)
        st.plotly_chart(fig_amenities, use_container_width=True)

    with tab3:
        st.subheader("🏘️ Neighborhood Equity Analysis")

        # Note about neighborhoods
        st.info(
            "ℹ️ To view neighborhood-level equity metrics, "
            "upload neighborhood boundaries in the Marimo notebook "
            "and re-save the processed data with equity calculations."
        )

        # Show equity metrics if available in dataframe
        if "neighborhood" in df.columns:
            equity_summary = (
                df.groupby("neighborhood")["overall_score"]
                .agg(["mean", "median", "std", "count"])
                .reset_index()
                .sort_values("mean", ascending=False)
            )

            st.dataframe(equity_summary, use_container_width=True)

            # Equity chart (mock since we don't have the actual neighborhoods GeoDataFrame)
            fig_equity = px.bar(
                equity_summary.sort_values("mean"),
                x="mean",
                y="neighborhood",
                orientation="h",
                title="Mean Accessibility Score by Neighborhood",
                color="mean",
                color_continuous_scale="RdYlGn",
                range_color=[0, 100],
            )
            st.plotly_chart(fig_equity, use_container_width=True)
        else:
            st.markdown(
                "### 📝 Equity Metrics Not Available\n\n"
                "The current dataset doesn't include neighborhood-level breakdowns. "
                "To generate equity metrics:\n\n"
                "1. Obtain a GeoJSON file with neighborhood boundaries\n"
                "2. Upload it in the Marimo notebook (Step 4)\n"
                "3. Re-save the processed data\n"
                "4. Refresh this dashboard"
            )

    with tab4:
        st.subheader("📋 Raw Accessibility Data")

        # Download button
        csv = df.to_csv(index=False)
        st.download_button(
            label="⬇️ Download as CSV",
            data=csv,
            file_name="accessibility_data.csv",
            mime="text/csv",
        )

        # Show dataframe
        st.dataframe(df, use_container_width=True, height=500)

    # Footer
    st.divider()
    st.markdown(
        f"""
        <div style='text-align: center; color: #666;'>
            <small>
                15-Minute City Analyzer | Data source: OpenStreetMap |
                {len(df):,} grid points analyzed |
                Generated with ❤️ using Streamlit & Plotly
            </small>
        </div>
        """,
        unsafe_allow_html=True,
    )


def get_available_files(data_dir: Path) -> list:
    """Get list of available parquet files in the data directory."""
    if not data_dir.exists():
        return []

    files = list(data_dir.glob("*.parquet"))
    return [f.name for f in files]


if __name__ == "__main__":
    main()
