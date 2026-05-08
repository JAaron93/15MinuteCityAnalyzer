import branca.colormap as cm
import folium
import geopandas as gpd


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
    # Centroid for initial view
    centroid = data.geometry.unary_union.centroid
    m = folium.Map(
        location=[centroid.y, centroid.x], zoom_start=12, tiles="CartoDB positron"
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
            return colormap(x["properties"]["accessibility_score"])

    else:  # median_income
        vmin = data["median_income"].min()
        vmax = data["median_income"].max()
        colormap = cm.LinearColormap(
            colors=["#f7fbff", "#08306b"],  # Blue scale
            vmin=vmin,
            vmax=vmax,
            caption="Median Household Income ($)",
        )

        def fill_color_fn(x):
            return colormap(x["properties"]["median_income"])

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

    # Add attribution
    folium.TileLayer(
        tiles="OpenStreetMap",
        attr=(
            '&copy; <a href="https://www.openstreetmap.org/copyright">'
            "OpenStreetMap</a> contributors"
        ),
    ).add_to(m)

    return m
