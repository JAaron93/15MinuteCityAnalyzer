import marimo

__generated_with = "0.8.0"
app = marimo.App(width="full")

@app.cell
def __():
    import marimo as mo
    return mo,

@app.cell
def __(mo):
    mo.md("# 15-Minute City & Transit Equity Analyzer Pipeline")
    return

@app.cell
def __(mo):
    # Configuration Parameters
    city_name = "Corona"
    state = "CA"
    # Need a bounding box for OSM and Census
    # For Corona, CA approx bbox: (33.91, 33.82, -117.50, -117.65)
    # format: (north, south, east, west)
    bbox = (33.91, 33.82, -117.50, -117.65)
    output_path = "data/processed/processed_equity_data.parquet"
    
    mo.md(f"**City:** {city_name}, {state}  \n**Output Path:** {output_path}  \n**Bbox:** {bbox}")
    return bbox, city_name, output_path, state

@app.cell
def __():
    import logging
    import geopandas as gpd
    import networkx as nx
    import matplotlib.pyplot as plt
    import datetime
    
    # Internal pipeline modules
    from src.pipeline.census_fetcher import CensusFetcher
    from src.pipeline.osm_fetcher import OSMFetcher
    from src.pipeline.crs_utils import determine_utm_zone, transform_to_utm, transform_to_wgs84
    from src.pipeline.isochrone import calculate_all_isochrones
    from src.pipeline.scoring import spatial_join_amenities, calculate_accessibility_score, assign_equity_category
    from src.pipeline.data_validator import DataValidator
    from src.pipeline.exporter import export_to_geoparquet
    
    return (
        CensusFetcher,
        DataValidator,
        OSMFetcher,
        assign_equity_category,
        calculate_accessibility_score,
        calculate_all_isochrones,
        datetime,
        determine_utm_zone,
        export_to_geoparquet,
        gpd,
        logging,
        nx,
        plt,
        spatial_join_amenities,
        transform_to_utm,
        transform_to_wgs84,
    )

@app.cell
def __(logging):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logger = logging.getLogger(__name__)
    return logger,

@app.cell
def __(CensusFetcher, bbox, logger, state):
    logger.info("Fetching Census demographics...")
    census_fetcher = CensusFetcher()
    block_groups = census_fetcher.fetch_data(state, bbox)
    logger.info(f"Fetched {len(block_groups)} block groups.")
    return block_groups, census_fetcher

@app.cell
def __(OSMFetcher, bbox, logger):
    logger.info("Fetching OSM amenities...")
    osm_fetcher = OSMFetcher()
    amenities = osm_fetcher.fetch_amenities(bbox)
    logger.info(f"Fetched {len(amenities)} amenities.")
    return amenities, osm_fetcher

@app.cell
def __(bbox, logger, osm_fetcher):
    logger.info("Fetching street network...")
    network = osm_fetcher.fetch_street_network(bbox)
    logger.info(f"Fetched network with {len(network.nodes)} nodes and {len(network.edges)} edges.")
    return network,

@app.cell
def __(amenities, bbox, block_groups, determine_utm_zone, logger, transform_to_utm):
    logger.info("Transforming CRS to local UTM...")
    utm_crs = determine_utm_zone(bbox)
    
    bg_utm = transform_to_utm(block_groups, utm_crs)
    amenities_utm = transform_to_utm(amenities, utm_crs)
    
    logger.info(f"Projected to {utm_crs}.")
    return amenities_utm, bg_utm, utm_crs

@app.cell
def __(amenities, calculate_all_isochrones, logger, network):
    logger.info("Calculating 15-minute isochrones...")
    # isochrones generation uses the WGS84 graph and WGS84 amenities directly
    isochrones = calculate_all_isochrones(
        graph=network,
        amenities=amenities,
        walk_time_minutes=15,
        max_workers=4
    )
    logger.info(f"Generated {len(isochrones)} isochrones.")
    return isochrones,

@app.cell
def __(isochrones, logger, transform_to_utm, utm_crs):
    logger.info("Transforming isochrones to UTM...")
    isochrones_utm = transform_to_utm(isochrones, utm_crs)
    return isochrones_utm,

@app.cell
def __(
    amenities_utm,
    assign_equity_category,
    bg_utm,
    calculate_accessibility_score,
    isochrones_utm,
    logger,
    spatial_join_amenities,
):
    logger.info("Performing spatial join and scoring...")
    joined_data = spatial_join_amenities(bg_utm, isochrones_utm, amenities_utm)
    scored_data = calculate_accessibility_score(joined_data)
    final_data, thresholds_metadata = assign_equity_category(scored_data)
    logger.info("Scoring complete.")
    return final_data, joined_data, scored_data, thresholds_metadata

@app.cell
def __(DataValidator, final_data, logger, transform_to_wgs84):
    logger.info("Validating and transforming back to WGS84...")
    output_data = transform_to_wgs84(final_data)
    
    # Data validation
    DataValidator.validate_crs(output_data, "EPSG:4326")
    DataValidator.validate_geometries(output_data)
    
    logger.info("Validation complete.")
    return output_data,

@app.cell
def __(block_groups, plt):
    # Visualization: Fetched block groups
    fig_bg, ax_bg = plt.subplots(figsize=(10, 8))
    block_groups.plot(ax=ax_bg, edgecolor="white", column="population", cmap="Blues", legend=True)
    ax_bg.set_title("Census Block Groups by Population")
    plt.close(fig_bg)
    return ax_bg, fig_bg

@app.cell
def __(amenities, plt):
    # Visualization: Amenities
    fig_am, ax_am = plt.subplots(figsize=(10, 8))
    amenities.plot(ax=ax_am, column="amenity_type", legend=True, markersize=10, alpha=0.7)
    ax_am.set_title("Fetched Amenities by Type")
    plt.close(fig_am)
    return ax_am, fig_am

@app.cell
def __(isochrones, plt):
    # Visualization: Isochrones
    fig_iso, ax_iso = plt.subplots(figsize=(10, 8))
    isochrones.plot(ax=ax_iso, alpha=0.3, edgecolor="k", column="amenity_type", legend=True)
    ax_iso.set_title("15-Minute Walking Isochrones")
    plt.close(fig_iso)
    return ax_iso, fig_iso

@app.cell
def __(output_data, plt):
    # Visualization: Accessibility Scores Histogram
    fig_hist, ax_hist = plt.subplots(figsize=(8, 6))
    output_data["accessibility_score"].hist(ax=ax_hist, bins=20, color="skyblue", edgecolor="k")
    ax_hist.set_title("Accessibility Score Distribution")
    ax_hist.set_xlabel("Score")
    ax_hist.set_ylabel("Count")
    plt.close(fig_hist)
    return ax_hist, fig_hist

@app.cell
def __(datetime, export_to_geoparquet, logger, output_data, output_path, thresholds_metadata):
    logger.info("Exporting to GeoParquet...")
    
    metadata = {
        "processing_date": datetime.datetime.now().isoformat(),
        "data_sources": "Census API, OpenStreetMap",
        **thresholds_metadata
    }
    
    export_to_geoparquet(output_data, output_path, metadata=metadata)
    logger.info("Pipeline execution complete.")
    return metadata,

if __name__ == "__main__":
    app.run()
