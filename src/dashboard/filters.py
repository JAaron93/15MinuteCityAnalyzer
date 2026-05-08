import geopandas as gpd

MAX_INCOME_THRESHOLD = 200000.0


def apply_all_filters(
    data: gpd.GeoDataFrame,
    income_threshold: float,
    score_range: tuple,
) -> gpd.GeoDataFrame:
    """
    Apply all filters to the dataset.

    Args:
        data (gpd.GeoDataFrame): The dataset.
        income_threshold (float): Max median income.
        score_range (tuple): (min_score, max_score).

    Returns:
        gpd.GeoDataFrame: Filtered dataset.
    """
    filtered_df = data.copy()

    if "median_income" not in filtered_df.columns:
        raise ValueError("Missing 'median_income' column in data.")

    if not isinstance(income_threshold, (int, float)):
        raise TypeError("income_threshold must be numeric.")

    income_threshold = max(0.0, min(float(income_threshold), MAX_INCOME_THRESHOLD))

    filtered_df = filtered_df[filtered_df["median_income"] <= income_threshold]

    if "accessibility_score" not in filtered_df.columns:
        raise ValueError("Missing 'accessibility_score' column in data.")

    if not isinstance(score_range, (tuple, list)) or len(score_range) != 2:
        raise ValueError("score_range must be a tuple or list of length 2.")

    try:
        min_score, max_score = float(score_range[0]), float(score_range[1])
    except (TypeError, ValueError) as e:
        raise TypeError("score_range values must be numeric.") from e

    if min_score > max_score:
        min_score, max_score = max_score, min_score

    # Score filter
    filtered_df = filtered_df[
        (filtered_df["accessibility_score"] >= min_score)
        & (filtered_df["accessibility_score"] <= max_score)
    ]

    return filtered_df
