# Data Sources

The 15-Minute City & Transit Equity Analyzer relies on two primary public data sources to compute accessibility metrics and demographic equity overlays.

## 1. US Census Bureau (American Community Survey)

We utilize the 5-Year American Community Survey (ACS) to obtain demographic data at the block group level.

*   **API Wrapper**: `cenpy`
*   **Default Vintage**: 2021 (configurable via `pipeline_config.yaml`)
*   **Geographic Level**: Block Group
*   **Metrics Fetched**:
    *   `B01003_001E`: Total Population. Used to weight equity metrics and filter unpopulated block groups.
    *   `B19013_001E`: Median Household Income. Used as the primary socioeconomic indicator for evaluating transit equity disparities.
*   **Geometry**: Census block group boundary polygons (fetched concurrently with demographic attributes).
*   **Limitations**: Data is subject to Census API rate limits. Multicounty bounding boxes involve joining data across distinct FIPS county fetches.

## 2. OpenStreetMap (OSM)

We utilize the OSM Overpass API to fetch walkable street networks and points of interest (amenities).

*   **API Wrapper**: `osmnx`
*   **Data Types**:
    *   **Street Network**: Walkable graph edges (`network_type="walk"`). Excludes highways and restricted pathways.
    *   **Amenities (POIs)**: Queried by specific bounding boxes and categorized into four core types:
        1.  **Grocery**: `shop=supermarket,convenience,deli`
        2.  **Healthcare**: `amenity=hospital,clinic,doctors,pharmacy`
        3.  **Transit**: `amenity=bus_station,train_station,subway_entrance`, `highway=bus_stop`
        4.  **Other**: `amenity=library,post_office,school`, `leisure=park,playground`
*   **Usage**: The street network is used to calculate Dijkstra shortest paths and isochrones (reachable areas) extending out from each amenity node.
*   **Limitations**: Massive bounding boxes may crash the Overpass API. We implement a custom spatial tiling algorithm (`tile_merger.py`) to subdivide the query bounding box and seamlessly restitch the resulting network graphs.

## Data Validation

Data integrity is rigorously enforced by `data_validator.py`.
*   Census data is checked for valid populations (non-negative) and properly handled nulls for income.
*   OSM data is checked to ensure spatial references are correctly aligned to `EPSG:4326` before projection, and all amenities have correctly parsed geographic coordinates.
