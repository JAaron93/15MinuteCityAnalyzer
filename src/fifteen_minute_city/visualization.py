"""Visualization utilities for accessibility analysis."""

from typing import Dict, Optional

import geopandas as gpd
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


COLOR_PALETTE = {
    "low": "#d73027",      # Red - poor accessibility
    "medium_low": "#fc8d59", # Orange
    "medium": "#fee08b",    # Yellow
    "medium_high": "#d9ef8b", # Light green
    "high": "#1a9850",      # Green - good accessibility
    "background": "#f8f9fa",
    "text": "#212529",
}


def create_accessibility_map(
    accessibility_df: pd.DataFrame,
    amenities: Optional[Dict[str, gpd.GeoDataFrame]] = None,
    center: Optional[Dict[str, float]] = None,
    zoom: int = 12,
) -> go.Figure:
    """Create an interactive accessibility heatmap.

    Args:
        accessibility_df: DataFrame with lat, lon, overall_score columns
        amenities: Optional dictionary of amenity GeoDataFrames
        center: Map center {'lat': x, 'lon': y}
        zoom: Initial zoom level

    Returns:
        Plotly figure object
    """
    fig = go.Figure()

    # Add accessibility heatmap
    fig.add_trace(
        go.Scattermapbox(
            lat=accessibility_df["lat"],
            lon=accessibility_df["lon"],
            mode="markers",
            marker=dict(
                size=8,
                color=accessibility_df["overall_score"],
                colorscale=[
                    [0, COLOR_PALETTE["low"]],
                    [0.25, COLOR_PALETTE["medium_low"]],
                    [0.5, COLOR_PALETTE["medium"]],
                    [0.75, COLOR_PALETTE["medium_high"]],
                    [1, COLOR_PALETTE["high"]],
                ],
                cmin=0,
                cmax=100,
                showscale=True,
                colorbar=dict(title="Accessibility Score"),
            ),
            text=[
                f"Score: {s:.1f}" for s in accessibility_df["overall_score"]
            ],
            hovertemplate="<b>Accessibility Score:</b> %{marker.color:.1f}<br>"
                         "<b>Lat:</b> %{lat:.4f}<br>"
                         "<b>Lon:</b> %{lon:.4f}<br>"
                         "<extra></extra>",
            name="Accessibility",
        )
    )

    # Add amenity markers if provided
    if amenities:
        colors = px.colors.qualitative.Set1
        for i, (name, gdf) in enumerate(amenities.items()):
            if gdf.empty:
                continue

            # Get points from geometries
            lats = []
            lons = []
            for geom in gdf.geometry:
                if geom is None:
                    continue
                if geom.geom_type == "Point":
                    lats.append(geom.y)
                    lons.append(geom.x)
                elif geom.geom_type in ["Polygon", "MultiPolygon"]:
                    centroid = geom.centroid
                    lats.append(centroid.y)
                    lons.append(centroid.x)

            if lats:
                fig.add_trace(
                    go.Scattermapbox(
                        lat=lats,
                        lon=lons,
                        mode="markers",
                        marker=dict(
                            size=10,
                            color=colors[i % len(colors)],
                            symbol="star",
                        ),
                        name=name.capitalize(),
                        hovertemplate=f"<b>{name.capitalize()}</b><br>"
                                     "<b>Lat:</b> %{lat:.4f}<br>"
                                     "<b>Lon:</b> %{lon:.4f}<br>"
                                     "<extra></extra>",
                    )
                )

    # Update layout
    if center:
        map_center = center
    elif not accessibility_df.empty:
        map_center = {
            "lat": accessibility_df["lat"].mean(),
            "lon": accessibility_df["lon"].mean(),
        }
    else:
        map_center = {"lat": 0, "lon": 0}

    fig.update_layout(
        mapbox=dict(
            style="carto-positron",
            center=map_center,
            zoom=zoom,
        ),
        margin=dict(l=0, r=0, t=30, b=0),
        title="15-Minute City Accessibility Map",
        legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01,
            bgcolor="rgba(255,255,255,0.8)",
        ),
    )

    return fig


