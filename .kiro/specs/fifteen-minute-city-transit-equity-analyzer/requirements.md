# Requirements Document: 15-Minute City & Transit Equity Analyzer

## 1. Functional Requirements

### 1.1 Data Acquisition

**FR-1.1.1**: The system SHALL fetch Census block group demographic data (population, median income) for a specified city and state using the Census API or cenpy library.

**FR-1.1.2**: The system SHALL download points of interest (POIs) including grocery stores, healthcare facilities, and public transit stops from OpenStreetMap using OSMnx for a specified bounding box.

**FR-1.1.3**: The system SHALL download the walkable street network for the target area using OSMnx with `network_type='walk'`.

**FR-1.1.4**: The system SHALL handle API failures gracefully with retry logic applying to all external API calls (Census API, Overpass API via OSMnx). The retry behaviour SHALL conform to the following parameters, all configurable via `pipeline_config.yaml` (`retry_policy`):

- **Target attempts**: 3 (i.e., 1 initial attempt + 2 retries). This is a target, not a guarantee — the maximum total retry duration (below) is a hard cap that may stop retries early before all 3 attempts are made.
- **Per-request timeout**: **10 seconds** — each individual HTTP request SHALL be cancelled and treated as a failure if no response is received within this duration.
- **Maximum total retry duration**: **60 seconds hard cap** on total elapsed time measured from the start of the first attempt. The system SHALL NOT start any new attempt (initial or retry) if doing so would cause the elapsed time to exceed this cap. The cap includes the duration of any in-flight request — if a request is still running when the cap is reached, it SHALL be cancelled and the final error raised immediately.
- **Backoff formula**: `delay = base_delay × multiplier ^ attempt_number` where:
  - `base_delay` = **500 ms** (delay before the first retry)
  - `multiplier` = **2.0** (doubles the delay on each subsequent retry)
  - `attempt_number` starts at 0 for the first retry (giving delays of 500 ms, 1 000 ms, 2 000 ms, …)
- **Jitter**: Each computed delay SHALL have a random jitter of ±20 % applied (i.e., `delay × uniform(0.8, 1.2)`) to prevent thundering-herd effects when multiple pipeline runs execute concurrently.
- **HTTP status handling**:
  - **Non-retryable — raise immediately** with a descriptive message: HTTP 400 (Bad Request), 401 (Unauthorized), 403 (Forbidden), 404 (Not Found). These indicate client-side or auth errors that will not resolve on retry.
  - **Retryable**: HTTP 5xx (server errors) — apply backoff and retry up to the target attempts / duration cap.
  - **Retryable with rate-limit awareness**: HTTP 429 (Too Many Requests) — treat as retryable; if the response includes a `Retry-After` header, use its value (in seconds) as the delay instead of the computed backoff delay (still apply jitter on top). If `Retry-After` exceeds the remaining time under the 60 s cap, raise immediately rather than waiting.
- **Logging**: Each retry attempt SHALL be logged at WARNING level with the attempt number, elapsed time, computed delay, HTTP status code, and the error that triggered the retry.

**FR-1.1.5** *(Bounding Box Validation — extends FR-1.1.2 and FR-1.1.3)*: Before issuing any OSMnx download (POIs or street network), the system SHALL validate the derived or user-supplied bounding box against the following limits, configurable via `pipeline_config.yaml` (`bbox_limits`):

- Maximum edge length: **1.0 decimal degrees** (~111 km) on any single side
- Maximum area: **1.0 square decimal degrees** (~12,000 km²)

If the bounding box exceeds either limit the system SHALL:
1. Log a descriptive error identifying which limit was exceeded and by how much
2. Raise a `BoundingBoxTooLargeError` with an actionable message (e.g., "Bounding box area 0.72 sq° exceeds limit 0.5 sq°; reduce the target area or enable tiling")
3. Reject the request — it SHALL NOT silently proceed with an oversized download that risks memory overflow or Overpass API timeout

