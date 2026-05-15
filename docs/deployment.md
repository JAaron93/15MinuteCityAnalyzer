# Deployment Guide

The 15-Minute City & Transit Equity Analyzer dashboard is designed to be deployed as a Streamlit web application.

## Local Deployment (Development)

To run the application locally for development or testing:

1.  **Install Dependencies**: Ensure you are using Python 3.9+ and install all dependencies via pip:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Configure Environment**: Provide the required Census API key:
    ```bash
    export CENSUS_API_KEY="your_api_key_here"
    ```
3.  **Run the Pipeline (Optional)**: If you need to regenerate the analysis data (e.g. for a new bounding box), run the pipeline script:
    ```bash
    python pipeline.py
    ```
4.  **Run the Dashboard**:
    ```bash
    streamlit run app.py
    ```

## Cloud Deployment (Streamlit Community Cloud)

The easiest way to share the dashboard is via Streamlit Community Cloud:

1.  Push the repository to GitHub. Ensure the `data/processed/analysis_results.parquet` file is included in the repository (or set up the app to fetch it from an S3 bucket or similar storage if it is too large for GitHub).
2.  Log in to [Streamlit Community Cloud](https://share.streamlit.io/).
3.  Click **New app**.
4.  Select the GitHub repository, branch, and specify `app.py` as the Main file path.
5.  In the **Advanced settings**, provide the `CENSUS_API_KEY` under the Secrets configuration:
    ```toml
    CENSUS_API_KEY = "your_api_key_here"
    ```
6.  Click **Deploy!**

## Docker Deployment

You can package the application in a Docker container for deployment to AWS, GCP, or Azure.

**Dockerfile**
```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .

RUN apt-get update && apt-get install -y \
    build-essential \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

Build and run:
```bash
docker build -t 15-min-city .
docker run -p 8501:8501 -e CENSUS_API_KEY=your_key 15-min-city
```