def create_equity_chart(equity_df: pd.DataFrame) -> go.Figure:
    """Create equity comparison chart by neighborhood.

    Args:
        equity_df: DataFrame with neighborhood equity metrics

    Returns:
        Plotly figure with bar chart
    """
    # Sort by mean score for better visualization
    df_sorted = equity_df.sort_values("mean_score", ascending=True)

    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=("Mean Accessibility Score", "% High Accessibility (Score > 80)"),
    )

    # Mean scores
    fig.add_trace(
        go.Bar(
            y=df_sorted["neighborhood"],
            x=df_sorted["mean_score"],
            orientation="h",
            marker=dict(
                color=df_sorted["mean_score"],
                colorscale=[
                    [0, COLOR_PALETTE["low"]],
                    [0.5, COLOR_PALETTE["medium"]],
                    [1, COLOR_PALETTE["high"]],
                ],
                cmin=0,
                cmax=100,
            ),
            text=[f"{v:.1f}" for v in df_sorted["mean_score"]],
            textposition="outside",
            name="Mean Score",
        ),
        row=1,
        col=1,
    )

    # Percentage above 80
    fig.add_trace(
        go.Bar(
            y=df_sorted["neighborhood"],
            x=df_sorted["pct_above_80"],
            orientation="h",
            marker=dict(color=COLOR_PALETTE["medium_high"]),
            text=[f"{v:.1f}%" for v in df_sorted["pct_above_80"]],
            textposition="outside",
            name="% Above 80",
        ),
        row=1,
        col=2,
    )

    fig.update_layout(
        title="Transit Equity by Neighborhood",
        showlegend=False,
        height=max(400, len(df_sorted) * 30),
    )

    fig.update_xaxes(title_text="Score (0-100)", row=1, col=1, range=[0, 105])
    fig.update_xaxes(title_text="Percentage", row=1, col=2, range=[0, 105])

    return fig


def create_amenity_breakdown(accessibility_df: pd.DataFrame) -> go.Figure:
    """Create horizontal bar chart showing amenity access breakdown.

    Args:
        accessibility_df: DataFrame with amenities column containing dicts

    Returns:
        Plotly figure with horizontal bar chart
    """
    # Single pass to accumulate sums and counts for all amenity types
    sum_map = {}
    count_map = {}

    for amens in accessibility_df["amenities"]:
        if isinstance(amens, dict):
            for atype, val in amens.items():
                if isinstance(val, dict):
                    count_val = val.get("count", 0)
                else:
                    count_val = val

                sum_map[atype] = sum_map.get(atype, 0) + count_val
                count_map[atype] = count_map.get(atype, 0) + 1

    # Derive amenity_types and calculate averages
    amenity_types = sorted(list(sum_map.keys()))
    avg_counts = {atype: sum_map[atype] / count_map[atype] for atype in amenity_types}

    # Create horizontal bar chart
    fig = go.Figure(
        go.Bar(
            y=[a.capitalize() for a in amenity_types],
            x=[avg_counts[a] for a in amenity_types],
            orientation="h",
            marker=dict(color=px.colors.qualitative.Set2[:len(amenity_types)]),
            text=[f"{avg_counts[a]:.2f}" for a in amenity_types],
            textposition="outside",
        )
    )

    fig.update_layout(
        title="Average Accessible Amenities per Location",
        xaxis_title="Count",
        yaxis_title="Amenity Type",
        template="plotly_white",
        margin=dict(l=100, r=20, t=50, b=20),
    )

    return fig


def create_summary_stats(accessibility_df: pd.DataFrame) -> Dict[str, any]:
    """Generate summary statistics for dashboard display.

    Args:
        accessibility_df: DataFrame with accessibility scores

    Returns:
        Dictionary of summary statistics
    """
    scores = accessibility_df["overall_score"]

    return {
        "mean_score": scores.mean(),
        "median_score": scores.median(),
        "std_score": scores.std(),
        "min_score": scores.min(),
        "max_score": scores.max(),
        "pct_high_accessibility": (scores >= 80).mean() * 100,
        "pct_low_accessibility": (scores < 40).mean() * 100,
        "total_points_analyzed": len(accessibility_df),
    }
