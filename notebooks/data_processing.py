# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "marimo>=0.4.0",
#     "osmnx>=1.7.0",
#     "geopandas>=0.13.0",
#     "pandas>=2.0.0",
#     "plotly>=5.15.0",
#     "numpy>=1.24.0",
# ]
# ///

"""15-Minute City Data Processing Pipeline

This Marimo notebook processes OpenStreetMap data to calculate
15-minute walking accessibility scores and transit equity metrics.

Run with: marimo edit notebooks/data_processing.py
"""

import marimo as mo


__generated_with = "0.4.0"


@app.cell
def _():
    import sys
    from pathlib import Path
    import plotly.express as px

    # Add src to path for imports
    project_root = Path.cwd()
    sys.path.insert(0, str(project_root / "src"))

    return Path, project_root, sys, px


@app.cell
def _():
    import marimo as mo
    import plotly.graph_objects as go
    import pandas as pd
    import geopandas as gpd
    from pathlib import Path

    from fifteen_minute_city import (
        download_city_network,
        get_amenities,
        generate_grid_accessibility,
        calculate_equity_metrics,
        create_accessibility_map,
        save_processed_data,
        DEFAULT_AMENITIES,
    )

    return (
        DEFAULT_AMENITIES,
        calculate_equity_metrics,
        create_accessibility_map,
        download_city_network,
        gpd,
        generate_grid_accessibility,
        get_amenities,
        go,
        mo,
        pd,
        save_processed_data,
    )


@app.cell
def _(mo):
    # UI Configuration
    mo.md("# 🏙️ 15-Minute City Data Processing Pipeline")
    return


@app.cell
def _(mo):
    # City Selection
    city_name = mo.ui.text(
        value="Berkeley, California, USA",
        label="Enter city name (as recognized by OpenStreetMap):",
    )
    city_name
    return (city_name,)


@app.cell
def _(mo):
    # Analysis Parameters
    time_threshold = mo.ui.slider(
        start=5, stop=30, step=5, value=15,
        label="Walking time threshold (minutes)",
    )

    grid_resolution = mo.ui.slider(
        start=10, stop=50, step=5, value=20,
        label="Grid resolution (higher = more detailed but slower)",
    )

    mo.hstack([time_threshold, grid_resolution])
    return grid_resolution, time_threshold


@app.cell
def _(city_name, mo):
    # Amenities Selection
    mo.md("## Select amenities to analyze")

    amenities_config = mo.ui.dropdown(
        options=[
            ("Default set", "default"),
            ("Essential only (grocery, healthcare, transit)", "essential"),
            ("Full set + extra amenities", "full"),
        ],
        value="default",
        label="Amenity preset",
    )
    amenities_config
    return (amenities_config,)


@app.cell
def _(amenities_config, mo):
    # Show selected amenities
    if amenities_config.value == "default":
        selected_amenities = ["grocery", "healthcare", "transit", "schools", "parks"]
    elif amenities_config.value == "essential":
        selected_amenities = ["grocery", "healthcare", "transit"]
    else:
        selected_amenities = list(DEFAULT_AMENITIES.keys())

    mo.md(f"**Selected amenities:** {', '.join(selected_amenities)}")
    return (selected_amenities,)


@app.cell
def _(mo):
    mo.md("---")
    mo.md("## Step 1: Download Street Network and Amenities")
    return


@app.cell
def _(mo):
    run_download = mo.ui.run_button(label="🚀 Load Data from OpenStreetMap")
    run_download
    return (run_download,)


@app.cell
def _(run_download, city_name, mo):
    if not run_download.value:
        mo.stop()

    with mo.status.spinner("Downloading data from OpenStreetMap...") as spinner:
        try:
            spinner.update("Downloading walking network...")
            graph, boundary = download_city_network(city_name.value)

            spinner.update("Downloading amenity locations...")
            amenities = get_amenities(city_name.value)

            spinner.update("Data download complete!")
            download_success = True
        except Exception as e:
            spinner.update(f"Error: {e}")
            download_success = False
            graph = None
            boundary = None
            amenities = {}

    mo.md(f"### Download Status: {'✅ Success' if download_success else '❌ Failed'}")

    return amenities, boundary, download_success, graph


@app.cell
def _(amenities, boundary, download_success, mo):
    if not download_success:
        mo.stop()

    mo.md("### Downloaded Data Summary")

    summary_data = {
        "Amenity Type": [],
        "Count": [],
    }

    for name, gdf in amenities.items():
        summary_data["Amenity Type"].append(name.capitalize())
        summary_data["Count"].append(len(gdf))

    summary_df = pd.DataFrame(summary_data)
    mo.hstack([
        mo.md(f"**City boundary:** {len(boundary)} polygon(s)"),
        mo.dataframe(summary_df),
    ])
    return (summary_df,)


@app.cell
def _(mo):
    mo.md("---")
    mo.md("## Step 2: Calculate 15-Minute Walking Accessibility")
    return


@app.cell
def _(mo):
    run_analysis = mo.ui.run_button(label="🧮 Run Accessibility Analysis")
    run_analysis
    return (run_analysis,)


