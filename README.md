# 15-Minute City & Transit Equity Analyzer

A geospatial analysis tool that evaluates urban accessibility and transit equity. This project analyzes whether residents can access essential amenities (grocery stores, healthcare, transit) within a 15-minute walk and identifies equity gaps by correlating accessibility with demographic data.

## Features

- **Data Acquisition**: Fetches Census block group demographics and OpenStreetMap POIs/street networks.
- **Spatial Analysis**: Calculates 15-minute walking isochrones and performs spatial joins with area-overlap thresholds.
- **Equity Scoring**: Computes composite accessibility scores and assigns equity categories.
- **Interactive Dashboard**: Visualizes results in a Streamlit web application with interactive maps and metrics.

## Installation

### Prerequisites

- Python 3.9 or higher
- `libspatialindex` (required for `rtree`)

```bash
# On macOS
brew install libspatialindex

# On Ubuntu/Debian
sudo apt-get install libspatialindex-dev
```

### Setup

```bash
# Clone the repository
git clone https://github.com/pretermodernist/15MinuteCityAnalyzer.git
cd 15MinuteCityAnalyzer

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

### 1. Run the Data Pipeline

The data processing is handled by a Marimo notebook which can be run as a script or interactively.

```bash
# Run interactively
marimo edit src/pipeline/pipeline.py

# Run as a script (once implemented)
python src/pipeline/pipeline.py
```

### 2. Launch the Dashboard

Once the pipeline has generated the processed data, launch the Streamlit dashboard:

```bash
streamlit run app.py
```

## Data Sources

- **Demographics**: [U.S. Census Bureau ACS 5-Year Estimates](https://www.census.gov/data/developers/data-sets/acs-5year.html)
- **Amenities & Infrastructure**: [OpenStreetMap](https://www.openstreetmap.org/) via OSMnx

## Deployment

The dashboard is designed to be deployable to [Streamlit Cloud](https://streamlit.io/cloud). Ensure the processed GeoParquet file is committed to the repository (if under 50MB) for seamless deployment.

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.
Data from OpenStreetMap is licensed under the [Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/).