**FR-1.1.6** *(Bounding Box Tiling — extends FR-1.1.5)*: The system SHALL support an optional automatic tiling strategy for bounding boxes that exceed the size limits defined in FR-1.1.5. When tiling is enabled (`pipeline_config.yaml`: `bbox_limits.enable_tiling: true`):

1. **Grid subdivision** — divide the oversized bounding box into an equal-grid of *nx × ny* non-overlapping tiles, where *nx* and *ny* are the smallest integers such that every tile's edge length ≤ `bbox_limits.max_edge_degrees` and area ≤ `bbox_limits.max_area_sq_degrees`. Tile IDs SHALL be assigned in row-major order (left-to-right, top-to-bottom) starting at `tile_0_0`.

2. **Per-tile downloads** — execute OSMnx POI and street-network downloads independently for each tile. Tiles are processed sequentially by default; parallel execution is optional and controlled by `bbox_limits.tiling.parallel: true`.

3. **Merge and deduplication rules** — after all tile downloads complete, merge results using the following geometry-type-specific rules:
   - **Point features (POIs)**: deduplicate by `osm_id`; keep a single canonical record (first occurrence in tile-ID order). Discard all duplicates.
   - **Polygon features**: deduplicate by `osm_id` using the same first-occurrence rule. Where the same polygon spans a tile boundary and is returned by multiple tiles, take the union of the partial geometries to reconstruct the full polygon.
   - **Line/network edges**: deduplicate edges by `osm_id`; where an edge is split at a tile boundary, rejoin the split segments by matching `osm_id` and reconnecting endpoints within a tolerance of 1 × 10⁻⁶ degrees. Merge nodes that are topologically equivalent (same coordinates within tolerance) to preserve graph connectivity. This tile-merge routine SHALL be implemented in `src/pipeline/tile_merger.py`.

4. **Failure threshold** — if any tile download fails, log the failure (tile ID, error message) and skip that tile. After all tiles are attempted:
   - Compute `skip_fraction = skipped_tiles / total_tiles`.
   - If `skip_fraction > bbox_limits.tiling.failure_threshold` (default: **0.20**, configurable), raise a `TilingFailureError` listing all skipped tile IDs and the skip fraction.
   - If `skip_fraction ≤ failure_threshold`, continue with the available data.
   - All skipped tile IDs SHALL be logged at WARNING level AND written to the GeoParquet output metadata under the key `skipped_tiles`.

When tiling is disabled (default), the system SHALL reject oversized requests per FR-1.1.5.

**FR-1.1.7** *(Multi-County Census Queries — extends FR-1.1.1)*: The system SHALL handle cities that span multiple counties using the following steps:

1. **Derive county FIPS codes** — before issuing any Census queries, determine which counties intersect the analysis bounding box by spatially intersecting the bounding box against a county polygon dataset (e.g., Census TIGER/Line county boundaries fetched via `cenpy` or a bundled lightweight county GeoJSON). The result is the set of `(state_fips, county_fips)` pairs to query. This step SHALL be logged at INFO level listing all identified county FIPS codes.
2. **Issue per-county queries** — issue a separate Census API query per county using `for=block group:* in state:{state} in county:{county}` and concatenate all results into a single GeoDataFrame.
3. **Deduplicate by `geoid`** — block groups returned by more than one county query (e.g., at county boundaries) SHALL be deduplicated using the following deterministic strategy:
   - Keep the first-occurrence record for a given `geoid` (i.e., the record from the lowest-sorted county FIPS code).
   - If any non-geometry attribute value differs between duplicate records for the same `geoid`, log a WARNING identifying the `geoid`, the conflicting field names, and the values from each source county query.
   - Geometry is taken from the first-occurrence record; conflicting geometries are not merged.
4. **Handle missing counties** — if Census data is unavailable for one or more counties (API returns no records), log a WARNING identifying the missing county FIPS codes and continue with the available data. The system SHALL NOT silently drop block groups without logging.
5. **Handle total failure** — if no Census data is returned for any county, raise `CensusDataUnavailableError` with the full list of queried `(state_fips, county_fips)` pairs so the caller can diagnose which counties were attempted.

