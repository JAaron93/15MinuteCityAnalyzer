# 15-Minute City Analyzer

A Python-based geospatial analysis project for evaluating urban accessibility and transit equity using the "15-minute city" concept. This project combines interactive data processing (Marimo notebooks) with a lightweight web dashboard (Streamlit).

## Overview

The 15-minute city is an urban planning concept where residents can access most daily necessities within a 15-minute walk or bike ride. This project provides tools to:

- **Analyze** urban accessibility by calculating walking coverage areas (isochrones)
- **Score** accessibility to essential amenities (grocery, healthcare, transit, schools, parks)
- **Visualize** accessibility patterns with interactive maps
- **Compare** transit equity across neighborhoods

## Quick Start

### Prerequisites

- Python 3.10+
- Git
- (Optional) GitHub CLI (`gh`)

### Installation

1. **Clone the repository** (if you haven't already):
```bash
git clone https://github.com/JAaron93/15MinuteCityAnalyzer.git
cd 15MinuteCityAnalyzer
```

2. **Create and activate virtual environment**:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**:
```bash
pip install -r requirements.txt
```

## Usage

### Part 1: Data Processing with Marimo

The Marimo notebook provides an interactive environment to download OpenStreetMap data, calculate 15-minute walking accessibility, and generate transit equity metrics.

1. **Launch the data processing notebook**:
```bash
marimo edit notebooks/data_processing.py
```

2. **In the notebook**:
   - Enter a city name (e.g., "Berkeley, California, USA")
   - Adjust the walking time threshold (default: 15 minutes)
   - Select amenities to analyze (grocery, healthcare, transit, schools, parks)
   - Click "Load Data from OpenStreetMap" to fetch the street network and amenity locations
   - Run the accessibility analysis to generate a grid of scores
   - View interactive maps and export processed data to `data/processed/`

3. **Optional**: Upload a GeoJSON file with neighborhood boundaries to calculate equity metrics

### Part 2: Web Dashboard with Streamlit

The Streamlit dashboard provides a polished, shareable interface for exploring pre-processed accessibility data.

1. **Run the dashboard**:
```bash
streamlit run dashboard/app.py
```

2. **In the dashboard**:
   - Select processed data files from the sidebar
   - View interactive accessibility heatmaps with multiple map styles
   - Explore score distributions and quartile breakdowns
   - Analyze amenity accessibility breakdowns
   - Download data as CSV for external analysis

## Project Structure

```
15MinuteCityAnalyzer/
├── notebooks/
│   └── data_processing.py      # Marimo interactive notebook
├── dashboard/
│   └── app.py                  # Streamlit web dashboard
├── src/
│   └── fifteen_minute_city/
│       ├── __init__.py
│       ├── data_loader.py      # OSM data downloading utilities
│       ├── accessibility.py    # 15-minute walk calculations
│       └── visualization.py    # Plotly visualization utilities
├── tests/
│   └── test_accessibility.py   # Pytest unit tests
├── data/
│   ├── raw/                    # Downloaded OSM data
│   └── processed/              # Output from Marimo notebook
├── requirements.txt
├── LICENSE (Apache 2.0)
└── README.md
```

## How It Works

### Data Pipeline

1. **Download**: OSMnx fetches street networks and amenity locations from OpenStreetMap
2. **Process**: NetworkX calculates walking distances (15 min = ~1.25km at 5 km/h)
3. **Score**: For each grid point, count accessible amenities within the time threshold
4. **Visualize**: Plotly renders interactive maps with accessibility heatmaps

### Scoring Methodology

- **100 points**: Point has access to at least one of each amenity type within 15 min walk
- **0-100 points**: Proportional to number of amenity categories accessible
- **Score breakdown** per amenity: count and minimum walking time recorded

### Performance Considerations

- Grid resolution is configurable (10-50 points per dimension)
- Higher resolution = more detail but slower processing
- Default 20×20 grid = 400 points analyzed per city
- Results cached in Parquet format for fast dashboard loading

## Development

### Running Tests

```bash
pytest tests/test_accessibility.py -v
```

### Exporting Marimo Notebook

Export as HTML for sharing or documentation:
```bash
marimo export html notebooks/data_processing.py -o report.html
```

### Adding New Amenity Types

Edit `src/fifteen_minute_city/data_loader.py`:

```python
DEFAULT_AMENITIES = {
    # ... existing amenities ...
    "library": "[amenity=library]",
}
```

## Data Sources

- **Street networks**: OpenStreetMap via [OSMnx](https://osmnx.readthedocs.io/)
- **Amenity locations**: OpenStreetMap via Overpass API
- **Neighborhood boundaries**: User-provided GeoJSON (optional)

## Configuration

### Environment Variables

Create a `.env` file to customize:

```bash
# Data directories
DATA_RAW_DIR=data/raw
DATA_PROCESSED_DIR=data/processed

# Analysis parameters
DEFAULT_TIME_MINUTES=15
WALKING_SPEED_MPM=83  # meters per minute (~5 km/h)
```

### Spec-Kit Constitution

This project follows the development principles defined in `.specify/memory/constitution.md`:

- **Code Quality**: PEP 8, type hints, max complexity 10
- **Testing**: 80% coverage, TDD, pytest
- **UX**: Consistent CLI patterns, accessible visualizations
- **Performance**: Streaming for large datasets, vectorized operations

## Troubleshooting

### OSMnx download fails

Try a more specific city query:
- ❌ "Berkeley" (ambiguous)
- ✅ "Berkeley, California, USA"

### Slow analysis

Reduce grid resolution in the Marimo notebook (slider from 20 to 10).

### Dashboard shows no data

Ensure you've run the Marimo notebook first and saved data to `data/processed/`.

## License

Apache License 2.0 - see [LICENSE](LICENSE) file for details.

## Acknowledgments

- [OSMnx](https://osmnx.readthedocs.io/) by Geoff Boeing for OSM data access
- [Marimo](https://marimo.io/) for reactive notebooks
- [Streamlit](https://streamlit.io/) for rapid dashboard development
- 15-minute city concept by Carlos Moreno

---

**Version**: 0.1.0 | **Python**: 3.10+ | **Author**: JAaron93
