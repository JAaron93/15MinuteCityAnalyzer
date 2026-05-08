import geopandas as gpd
import pandas as pd


def calculate_equity_metrics(
    data: gpd.GeoDataFrame, income_threshold: float = 50000.0
) -> dict:
    """
    Calculate high-level equity KPIs.

    Args:
        data (gpd.GeoDataFrame): The processed dataset.
        income_threshold (float): Threshold to define 'low-income'.

    Returns:
        dict: A dictionary containing metrics.
    """
    if data.empty:
        return {
            "total_block_groups": 0,
            "total_population": 0,
            "pct_pop_low_access": 0.0,
            "pct_low_income_low_access": 0.0,
            "avg_score_by_quartile": {},
            "median_accessibility_score": 0.0,
            "city_avg_score": 0.0,
        }

    total_pop = data["population"].sum()
    low_access = data[data["equity_category"] == "Low Access"]
    low_income = data[data["median_income"] < income_threshold]

    # Percentage of population in low-access areas
    pop_low_access = low_access["population"].sum()
    pct_pop_low_access = (pop_low_access / total_pop * 100) if total_pop > 0 else 0

    # Percentage of low-income population in low-access areas
    # This requires intersection of low-income and low-access
    low_income_low_access = data[
        (data["median_income"] < income_threshold)
        & (data["equity_category"] == "Low Access")
    ]
    total_low_income_pop = low_income["population"].sum()
    pop_low_income_low_access = low_income_low_access["population"].sum()
    pct_low_income_low_access = (
        (pop_low_income_low_access / total_low_income_pop * 100)
        if total_low_income_pop > 0
        else 0
    )

    # Average accessibility score by income quartile
    # Use qcut to divide into 4 groups based on median_income
    try:
        # Filter out records with 0 or NaN income for quartile calculation if necessary,
        # but here we'll just use the data we have.
        data_with_income = data[data["median_income"] > 0].copy()
        if len(data_with_income) >= 4:
            data_with_income["income_quartile"] = pd.qcut(
                data_with_income["median_income"],
                4,
                labels=["Q1 (Low)", "Q2", "Q3", "Q4 (High)"],
            )
            avg_score_by_quartile = (
                data_with_income.groupby("income_quartile", observed=True)[
                    "accessibility_score"
                ]
                .mean()
                .to_dict()
            )
        else:
            avg_score_by_quartile = {}
    except Exception:
        avg_score_by_quartile = {}

    return {
        "total_block_groups": len(data),
        "total_population": total_pop,
        "pct_pop_low_access": pct_pop_low_access,
        "pct_low_income_low_access": pct_low_income_low_access,
        "avg_score_by_quartile": avg_score_by_quartile,
        "median_accessibility_score": data["accessibility_score"].median(),
        "city_avg_score": data["accessibility_score"].mean(),
    }