### 1.2 Spatial Analysis

**FR-1.2.1**: The system SHALL calculate 15-minute walking isochrones around each amenity using network analysis. The default walking speed SHALL be **4.5 km/h**, which is configurable via `pipeline_config.yaml` (`walk_speed_kmh`). The plausible range is 4.0–5.5 km/h for healthy adults; lower values (e.g., 3.0–3.5 km/h) should be used for analyses targeting elderly populations, children, or hilly terrain.

**FR-1.2.2**: The system SHALL perform spatial joins between Census block groups and 15-minute accessibility buffers using an **area-overlap threshold**: a block group is counted as having access to an amenity only when `area(intersection(block_group, isochrone)) ≥ MIN_OVERLAP_FRACTION × area(block_group)`. The default `MIN_OVERLAP_FRACTION` SHALL be **0.10** (10%) and SHALL be configurable via `pipeline_config.yaml` (`spatial_join.min_overlap_fraction`). All area calculations SHALL be performed in the **local UTM projection**, determined deterministically as follows: compute the centroid of the analysis bounding box in WGS84, then derive the UTM CRS using `geopandas.estimate_utm_crs(latitude, longitude)` (or equivalent). Both the block group geometries and the isochrone geometries SHALL be reprojected to this centroid-derived UTM CRS before computing `area(intersection(...))` and `area(block_group)`. The same UTM CRS SHALL be used consistently for all area calculations within a single pipeline run.

**FR-1.2.3**: The system SHALL calculate an accessibility score (0–100) for each block group using the canonical capped weighted formula:

```
raw_score = (
    0.35 * min(grocery_count,    5)  +
    0.30 * min(healthcare_count, 3)  +
    0.25 * min(transit_count,   10)  +
    0.10 * min(other_count,      5)
)

accessibility_score = normalize(raw_score)
```

Where:
- `raw_score` is the **capped weighted sum prior to any normalization**. It is the quantity used for all monotonicity checks (Property 2) and SHALL be stored in the output GeoParquet as a separate column (see DR-3.2.1) for transparency and audit purposes.
- `normalize(x) = 100 × (x − city_min) / (city_max − city_min)` across all block groups, where `city_min` and `city_max` are the minimum and maximum `raw_score` values in the dataset.

**Normalization edge-case**: When `city_max == city_min` (i.e., all block groups have identical raw scores — possible for very small cities or datasets with a single block group), the division is undefined. In this case the system SHALL assign `accessibility_score = 50` to all block groups and log a WARNING stating that min-max normalization was skipped due to a degenerate score distribution.

**Configurability**: Both the per-type caps and the weights SHALL be read from `pipeline_config.yaml` at runtime:
- Weights: `scoring_weights` (keys: `grocery`, `healthcare`, `transit`, `other`; defaults: 0.35, 0.30, 0.25, 0.10)
- Caps: `scoring_caps` (keys: `grocery`, `healthcare`, `transit`, `other`; defaults: 5, 3, 10, 5)

Note: `total_amenities` is a display field and does not have a monotonic relationship with `accessibility_score` once any per-type cap is saturated. The OSM tags that populate each count field are defined in DR-3.1.5; `other_count` specifically covers the "other daily-need amenities" tag set listed there.

**FR-1.2.4**: The system SHALL assign equity categories ("High Access", "Medium Access", "Low Access") to each block group based on configurable accessibility score thresholds, and SHALL enforce the following validation workflow before finalising those thresholds for a given city run.

**Threshold bounds** (enforced at pipeline startup, before any scoring):
- `equity_thresholds.high_access_min` and `equity_thresholds.medium_access_min` SHALL both be in the range [0, 100].
- `equity_thresholds.high_access_min` SHALL be strictly greater than `equity_thresholds.medium_access_min`.
- If either constraint is violated the pipeline SHALL raise a `ThresholdConfigError` with a descriptive message and halt before processing.
- Default values: `high_access_min = 70`, `medium_access_min = 40` (configurable via `pipeline_config.yaml`).

