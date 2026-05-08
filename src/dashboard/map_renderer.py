import branca.colormap as cm
import folium
import geopandas as gpd
import pandas as pd


def create_choropleth_map(
    data: gpd.GeoDataFrame, metric: str = "accessibility_score"
) -> folium.Map:
    """
    Render interactive choropleth map using Folium.

    Args:
        data (gpd.GeoDataFrame): The filtered dataset.
        metric (str): 'accessibility_score' or 'median_income'.

    Returns:
        folium.Map: The Folium map object.
    """
    if data.empty:
        raise ValueError("Cannot create map from empty dataset")

    # Centroid for initial view
    centroid = data.geometry.unary_union.centroid
    m = folium.Map(
        location=[centroid.y, centroid.x],
        zoom_start=12,
        tiles="CartoDB positron"
    )

    # Define colormap
    if metric == "accessibility_score":
        colormap = cm.LinearColormap(
            colors=["red", "yellow", "green"],
            vmin=0,
            vmax=100,
            caption="Accessibility Score",
        )

        def fill_color_fn(x):
            score = x["properties"].get("accessibility_score", 0)
            return colormap(score)

    else:  # median_income
        vmin = data["median_income"].min(skipna=True)
        vmax = data["median_income"].max(skipna=True)
        if pd.isna(vmin) or pd.isna(vmax):
            raise ValueError("All median_income values are null")
        if vmin == vmax:
            vmax = vmin + 1  # Avoid division by zero in gradient
        colormap = cm.LinearColormap(
            colors=["#f7fbff", "#08306b"],  # Blue scale
            vmin=vmin,
            vmax=vmax,
            caption="Median Household Income ($)",
        )

        def fill_color_fn(x):
            income = x["properties"].get("median_income", vmin)
            return colormap(income)

    # Add GeoJson with tooltips
    folium.GeoJson(
        data,
        style_function=lambda x: {
            "fillColor": fill_color_fn(x),
            "color": "black",
            "weight": 1,
            "fillOpacity": 0.7,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=[
                "geoid",
                "population",
                "median_income",
                "accessibility_score",
                "equity_category",
            ],
            aliases=[
                "GEOID:",
                "Population:",
                "Median Income ($):",
                "Access Score:",
                "Category:",
            ],
            localize=True,
        ),
    ).add_to(m)

    # Add colormap to map
    colormap.add_to(m)

    return m
