# Implementation Tasks: 15-Minute City & Transit Equity Analyzer

## [x] 1. Project Setup and Configuration

- [x] 1.1 Create project directory structure
  - [x] 1.1.1 Create `data/raw` and `data/processed` directories
  - [x] 1.1.2 Create `src/pipeline` directory for pipeline modules
  - [x] 1.1.3 Create `src/dashboard` directory for Streamlit app modules
  - [x] 1.1.4 Create `tests` directory with subdirectories for unit and integration tests
  - [x] 1.1.5 Create `.streamlit` directory for Streamlit configuration

- [x] 1.2 Configure development environment
  - [x] 1.2.1 Update `requirements.txt` with all necessary dependencies (geopandas, osmnx, cenpy, marimo, streamlit, streamlit-folium, folium, pyarrow, networkx, rtree, shapely)
  - [x] 1.2.2 Add development dependencies (pytest, pytest-cov, hypothesis, black, mypy, ruff)
  - [x] 1.2.3 Create `.env.example` file for Census API key (optional)
  - [x] 1.2.4 Create `.gitignore` file to exclude venv, .env, __pycache__, .mypy_cache, data/raw/*
  - [x] 1.2.5 Create `pyproject.toml` for Black, Ruff, and mypy configuration
  - [x] 1.2.6 Create `pipeline_config.yaml` with all configurable parameters: `walk_speed_kmh`, `spatial_join.min_overlap_fraction`, `equity_thresholds.high_access_min`, `equity_thresholds.medium_access_min`, `equity_thresholds.min_category_fraction` (default 0.05), `equity_thresholds.sensitivity_stability_threshold` (default 0.90), `scoring_weights` (grocery/healthcare/transit/other), `scoring_caps` (grocery/healthcare/transit/other), `bbox_limits` (max_edge_degrees, max_area_sq_degrees, enable_tiling, `tiling.failure_threshold`, `tiling.parallel`), `retry_policy` (attempts, per_request_timeout_s, max_total_duration_s, base_delay_ms, multiplier, jitter_factor)

- [x] 1.3 Create Streamlit configuration
  - [x] 1.3.1 Create `.streamlit/config.toml` with theme settings (primaryColor, backgroundColor, secondaryBackgroundColor, textColor, font)
  - [x] 1.3.2 Configure server settings (maxUploadSize, enableCORS, enableXsrfProtection)

- [x] 1.4 Update project documentation
  - [x] 1.4.1 Update README.md with project overview, installation instructions, and usage guide
  - [x] 1.4.2 Add section on running the Marimo pipeline
  - [x] 1.4.3 Add section on launching the Streamlit dashboard
  - [x] 1.4.4 Add section on deploying to Streamlit Cloud
  - [x] 1.4.5 Add data sources and attribution section
  - [x] 1.4.6 Add license information and compliance notes

## [x] 2. Data Acquisition Module

- [ ] 2.1 Implement Census data fetching
  - [x] 2.1.1 Create `src/pipeline/census_fetcher.py` module
  - [x] 2.1.2 Implement `fetch_block_groups()` function to fetch Census block group geometries
  - [x] 2.1.3 Implement `fetch_demographics()` function to fetch population and median income data
  - [x] 2.1.4 Implement retry logic per FR-1.1.4: enforce 10 s per-request timeout, 60 s hard-cap on total elapsed time (including in-flight requests), backoff formula `500ms × 2.0^attempt` with ±20 % jitter; non-retryable on HTTP 400/401/403/404 (raise immediately); retryable on 5xx; retryable on 429 with `Retry-After` header support; log each attempt at WARNING level with status code
  - [x] 2.1.5 Add error handling for invalid city names or missing data
  - [x] 2.1.6 Add logging for API requests and responses
  - [x] 2.1.7 Validate fetched data (non-null geometries, valid FIPS codes)
  - [x] 2.1.8 Implement multi-county Census queries (FR-1.1.7): (a) derive county FIPS codes by spatially intersecting the bounding box against county polygons (TIGER/Line or bundled GeoJSON), log identified counties at INFO level; (b) issue per-county `for=block group:* in state:{state} in county:{county}` queries; (c) deduplicate by `geoid` keeping first-occurrence (lowest county FIPS), log WARNING for any conflicting attribute values across duplicates; (d) log WARNING for missing counties and continue; (e) raise `CensusDataUnavailableError` with full `(state_fips, county_fips)` list if all counties return no data

- [ ] 2.2 Implement OpenStreetMap data fetching
  - [x] 2.2.1 Create `src/pipeline/osm_fetcher.py` module
  - [x] 2.2.1b Create `src/pipeline/tile_merger.py` module implementing the tile-merge routine: point dedup, polygon union for split geometries, and network edge rejoining with topological reconnection
  - [x] 2.2.2 Implement `fetch_amenities()` function to download all four POI types (grocery, healthcare, transit, other) using the OSM tag sets defined in DR-3.1.5; tag each feature with its `amenity_type` before returning
  - [x] 2.2.3 Implement `fetch_street_network()` function to download walkable street network
  - [x] 2.2.4 Add bounding box calculation from city name or explicit coordinates
  - [x] 2.2.5 Implement bounding box validation (FR-1.1.5): check max edge ≤ 1.0° and area ≤ 1.0 sq° (configurable via `pipeline_config.yaml`); raise `BoundingBoxTooLargeError` with descriptive message if exceeded
  - [x] 2.2.6 Implement optional bbox tiling (FR-1.1.6): when `bbox_limits.enable_tiling=true`, subdivide into equal nx×ny grid tiles (smallest grid where each tile ≤ max edge/area limits), assign row-major tile IDs; download per tile; merge using `src/pipeline/tile_merger.py` (point/POI dedup by `osm_id` first-occurrence, polygon union for split geometries, edge rejoining with 1e-6° tolerance for network topology); apply failure threshold (`bbox_limits.tiling.failure_threshold`, default 0.20) — raise `TilingFailureError` if skip fraction exceeds threshold; write skipped tile IDs to GeoParquet metadata under `skipped_tiles`
  - [x] 2.2.7 Implement request throttling (1 request/second for Overpass API)
  - [x] 2.2.8 Apply same retry policy as 2.1.4 (FR-1.1.4) to all OSMnx/Overpass requests: 60 s hard cap including in-flight requests, non-retryable on 400/401/403/404, retryable on 5xx, 429 with Retry-After support
  - [x] 2.2.9 Add error handling for network download failures
  - [x] 2.2.10 Add logging for OSM queries and data statistics

- [x] 2.3 Create data validation utilities
  - [x] 2.3.1 Create `src/pipeline/data_validator.py` module
  - [x] 2.3.2 Implement `validate_geometries()` function to check for null or invalid geometries
  - [x] 2.3.3 Implement `validate_crs()` function to verify coordinate reference system
  - [x] 2.3.4 Implement `validate_demographics()` function to check for missing or invalid demographic data
  - [x] 2.3.5 Implement `repair_geometries()` function using buffer(0) technique

## 3. Spatial Analysis Module

- [x] 3.1 Implement CRS transformation utilities
  - [x] 3.1.1 Create `src/pipeline/crs_utils.py` module
  - [x] 3.1.2 Implement `determine_utm_zone()` function: compute the centroid of the analysis bounding box in WGS84 and call `geopandas.estimate_utm_crs(latitude, longitude)` to derive the local UTM CRS deterministically; return the CRS for use by all spatial operations in the pipeline run
  - [x] 3.1.3 Implement `transform_to_utm()` function to convert WGS84 to local UTM
  - [x] 3.1.4 Implement `transform_to_wgs84()` function to convert UTM back to WGS84
  - [x] 3.1.5 Add error handling for CRS transformation failures
  - [x] 3.1.6 Add validation to ensure output is always in WGS84

- [x] 3.2 Implement isochrone generation
  - [x] 3.2.1 Create `src/pipeline/isochrone.py` module
  - [x] 3.2.2 Implement `calculate_isochrone()` function to generate 15-minute walking buffer for a single amenity
  - [x] 3.2.3 Read walking speed from `pipeline_config.yaml` (`walk_speed_kmh`, default 4.5 km/h per design §Isochrone Generation Algorithm); do not hard-code the value
  - [x] 3.2.4 Implement network analysis using NetworkX shortest path algorithms
  - [x] 3.2.5 Generate convex hull or alpha shape around reachable nodes
  - [x] 3.2.6 Implement `calculate_all_isochrones()` function to process all amenities
  - [x] 3.2.7 Add parallel processing support using multiprocessing for performance
  - [x] 3.2.8 Add progress logging for isochrone calculations

- [x] 3.3 Implement spatial join and scoring
  - [x] 3.3.1 Create `src/pipeline/scoring.py` module
  - [x] 3.3.2 Implement `spatial_join_amenities()` function: after the geometric join, filter results to only rows where `overlap_area / block_area ≥ MIN_OVERLAP_FRACTION` (read from `pipeline_config.yaml`, default 0.10); all area calculations in local UTM projection
  - [x] 3.3.3 Implement `count_amenities_by_type()` function to count accessible amenities per block group across all four types: grocery, healthcare, transit, other
  - [x] 3.3.4 Implement `calculate_accessibility_score()`: compute `raw_score = w_g*min(grocery,c_g) + w_h*min(healthcare,c_h) + w_t*min(transit,c_t) + w_o*min(other,c_o)` (weights from `scoring_weights`, caps from `scoring_caps` in `pipeline_config.yaml`); store `raw_score` as a separate column in the output GeoDataFrame; then compute `accessibility_score = normalize(raw_score)`
  - [x] 3.3.5 Implement score normalization: `100 × (raw − city_min) / (city_max − city_min)`; when `city_max == city_min`, assign `accessibility_score = 50` to all records and log a WARNING about the degenerate distribution
  - [x] 3.3.6 Implement `assign_equity_category()`: (a) at pipeline startup validate `high_access_min > medium_access_min` and both in [0,100] — raise `ThresholdConfigError` if violated; (b) after scoring run mandatory percentile check — each category ≥ `min_category_fraction` (default 5%), log WARNING and record `"percentile_check": "WARN"/"PASS"` in metadata; (c) run mandatory ±5-point sensitivity test — compute stability for +5 and −5 shifts, compare against `sensitivity_stability_threshold` (default 90%), log WARNING and record `"sensitivity_check": "WARN"/"PASS"` in metadata; (d) write all seven `equity_thresholds.*` metadata fields to GeoParquet (thresholds, percentile_check, category_fractions, sensitivity_check, sensitivity_stability, validated_at timestamp) and log at INFO level
  - [x] 3.3.7 Add validation to ensure `total_amenities` equals `grocery_count + healthcare_count + transit_count + other_count` for every record

- [x] 3.4 Implement spatial indexing for performance
  - [x] 3.4.1 Add R-tree spatial index creation for block groups
  - [x] 3.4.2 Add R-tree spatial index creation for isochrones
  - [x] 3.4.3 Use spatial index for faster spatial join operations

## [x] 4. Data Processing Pipeline (Marimo Notebook)

- [x] 4.1 Create Marimo notebook structure
  - [x] 4.1.1 Create `pipeline.py` as Marimo-compatible notebook
  - [x] 4.1.2 Add cell for configuration parameters (city name, state, bounding box, output path)
  - [x] 4.1.3 Add cell for importing required modules
  - [x] 4.1.4 Add cell for setting up logging

- [x] 4.2 Implement pipeline workflow cells
  - [x] 4.2.1 Add cell for fetching Census demographics
  - [x] 4.2.2 Add cell for fetching OSM amenities
  - [x] 4.2.3 Add cell for fetching street network
  - [x] 4.2.4 Add cell for CRS transformation to UTM
  - [x] 4.2.5 Add cell for calculating isochrones
  - [x] 4.2.6 Add cell for CRS transformation back to WGS84
  - [x] 4.2.7 Add cell for spatial join and accessibility scoring
  - [x] 4.2.8 Add cell for data validation and quality checks
  - [x] 4.2.9 Add cell for exporting to GeoParquet

- [x] 4.3 Add visualization cells for debugging
  - [x] 4.3.1 Add cell to visualize fetched block groups
  - [x] 4.3.2 Add cell to visualize amenities on map
  - [x] 4.3.3 Add cell to visualize sample isochrones
  - [x] 4.3.4 Add cell to display accessibility score distribution histogram
  - [x] 4.3.5 Add cell to show summary statistics

- [x] 4.4 Implement data export
  - [x] 4.4.1 Create `src/pipeline/exporter.py` module
  - [x] 4.4.2 Implement `export_to_geoparquet()` function with snappy compression
  - [x] 4.4.3 Add metadata to GeoParquet file: processing date, pipeline parameters, data sources, `equity_thresholds.*` validation fields (all seven keys from FR-1.2.4), and `skipped_tiles` list (from tiling, if applicable)
  - [x] 4.4.4 Implement geometry simplification to reduce file size (tolerance=0.0001)
  - [x] 4.4.5 Validate output file size is under 50 MB; if the limit is exceeded, apply the following remediation steps in order:
    - [x] 4.4.5.1 Increase geometry simplification tolerance (try `tolerance=0.0005`, then `0.001`) and re-run snappy compression; log the file size after each step
    - [x] 4.4.5.2 If simplification alone is insufficient, implement spatial chunking: split the output by tile or region (e.g., quadrant grid), export each chunk as a separate GeoParquet file, and add a `README_assembly.md` explaining how to load and concatenate the chunks in the Streamlit app
    - [x] 4.4.5.3 Document expected output sizes for different city scales in `docs/data_sources.md`:
      - Small city (< 100k pop): ~5–15 MB — single file, default tolerance sufficient
      - Medium city (100k–500k pop): ~15–40 MB — may need tolerance increase
      - Large city (> 500k pop): ~40–100 MB — likely requires spatial chunking or aggressive simplification
    - [x] 4.4.5.4 Raise a `FileSizeLimitError` with a descriptive message if the file still exceeds 50 MB after all remediation steps, listing which steps were attempted and the resulting sizes
  - [x] 4.4.6 Add logging for export statistics (file size, record count, processing time)

## [x] 5. Streamlit Dashboard

- [x] 5.1 Create main dashboard application
  - [x] 5.1.1 Create `app.py` in project root
  - [x] 5.1.2 Implement page configuration (title, icon, layout="wide")
  - [x] 5.1.3 Add project title and description at top of page
  - [x] 5.1.4 Add footer with data sources, attribution, and license information

- [x] 5.2 Implement data loading
  - [x] 5.2.1 Create `src/dashboard/data_loader.py` module
  - [x] 5.2.2 Implement `load_geoparquet()` function with @st.cache_data decorator
  - [x] 5.2.3 Add error handling for missing file with user-friendly message
  - [x] 5.2.4 Add data validation checks (required columns, valid geometries, CRS)
  - [x] 5.2.5 Add logging for data loading statistics

- [x] 5.3 Implement map visualization
  - [x] 5.3.1 Create `src/dashboard/map_renderer.py` module
  - [x] 5.3.2 Implement `create_choropleth_map()` function using Folium
  - [x] 5.3.3 Add color scale for accessibility scores (RdYlGn colormap)
  - [x] 5.3.4 Add color scale for median income (YlOrRd colormap)
  - [x] 5.3.5 Implement tooltips showing block group details (geoid, population, income, score)
  - [x] 5.3.6 Add map legend explaining color scales
  - [x] 5.3.7 Add OpenStreetMap attribution in map footer
  - [x] 5.3.8 Implement layer toggle between Accessibility Score and Median Income
  - [x] 5.3.9 Integrate map with Streamlit using streamlit-folium

- [x] 5.4 Implement metrics calculation
  - [x] 5.4.1 Create `src/dashboard/metrics.py` module
  - [x] 5.4.2 Implement `calculate_equity_metrics()` function
  - [x] 5.4.3 Calculate percentage of population in low-access areas (score < 40)
  - [x] 5.4.4 Calculate percentage of low-income population in low-access areas
  - [x] 5.4.5 Calculate average accessibility score by income quartile
  - [x] 5.4.6 Calculate total number of block groups analyzed
  - [x] 5.4.7 Calculate median accessibility score
  - [x] 5.4.8 Calculate Gini coefficient for accessibility distribution (optional)

- [x] 5.5 Implement sidebar controls
  - [x] 5.5.1 Add layer toggle radio buttons (Accessibility Score / Median Income)
  - [x] 5.5.2 Add income threshold slider (range: $0–$200k, location-adjusted default): compute the slider's initial value as `default_threshold = clamp(city_median_income * DEFAULT_RATIO, 0, 200_000)` where `city_median_income` is the median of the `median_income` column in the loaded GeoParquet data and `DEFAULT_RATIO = 0.5` (configurable). Display the computed default value in the slider tooltip (e.g., "Default: $47,500 — 50 % of city median income"). Fall back to $50,000 if `city_median_income` is unavailable or zero.
  - [x] 5.5.3 Add accessibility score range slider (range: 0-100, default: 0-100)
  - [x] 5.5.4 Add population density filter slider (optional)
  - [x] 5.5.5 Add "Reset Filters" button
  - [x] 5.5.6 Display current filter values

- [x] 5.6 Implement metrics panel
  - [x] 5.6.1 Create metrics display in sidebar or main columns
  - [x] 5.6.2 Display percentage of population in low-access areas with st.metric()
  - [x] 5.6.3 Display percentage of low-income population in low-access areas
  - [x] 5.6.4 Display average accessibility score by income quartile (bar chart)
  - [x] 5.6.5 Display total block groups analyzed
  - [x] 5.6.6 Add delta indicators showing change from city average

- [x] 5.7 Implement filtering logic
  - [x] 5.7.1 Create `src/dashboard/filters.py` module
  - [x] 5.7.2 Implement `apply_income_filter()` function
  - [x] 5.7.3 Implement `apply_score_filter()` function
  - [x] 5.7.4 Implement `apply_all_filters()` function to combine filters
  - [x] 5.7.5 Update map and metrics when filters change
  - [x] 5.7.6 Add filter summary text showing number of block groups displayed

## 6. Testing

- [x] 6.1 Unit tests for data acquisition
  - [x] 6.1.1 Create `tests/test_census_fetcher.py`
  - [x] 6.1.2 Test `fetch_block_groups()` with mock Census API responses
  - [x] 6.1.3 Test `fetch_demographics()` with mock data
  - [x] 6.1.4 Test retry logic with simulated API failures
  - [x] 6.1.5 Test error handling for invalid city names
  - [x] 6.1.6 Create `tests/test_osm_fetcher.py`
  - [x] 6.1.7 Test `fetch_amenities()` with mock OSM data
  - [x] 6.1.8 Test `fetch_street_network()` with sample bounding box
  - [x] 6.1.9 Test bounding box calculation
  - [x] 6.1.10 Test bbox validation: verify `BoundingBoxTooLargeError` raised when edge > 1.0° or area > 0.5 sq°; verify valid bbox passes
  - [x] 6.1.11 Test bbox tiling: verify nx×ny grid produces tiles within size limits; verify point dedup keeps first-occurrence by `osm_id`; verify polygon union reconstructs split geometries; verify edge rejoining reconnects split network edges within 1e-6° tolerance; verify `TilingFailureError` raised when skip fraction > failure_threshold; verify skipped tile IDs written to GeoParquet metadata
  - [x] 6.1.12 Test multi-county Census queries: verify county FIPS codes are derived by bbox-polygon intersection; verify per-county queries are issued; verify `geoid` deduplication keeps first-occurrence (lowest county FIPS) and logs WARNING for conflicting attribute values; verify WARNING logged for missing county; verify `CensusDataUnavailableError` raised with full `(state_fips, county_fips)` list when all counties return no data
  - [x] 6.1.13 Test retry policy: verify per-request timeout enforced; verify 60 s hard cap cancels in-flight request and stops retries; verify backoff delays match formula with jitter; verify HTTP 400/401/403/404 raise immediately without retry; verify 5xx triggers retry; verify 429 with `Retry-After` header uses header value as delay; verify 429 without header uses computed backoff

- [x] 6.2 Unit tests for spatial analysis
  - [x] 6.2.1 Create `tests/test_crs_utils.py`
  - [x] 6.2.2 Test `determine_utm_zone()` with known coordinates
  - [x] 6.2.3 Test CRS transformations with sample geometries
  - [x] 6.2.4 Create `tests/test_isochrone.py`
  - [x] 6.2.5 Test isochrone generation with synthetic network
  - [x] 6.2.6 Test parallel processing of isochrones
  - [x] 6.2.7 Create `tests/test_scoring.py`
  - [x] 6.2.8 Test spatial join with synthetic geometries: verify area-overlap threshold filter correctly includes/excludes block groups at/below `MIN_OVERLAP_FRACTION`
  - [x] 6.2.9 Test `raw_score` computation: verify correct capped weighted sum with known inputs including `other_count`; verify caps are applied correctly; verify `raw_score` is stored as a separate column in output
  - [x] 6.2.10 Test score normalization: verify `accessibility_score = 100*(raw-min)/(max-min)`; verify `city_max == city_min` edge-case assigns 50 to all records and logs WARNING
  - [x] 6.2.11 Test equity category assignment: verify `ThresholdConfigError` raised when `high_access_min ≤ medium_access_min` or either outside [0,100]; verify percentile check logs WARNING and records WARN/PASS in metadata; verify sensitivity test computes stability for ±5 shifts and records WARN/PASS; verify all seven `equity_thresholds.*` metadata fields written to GeoParquet
  - [x] 6.2.12 Test equity category assignment reads thresholds from config rather than hard-coded values

- [x] 6.3 Unit tests for data validation
  - [x] 6.3.1 Create `tests/test_validators.py`
  - [x] 6.3.2 Test geometry validation with valid and invalid geometries
  - [x] 6.3.3 Test CRS validation
  - [x] 6.3.4 Test demographic data validation
  - [x] 6.3.5 Test geometry repair function

- [x] 6.4 Unit tests for dashboard components
  - [x] 6.4.1 Create `tests/test_data_loader.py`
  - [x] 6.4.2 Test GeoParquet loading with sample file
  - [x] 6.4.3 Test error handling for missing file
  - [x] 6.4.4 Create `tests/test_metrics.py`
  - [x] 6.4.5 Test equity metrics calculation with sample data
  - [x] 6.4.6 Create `tests/test_filters.py`
  - [x] 6.4.7 Test income filter with sample data
  - [x] 6.4.8 Test score filter with sample data
  - [x] 6.4.9 Test combined filters

- [x] 6.5 Property-based tests
  - [x] 6.5.1 Create `tests/test_properties.py`
  - [x] 6.5.2 Implement property test for spatial integrity: verify that only block groups where `overlap_area / block_area ≥ MIN_OVERLAP_FRACTION` are counted as having access; test at-threshold, below-threshold, and zero-overlap cases; all area calculations in UTM
  - [x] 6.5.3 Implement property test for score monotonicity: verify `raw_score(b1) > raw_score(b2) ⟹ accessibility_score(b1) ≥ accessibility_score(b2)` where `raw_score` uses the capped weighted formula; do NOT assert monotonicity over `total_amenities`
  - [x] 6.5.4 Implement property test for CRS consistency (output always WGS84)
  - [x] 6.5.5 Implement property test for data completeness (all block groups have scores)
  - [x] 6.5.6 Implement property test for equity category consistency (score thresholds)
  - [x] 6.5.7 Use Hypothesis library to generate random test data

- [x] 6.6 Integration tests
  - [x] 6.6.1 Create `tests/test_integration.py`
  - [x] 6.6.2 Test end-to-end pipeline with small test city
  - [x] 6.6.3 Test pipeline-to-dashboard integration
  - [x] 6.6.4 Test GeoParquet export and import round-trip
  - [x] 6.6.5 Test cross-CRS transformations throughout pipeline
  - [x] 6.6.6 Measure and validate processing time for test city

- [x] 6.7 Test coverage and quality
  - [x] 6.7.1 Configure pytest-cov for coverage reporting
  - [x] 6.7.2 Run all tests and generate coverage report
  - [x] 6.7.3 Ensure at least 80% code coverage
  - [x] 6.7.4 Add coverage badge to README.md

## 7. Code Quality and Documentation

- [ ] 7.1 Code formatting and linting
  - [ ] 7.1.1 Run Black formatter on all Python files
  - [ ] 7.1.2 Run Ruff linter and fix all issues
  - [ ] 7.1.3 Configure pre-commit hooks for Black and Ruff (optional)

- [ ] 7.2 Type checking
  - [ ] 7.2.1 Add type hints to all function signatures in pipeline modules
  - [ ] 7.2.2 Add type hints to all function signatures in dashboard modules
  - [ ] 7.2.3 Run mypy type checker and fix all errors
  - [ ] 7.2.4 Configure mypy strict mode in pyproject.toml

- [ ] 7.3 Documentation
  - [ ] 7.3.1 Add docstrings to all public functions and classes
  - [ ] 7.3.2 Use Google-style or NumPy-style docstring format
  - [ ] 7.3.3 Document function parameters, return values, and exceptions
  - [ ] 7.3.4 Add module-level docstrings explaining purpose
  - [ ] 7.3.5 Create `docs/architecture.md` explaining system design
  - [ ] 7.3.6 Create `docs/data_sources.md` documenting Census and OSM data
  - [ ] 7.3.7 Create `docs/deployment.md` with Streamlit Cloud deployment guide

- [ ] 7.4 Code comments
  - [ ] 7.4.1 Add inline comments for complex algorithms (isochrone generation, scoring)
  - [ ] 7.4.2 Add comments explaining CRS transformation workflow
  - [ ] 7.4.3 Add comments for performance optimizations (spatial indexing, parallel processing)

## 8. Performance Optimization

- [ ] 8.1 Pipeline performance optimization
  - [ ] 8.1.1 Implement parallel processing for isochrone calculations using multiprocessing
  - [ ] 8.1.2 Add R-tree spatial indexing for faster spatial joins
  - [ ] 8.1.3 Implement geometry simplification to reduce processing time
  - [ ] 8.1.4 Add caching for intermediate results (network, amenities)
  - [ ] 8.1.5 Profile pipeline execution and identify bottlenecks
  - [ ] 8.1.6 Optimize memory usage for large cities (chunked processing)

- [ ] 8.2 Dashboard performance optimization
  - [ ] 8.2.1 Implement data caching with @st.cache_data
  - [ ] 8.2.2 Simplify geometries for web display (tolerance=0.0001)
  - [ ] 8.2.3 Optimize map rendering (reduce polygon complexity)
  - [ ] 8.2.4 Implement lazy loading for map tiles
  - [ ] 8.2.5 Profile dashboard load time and optimize slow components

- [ ] 8.3 File size optimization
  - [ ] 8.3.1 Implement geometry simplification in export function
  - [ ] 8.3.2 Use snappy compression for GeoParquet
  - [ ] 8.3.3 Remove unnecessary columns from output
  - [ ] 8.3.4 Validate final file size is under 50 MB
  - [ ] 8.3.5 Document file size reduction techniques in README

## 9. Deployment Preparation

- [ ] 9.1 Prepare for Streamlit Cloud deployment
  - [ ] 9.1.1 Ensure `app.py` is in project root
  - [ ] 9.1.2 Ensure `requirements.txt` has pinned versions
  - [ ] 9.1.3 Commit processed GeoParquet file to repository
  - [ ] 9.1.4 Test app locally with `streamlit run app.py`
  - [ ] 9.1.5 Verify all file paths are relative (not absolute)
  - [ ] 9.1.6 Add `.streamlit/config.toml` to repository

- [ ] 9.2 Create deployment documentation
  - [ ] 9.2.1 Document Streamlit Cloud deployment steps in README
  - [ ] 9.2.2 Add screenshots of dashboard to README
  - [ ] 9.2.3 Add link to live demo (after deployment)
  - [ ] 9.2.4 Document environment variables (if any)
  - [ ] 9.2.5 Document system requirements for local development

- [ ] 9.3 License and attribution
  - [ ] 9.3.1 Add LICENSE file (Apache 2.0 or MIT)
  - [ ] 9.3.2 Add OpenStreetMap attribution to dashboard footer
  - [ ] 9.3.3 Add Census Bureau attribution to dashboard footer
  - [ ] 9.3.4 Document third-party library licenses in README
  - [ ] 9.3.5 Add NOTICE file with all attributions

## 10. Final Testing and Validation

- [ ] 10.1 End-to-end testing
  - [ ] 10.1.1 Run complete pipeline for test city (Corona, CA)
  - [ ] 10.1.2 Verify GeoParquet file is created successfully
  - [ ] 10.1.3 Launch Streamlit dashboard and verify all features work
  - [ ] 10.1.4 Test all filters and layer toggles
  - [ ] 10.1.5 Verify metrics are calculated correctly
  - [ ] 10.1.6 Test on different browsers (Chrome, Firefox, Safari)

- [ ] 10.2 Data quality validation
  - [ ] 10.2.1 Verify all block groups have valid geometries
  - [ ] 10.2.2 Verify all accessibility scores are in range [0, 100]
  - [ ] 10.2.3 Verify equity categories are correctly assigned
  - [ ] 10.2.4 Verify output CRS is WGS84
  - [ ] 10.2.5 Verify `total_amenities` equals `grocery_count + healthcare_count + transit_count + other_count` for every record
  - [ ] 10.2.6 Verify `raw_score` column is present in output and all values are non-negative floats
  - [ ] 10.2.7 Verify all seven `equity_thresholds.*` metadata fields are present in GeoParquet metadata
  - [ ] 10.2.8 Generate data quality report

- [ ] 10.3 Performance validation
  - [ ] 10.3.1 Measure pipeline execution time for test city
  - [ ] 10.3.2 Verify pipeline completes within 20 minutes
  - [ ] 10.3.3 Measure dashboard load time
  - [ ] 10.3.4 Verify dashboard loads within 2 seconds
  - [ ] 10.3.5 Measure filter update time
  - [ ] 10.3.6 Verify filters update within 500ms

- [ ] 10.4 Acceptance criteria validation
  - [ ] 10.4.1 Verify all functional requirements are met
  - [ ] 10.4.2 Verify all non-functional requirements are met
  - [ ] 10.4.3 Verify all acceptance criteria are satisfied
  - [ ] 10.4.4 Create acceptance test report
  - [ ] 10.4.5 Document any deviations or limitations

- [ ] 10.5 Portfolio presentation preparation
  - [ ] 10.5.1 Create compelling project description for portfolio
  - [ ] 10.5.2 Take high-quality screenshots of dashboard
  - [ ] 10.5.3 Create demo video showing key features (optional)
  - [ ] 10.5.4 Write blog post or case study explaining project (optional)
  - [ ] 10.5.5 Prepare talking points for interviews