**Mandatory percentile check** (run after scoring, before export):
- Compute the fraction of block groups in each category (High / Medium / Low).
- Each category SHALL contain at least **5 %** of block groups (configurable via `pipeline_config.yaml`: `equity_thresholds.min_category_fraction`, default 0.05).
- If any category falls below the minimum fraction, log a WARNING identifying the under-populated category and its actual fraction. The pipeline SHALL NOT halt — the warning is advisory — but the result SHALL be recorded as `"percentile_check": "WARN"` in the GeoParquet metadata.
- If all categories meet the minimum, record `"percentile_check": "PASS"`.

**Mandatory ±5-point sensitivity test** (run after scoring, before export):
- Re-assign equity categories using thresholds shifted by +5 points (`high_access_min + 5`, `medium_access_min + 5`) and again by −5 points (`high_access_min − 5`, `medium_access_min − 5`), clamped to [0, 100].
- For each shift, compute the fraction of block groups whose category is unchanged relative to the baseline assignment (`sensitivity_stability`).
- The stability SHALL meet or exceed a configurable pass threshold (`pipeline_config.yaml`: `equity_thresholds.sensitivity_stability_threshold`, default **0.90**, i.e., ≥ 90 % of block groups retain their category under both shifts).
- If either shift produces stability below the threshold, log a WARNING and record `"sensitivity_check": "WARN"` in the GeoParquet metadata; otherwise record `"sensitivity_check": "PASS"`.

**Metadata recording** (written to GeoParquet file metadata and logged at INFO level):
```
equity_thresholds.high_access_min        # final value used
equity_thresholds.medium_access_min      # final value used
equity_thresholds.percentile_check       # "PASS" or "WARN"
equity_thresholds.category_fractions     # {"High": x, "Medium": y, "Low": z}
equity_thresholds.sensitivity_check      # "PASS" or "WARN"
equity_thresholds.sensitivity_stability  # {"shift_plus5": s1, "shift_minus5": s2}
equity_thresholds.validated_at           # ISO-8601 timestamp of the pipeline run
```

**FR-1.2.5**: The system SHALL transform coordinate reference systems correctly: WGS84 for input/output, local UTM for distance calculations.

### 1.3 Data Processing Pipeline

**FR-1.3.1**: The system SHALL implement the data processing pipeline as a Marimo notebook (`pipeline.py`) that can be executed interactively or as a script.

**FR-1.3.2**: The system SHALL export the final processed dataset to GeoParquet format with snappy compression.

**FR-1.3.3**: The system SHALL preserve all geometries in WGS84 (EPSG:4326) coordinate reference system in the output file.

**FR-1.3.4**: The system SHALL include the following fields in the output dataset: geoid, geometry, population, median_income, raw_score, accessibility_score, grocery_count, healthcare_count, transit_count, other_count, total_amenities, equity_category.

**FR-1.3.5**: The system SHALL log processing progress and any errors encountered during pipeline execution.

### 1.4 Interactive Dashboard

**FR-1.4.1**: The system SHALL provide a Streamlit web application (`app.py`) that loads and displays the processed GeoParquet data.

**FR-1.4.2**: The system SHALL render an interactive choropleth map showing Census block groups colored by accessibility score or median income.

**FR-1.4.3**: The system SHALL provide a toggle control allowing users to switch between viewing "Accessibility Score" and "Median Income" on the map.

**FR-1.4.4**: The system SHALL display high-level equity metrics in a sidebar or panel, including:
- Percentage of population in low-access areas
- Percentage of low-income population in low-access areas
- Average accessibility score by income quartile
- Total number of block groups analyzed

**FR-1.4.5**: The system SHALL provide slider controls to filter the map by:
- Median income threshold
- Accessibility score range
- Population density (optional)

**FR-1.4.6**: The system SHALL update the map and metrics dynamically when filters are applied.

**FR-1.4.7**: The system SHALL cache the loaded GeoParquet data using Streamlit's `@st.cache_data` decorator to improve performance.

