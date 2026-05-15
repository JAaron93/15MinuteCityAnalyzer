# 15-Minute City & Transit Equity Analyzer: Architecture

## High-Level Architecture

The 15-Minute City & Transit Equity Analyzer is a monolithic data processing pipeline and interactive dashboard designed to evaluate urban accessibility and demographic equity.

The system is composed of two primary layers:
1. **Data Processing Pipeline (`src/pipeline/`)**: An offline batch-processing layer that fetches, processes, and joins spatial and demographic data.
2. **Interactive Dashboard (`src/dashboard/`)**: A Streamlit-based web application that visualizes the pre-processed data.

## Pipeline Architecture

The pipeline is designed around a modular extraction, transformation, and load (ETL) approach:

*   **Extraction Layer**:
    *   `census_fetcher.py`: Retrieves demographic data (population, median income) and block group boundaries via the Census Bureau API (`cenpy`).
    *   `osm_fetcher.py`: Retrieves points of interest (amenities) and the walkable street network via OpenStreetMap (`osmnx`). Uses bounding box tiling for large areas to prevent memory exhaustion and API timeouts.
*   **Transformation Layer**:
    *   `crs_utils.py`: Manages deterministic Coordinate Reference System (CRS) transformations. All spatial operations are performed in a dynamically determined local UTM zone to ensure accurate distance and area calculations.
    *   `isochrone.py`: Calculates 15-minute walking catchments around amenities using network analysis (Dijkstra's algorithm) and convex hulls.
    *   `scoring.py`: Performs an area-overlap spatial join between Census block groups and amenity isochrones. Computes a capped, weighted accessibility score and categorizes equity based on predefined thresholds.
    *   `tile_merger.py`: Recombines tiled OSM data, deduplicating POIs and topologically re-stitching network graphs.
*   **Load Layer**:
    *   `exporter.py`: Serializes the final enriched GeoDataFrame to GeoParquet format, appending strict metadata schemas (e.g., threshold configurations, execution timestamps) for dashboard consumption.

## Dashboard Architecture

The dashboard is a stateless web application built on Streamlit:
*   **app.py**: The entry point, handling layout, user inputs, and overall state.
*   **map_renderer.py**: Utilizes `folium` to render an interactive choropleth map representing block-group accessibility scores or demographic data.
*   **metrics.py**: Computes and displays aggregated KPIs (e.g., average accessibility score, equity disparities, demographic distributions).
*   **charts.py**: Renders statistical charts (e.g., scatter plots of income vs. access) using `plotly` or `altair`.

## Error Handling & Resiliency
The architecture employs an active `retry_with_policy` decorator across all external API calls. This decorator implements exponential backoff with jitter to gracefully handle transient network failures or rate limiting from the Census or OSM APIs.

## Data Persistence
Pre-computed analysis results are stored locally in GeoParquet format (`data/processed/`). This allows the dashboard to load massive spatial datasets rapidly without requiring on-the-fly network or spatial computation.