@app.cell
def _(
    amenities,
    boundary,
    download_success,
    graph,
    grid_resolution,
    mo,
    run_analysis,
    selected_amenities,
    time_threshold,
):
    if not run_analysis.value or not download_success:
        mo.stop()

    # Filter amenities based on selection
    filtered_amenities = {
        k: v for k, v in amenities.items()
        if k in selected_amenities
    }

    with mo.status.spinner("Calculating accessibility scores...") as spinner:
        # Get bounds from boundary
        bounds = boundary.total_bounds

        spinner.update(f"Generating {grid_resolution.value}x{grid_resolution.value} accessibility grid...")

        accessibility_df = generate_grid_accessibility(
            bounds=tuple(bounds),
            amenities=filtered_amenities,
            graph=graph,
            grid_resolution=grid_resolution.value,
            time_threshold_minutes=time_threshold.value,
        )

        spinner.update(f"Analyzed {len(accessibility_df)} grid points")

    mo.md(f"### Analysis Complete: {len(accessibility_df)} points evaluated")
    mo.md(f"**Mean accessibility score:** {accessibility_df['overall_score'].mean():.1f}/100")

    return accessibility_df, bounds, filtered_amenities


@app.cell
def _(accessibility_df, mo, px):
    mo.md("### Accessibility Score Distribution")

    # Create histogram
    fig = px.histogram(
        accessibility_df,
        x="overall_score",
        nbins=20,
        title="Distribution of Accessibility Scores",
        labels={"overall_score": "Accessibility Score (0-100)"},
        color_discrete_sequence=["#1a9850"],
    )
    fig.add_vline(x=80, line_dash="dash", line_color="green", annotation_text="Good (80+)")
    fig.add_vline(x=40, line_dash="dash", line_color="red", annotation_text="Poor (<40)")

    mo.plotly(fig)
    return (fig,)


@app.cell
def _(mo):
    mo.md("---")
    mo.md("## Step 3: Visualize Results")
    return


@app.cell
def _(accessibility_df, filtered_amenities, mo):
    if len(accessibility_df) == 0:
        mo.md("⚠️ No accessibility data to visualize yet. Run the analysis first.")
        mo.stop()

    mo.md("### Interactive Accessibility Map")

    map_fig = create_accessibility_map(
        accessibility_df,
        amenities=filtered_amenities,
    )

    mo.plotly(map_fig)
    return (map_fig,)


@app.cell
def _(mo):
    mo.md("---")
    mo.md("## Step 4: Transit Equity by Neighborhood (Optional)")
    return


@app.cell
def _(mo):
    mo.md("""
    To calculate equity metrics, you'll need to provide a neighborhoods GeoJSON file
    with neighborhood boundaries and a 'name' column.

    **Skip this step** if you don't have neighborhood data.
    """)

    upload_neighborhoods = mo.ui.file(
        label="Upload neighborhoods GeoJSON (optional)",
        accept=".geojson,.json",
    )
    upload_neighborhoods
    return (upload_neighborhoods,)


@app.cell
def _(gpd, mo, upload_neighborhoods):
    if not upload_neighborhoods.value:
        neighborhoods = None
        have_neighborhoods = False
    else:
        try:
            neighborhoods = gpd.read_file(upload_neighborhoods.value[0].path)
            have_neighborhoods = True
            mo.md(f"✅ Loaded {len(neighborhoods)} neighborhoods")
        except Exception as e:
            mo.md(f"❌ Error loading neighborhoods: {e}")
            neighborhoods = None
            have_neighborhoods = False

    return have_neighborhoods, neighborhoods


@app.cell
def _(
    accessibility_df,
    calculate_equity_metrics,
    have_neighborhoods,
    mo,
    neighborhoods,
):
    if not have_neighborhoods or len(accessibility_df) == 0:
        mo.md("ℹ️ Skip this step or run accessibility analysis first.")
        mo.stop()

    equity_df = calculate_equity_metrics(accessibility_df, neighborhoods)

    mo.md("### Transit Equity Metrics by Neighborhood")
    mo.dataframe(equity_df)

    # Show bar chart of mean scores
    fig = px.bar(
        equity_df.sort_values("mean_score"),
        x="mean_score",
        y="neighborhood",
        orientation="h",
        title="Mean Accessibility Score by Neighborhood",
        color="mean_score",
        color_continuous_scale="RdYlGn",
        range_color=[0, 100],
    )
    mo.plotly(fig)

    return equity_df, fig


@app.cell
def _(mo):
    mo.md("---")
    mo.md("## Step 5: Export Processed Data")
    return


@app.cell
def _(accessibility_df, mo):
    # Check if we have data to save
    can_save = len(accessibility_df) > 0

    if not can_save:
        mo.md("⚠️ No data to save. Run accessibility analysis first.")
        mo.stop()

    save_path = mo.ui.text(
        value="data/processed/accessibility_data.parquet",
        label="Save path (relative to project root):",
    )
    save_path
    return can_save, save_path


@app.cell
def _(accessibility_df, mo, project_root, save_path):
    save_button = mo.ui.run_button(label="💾 Save Data to Parquet")
    save_button
    return (save_button,)


@app.cell
def _(
    accessibility_df,
    mo,
    project_root,
    save_button,
    save_path,
):
    if not save_button.value:
        mo.md("Click 'Save Data' to export processed accessibility data.")
        mo.stop()

    try:
        full_path = project_root / save_path.value
        full_path.parent.mkdir(parents=True, exist_ok=True)

        accessibility_df.to_parquet(full_path)
        mo.md(f"✅ **Saved:** `{full_path}` ({len(accessibility_df)} records)")
    except Exception as e:
        mo.md(f"❌ **Error saving:** {e}")

    return (full_path,)


@app.cell
def _(mo):
    mo.md("""
    ---
    ## 📊 Next Steps

    After saving the data, run the Streamlit dashboard:

    ```bash
    streamlit run dashboard/app.py
    ```

    Or export this notebook as a script for batch processing:

    ```bash
    marimo export html notebooks/data_processing.py -o report.html
    ```
    """)
    return


if __name__ == "__main__":
    app.run()