### 1.5 Visualization

**FR-1.5.1**: The system SHALL use Folium or PyDeck to render interactive maps with zoom, pan, and tooltip capabilities.

**FR-1.5.2**: The system SHALL display tooltips on map hover showing block group details (geoid, population, income, accessibility score).

**FR-1.5.3**: The system SHALL use an appropriate color scheme (e.g., RdYlGn) to represent accessibility scores, with green indicating high access and red indicating low access.

**FR-1.5.4**: The system SHALL include a map legend explaining the color scale and equity categories.

**FR-1.5.5**: The system SHALL include OpenStreetMap attribution in the map footer as required by ODbL license.

## 2. Non-Functional Requirements

### 2.1 Performance

**NFR-2.1.1**: The data processing pipeline SHALL complete execution for a medium-sized city (100k-500k population) within 20 minutes on a standard laptop (8GB RAM, 4 CPU cores).

**NFR-2.1.2**: The Streamlit dashboard SHALL load the GeoParquet data and render the initial map within 2 seconds (with caching enabled).

**NFR-2.1.3**: The dashboard SHALL update the map visualization within 500ms when filters are applied.

**NFR-2.1.4**: The dashboard SHALL respond to layer toggle actions within 300ms.

**NFR-2.1.5**: The final GeoParquet file SHALL be less than 50 MB to enable deployment on Streamlit Cloud free tier.

### 2.2 Scalability

**NFR-2.2.1**: The pipeline SHALL support processing cities with up to 1 million population without running out of memory on systems with 16GB RAM.

**NFR-2.2.2**: The pipeline SHALL implement chunked processing for large datasets to prevent memory overflow.

**NFR-2.2.3**: The system SHALL support parallel processing of isochrone calculations across multiple amenities to reduce processing time.

### 2.3 Reliability

**NFR-2.3.1**: The pipeline SHALL validate all input data (Census data, OSM data) for completeness and correctness before processing.

**NFR-2.3.2**: The pipeline SHALL handle missing or invalid geometries gracefully using repair techniques (e.g., `buffer(0)`).

**NFR-2.3.3**: The dashboard SHALL display a user-friendly error message if the GeoParquet file is not found, with instructions to run the pipeline first.

**NFR-2.3.4**: The system SHALL log all errors with sufficient detail to enable debugging (error type, parameters, stack trace).

### 2.4 Usability

**NFR-2.4.1**: The Streamlit dashboard SHALL provide a clean, professional user interface suitable for portfolio presentation.

**NFR-2.4.2**: The dashboard SHALL include clear labels and descriptions for all controls and metrics.

**NFR-2.4.3**: The dashboard SHALL be responsive and usable on desktop browsers (mobile optimization is optional).

**NFR-2.4.4**: The system SHALL provide comprehensive documentation in README.md explaining how to run the pipeline and launch the dashboard.

### 2.5 Maintainability

**NFR-2.5.1**: The codebase SHALL follow PEP 8 style guidelines for Python code.

**NFR-2.5.2**: The codebase SHALL include type hints for all function signatures.

**NFR-2.5.3**: The codebase SHALL include docstrings for all public functions and classes.

**NFR-2.5.4**: The codebase SHALL achieve at least 80% code coverage with unit tests.

**NFR-2.5.5**: The codebase SHALL use Black for code formatting and Ruff for linting.

### 2.6 Portability

**NFR-2.6.1**: The system SHALL run on Windows, macOS, and Linux operating systems.

**NFR-2.6.2**: The system SHALL use only cross-platform Python libraries.

**NFR-2.6.3**: The Streamlit dashboard SHALL be deployable to Streamlit Cloud without modification.

**NFR-2.6.4**: The system SHALL document all system dependencies (e.g., libspatialindex) required for installation.

### 2.7 Security

**NFR-2.7.1**: The system SHALL NOT collect, store, or transmit any personally identifiable information (PII).

**NFR-2.7.2**: The system SHALL use only publicly available data sources (Census Bureau, OpenStreetMap).

**NFR-2.7.3**: The system SHALL store Census API keys (if used) in environment variables, not in source code.

**NFR-2.7.4**: The system SHALL respect API rate limits for Census API (500 requests/day) and Overpass API (1 request/second).

**NFR-2.7.5**: The system SHALL validate and sanitize all user inputs (if extended to allow custom city selection).

### 2.8 Compliance

**NFR-2.8.1**: The system SHALL comply with OpenStreetMap's Open Database License (ODbL) by including proper attribution.

**NFR-2.8.2**: The system SHALL include license information for all third-party libraries in the documentation.

**NFR-2.8.3**: The system SHALL use only open-source libraries with permissive licenses (MIT, BSD, Apache 2.0).

## 3. Data Requirements

### 3.1 Input Data

**DR-3.1.1**: The system SHALL accept a city name and state as input parameters for the data pipeline.

**DR-3.1.2**: The system SHALL derive a bounding box from the city name or accept explicit bounding box coordinates.

**DR-3.1.3**: The system SHALL fetch Census data at the block group level (not tract or county level).

**DR-3.1.4**: The system SHALL fetch the following demographic fields from Census API:
- Total population (B01003_001E)
- Median household income (B19013_001E)

**DR-3.1.5**: The system SHALL fetch the following amenity types from OpenStreetMap:
- Grocery stores → `grocery_count` (OSM tags: `amenity=supermarket`, `shop=supermarket`, `shop=grocery`, `shop=convenience`)
- Healthcare facilities → `healthcare_count` (OSM tags: `amenity=hospital`, `amenity=clinic`, `amenity=doctors`, `amenity=pharmacy`)
- Public transit stops → `transit_count` (OSM tags: `public_transport=stop_position`, `highway=bus_stop`, `railway=station`, `railway=halt`)
- Other daily-need amenities → `other_count` (OSM tags: `amenity=school`, `amenity=library`, `amenity=community_centre`, `leisure=park`, `amenity=place_of_worship`). These represent secondary quality-of-life destinations that contribute the 0.10-weighted component of the accessibility score (FR-1.2.3). The tag set is configurable and may be extended without changing the scoring formula.

### 3.2 Output Data

**DR-3.2.1**: The system SHALL output a GeoParquet file containing all processed data with the following schema:
- geoid: string (12 characters)
- geometry: Polygon (WGS84)
- population: integer
- median_income: float
- raw_score: float — the capped weighted sum prior to normalization (`0.35*min(grocery,5) + 0.30*min(healthcare,3) + 0.25*min(transit,10) + 0.10*min(other,5)`); used for monotonicity validation and audit
- accessibility_score: float (0-100) — `normalize(raw_score)` across the city-wide distribution
- grocery_count: integer
- healthcare_count: integer
- transit_count: integer
- other_count: integer
- total_amenities: integer (display/filter field; validated to equal `grocery_count + healthcare_count + transit_count + other_count`; does **not** drive score monotonicity — use `raw_score` for that)
- equity_category: string

**DR-3.2.2**: The system SHALL ensure all geometries in the output file are valid (no self-intersections, no null geometries).

**DR-3.2.3**: The system SHALL include metadata in the GeoParquet file indicating the source data date and processing parameters.

### 3.3 Data Quality

**DR-3.3.1**: The system SHALL validate that all Census block groups have non-null geometries.

**DR-3.3.2**: The system SHALL validate that all accessibility scores are in the range [0, 100].

**DR-3.3.3**: The system SHALL validate that `total_amenities` equals the sum of `grocery_count + healthcare_count + transit_count + other_count` for every record. Note: `total_amenities` is a display/filter field; score monotonicity is validated over `raw_score` (the capped weighted sum), not over `total_amenities`.

**DR-3.3.4**: The system SHALL validate that equity categories are correctly assigned based on accessibility score thresholds.

**DR-3.3.5**: The system SHALL report data quality metrics (e.g., percentage of block groups with complete data) in the pipeline log.

## 4. Interface Requirements

### 4.1 User Interface

**IR-4.1.1**: The Streamlit dashboard SHALL provide the following UI components:
- Main map view (occupying majority of screen)
- Sidebar with controls and metrics
- Layer toggle buttons (Accessibility Score / Median Income)
- Filter sliders (income threshold, score range)
- Metrics panel (KPIs)

**IR-4.1.2**: The dashboard SHALL use a professional color scheme appropriate for data visualization.

**IR-4.1.3**: The dashboard SHALL include a title and brief description of the project at the top of the page.

**IR-4.1.4**: The dashboard SHALL include a footer with data sources, attribution, and license information.

### 4.2 API Interfaces

**IR-4.2.1**: The system SHALL interface with the Census API using the following endpoint:
- Base URL: https://api.census.gov/data/2021/acs/acs5
- Parameters: get, for, in (state, county)

**IR-4.2.2**: The system SHALL interface with OpenStreetMap via OSMnx library using the following functions:
- `osmnx.graph_from_bbox()` for street networks
- `osmnx.features_from_bbox()` for amenities

**IR-4.2.3**: The system SHALL handle API responses in JSON format (Census) and GeoJSON format (OSM).

### 4.3 File Interfaces

**IR-4.3.1**: The system SHALL read and write GeoParquet files using GeoPandas with PyArrow engine.

**IR-4.3.2**: The system SHALL use the following file paths:
- Input: None (data fetched from APIs)
- Output: `data/processed/processed_equity_data.parquet`

**IR-4.3.3**: The system SHALL create output directories automatically if they do not exist.

## 5. Constraint Requirements

### 5.1 Technical Constraints

**CR-5.1.1**: The system SHALL be implemented in Python 3.9 or higher.

**CR-5.1.2**: The system SHALL use Marimo for the data processing notebook environment.

**CR-5.1.3**: The system SHALL use Streamlit for the web dashboard framework.

**CR-5.1.4**: The system SHALL NOT require a backend server or database (Streamlit app runs entirely off the GeoParquet file).

**CR-5.1.5**: The system SHALL use GeoParquet as the data storage format (not Shapefile, GeoJSON, or PostGIS).

### 5.2 Resource Constraints

**CR-5.2.1**: The system SHALL be deployable on Streamlit Cloud free tier (1 GB RAM, 1 CPU).

**CR-5.2.2**: The system SHALL keep the GeoParquet file size under 50 MB to fit within Streamlit Cloud limits.

**CR-5.2.3**: The system SHALL run the data pipeline on a standard laptop without requiring cloud computing resources.

### 5.3 Regulatory Constraints

**CR-5.3.1**: The system SHALL comply with OpenStreetMap's Open Database License (ODbL).

**CR-5.3.2**: The system SHALL comply with Census Bureau's data usage terms (public domain, no restrictions).

**CR-5.3.3**: The system SHALL NOT violate any API terms of service (Census API, Overpass API).

## 6. Acceptance Criteria

### 6.1 Pipeline Acceptance Criteria

**AC-6.1.1**: The pipeline successfully fetches Census data for a test city (e.g., Corona, CA) without errors.

**AC-6.1.2**: The pipeline successfully downloads amenities and street network from OpenStreetMap for the test city.

**AC-6.1.3**: The pipeline calculates 15-minute isochrones for all amenities without errors.

**AC-6.1.4**: The pipeline performs spatial joins and calculates accessibility scores for all block groups.

**AC-6.1.5**: The pipeline exports a valid GeoParquet file with all required fields and correct data types.

**AC-6.1.6**: The pipeline completes execution within 20 minutes for a medium-sized city.

**AC-6.1.7**: The pipeline logs all processing steps and any errors encountered.

### 6.2 Dashboard Acceptance Criteria

**AC-6.2.1**: The dashboard successfully loads the GeoParquet file and displays the map without errors.

**AC-6.2.2**: The dashboard renders a choropleth map with block groups colored by accessibility score.

**AC-6.2.3**: The dashboard allows toggling between Accessibility Score and Median Income layers.

**AC-6.2.4**: The dashboard displays equity metrics (percentage in low-access areas, etc.) correctly.

**AC-6.2.5**: The dashboard filters the map correctly when income or score sliders are adjusted.

**AC-6.2.6**: The dashboard loads and renders the initial map within 2 seconds.

**AC-6.2.7**: The dashboard is deployable to Streamlit Cloud without modification.

### 6.3 Quality Acceptance Criteria

**AC-6.3.1**: All unit tests pass with at least 80% code coverage.

**AC-6.3.2**: All property-based tests pass, including: spatial integrity (area-overlap threshold correctly gates access), score monotonicity (higher `raw_score` implies higher `accessibility_score`), and CRS consistency (all output geometries in WGS84).

**AC-6.3.3**: The codebase passes Black formatting and Ruff linting checks.

**AC-6.3.4**: The codebase includes type hints for all functions and passes mypy type checking.

**AC-6.3.5**: The README.md includes complete setup and usage instructions.

### 6.4 Data Quality Acceptance Criteria

**AC-6.4.1**: All block groups in the output have valid (non-null) geometries.

**AC-6.4.2**: All accessibility scores are in the range [0, 100].

**AC-6.4.3**: All equity categories are correctly assigned based on score thresholds.

**AC-6.4.4**: The output file is in WGS84 (EPSG:4326) coordinate reference system.

**AC-6.4.5**: The output file size is less than 50 MB.

## 7. Assumptions and Dependencies

### 7.1 Assumptions

**A-7.1.1**: The user has a stable internet connection to fetch data from Census API and OpenStreetMap.

**A-7.1.2**: The target city has sufficient OpenStreetMap coverage for amenities and street networks.

**A-7.1.3**: Census data is available for the target city at the block group level.

**A-7.1.4**: The user has Python 3.9 or higher installed on their system.

**A-7.1.5**: The user has sufficient disk space to store the GeoParquet file (< 100 MB).

### 7.2 Dependencies

**D-7.2.1**: The system depends on the Census Bureau API being available and operational.

**D-7.2.2**: The system depends on the Overpass API (via OSMnx) being available and operational.

**D-7.2.3**: The system depends on Streamlit Cloud for deployment (or local Streamlit installation for local use).

**D-7.2.4**: The system depends on the following Python libraries: geopandas, osmnx, cenpy, networkx, pyarrow, marimo, streamlit, streamlit-folium, folium.

**D-7.2.5**: The system depends on the libspatialindex system library for spatial indexing (rtree).

## 8. Out of Scope

### 8.1 Features Not Included

**OS-8.1.1**: Real-time data updates (data is static after pipeline execution).

**OS-8.1.2**: User authentication or multi-user support.

**OS-8.1.3**: Database backend (all data stored in GeoParquet file).

**OS-8.1.4**: Mobile app or native mobile optimization.

**OS-8.1.5**: Biking or driving accessibility analysis (only walking).

**OS-8.1.6**: Temporal analysis (time-of-day variations in transit access).

**OS-8.1.7**: Routing or turn-by-turn directions.

**OS-8.1.8**: User-contributed data or crowdsourcing.

**OS-8.1.9**: Integration with other urban planning tools or GIS software.

**OS-8.1.10**: Automated report generation or PDF export.

### 8.2 Future Enhancements

**FE-8.2.1**: Support for multiple cities with a city selector dropdown.

**FE-8.2.2**: Comparison mode to compare accessibility across different cities.

**FE-8.2.3**: Historical trend analysis (comparing accessibility over multiple years).

**FE-8.2.4**: Integration with additional data sources (crime data, school quality, air quality).

**FE-8.2.5**: Advanced analytics (clustering, regression analysis, predictive modeling).

**FE-8.2.6**: Export functionality (download filtered data as CSV or GeoJSON).

**FE-8.2.7**: Customizable accessibility score weights (user-defined priorities).

**FE-8.2.8**: 3D visualization or terrain-aware routing.
