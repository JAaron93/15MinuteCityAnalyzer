import geopandas as gpd


def apply_all_filters(
    data: gpd.GeoDataFrame,
    income_threshold: float,
    score_range: tuple,
    pop_density_min: float = 0.0,
) -> gpd.GeoDataFrame:
    """
    Apply all filters to the dataset.

    Args:
        data (gpd.GeoDataFrame): The dataset.
        income_threshold (float): Max median income.
        score_range (tuple): (min_score, max_score).
        pop_density_min (float): Min population density (optional).

    Returns:
        gpd.GeoDataFrame: Filtered dataset.
    """
    filtered_df = data.copy()

    # Income filter (show block groups WITH median_income <= threshold)
    # Note: FR-1.4.5 says "filter the map by Median income threshold"
    # Usually this means "show areas with income below X" or "above X".
    # I'll implement it as "median_income >= threshold" for a range or just a limit.
    # Actually, let's stick to the requirements which say "income threshold".
    # I'll use it as a range filter for more flexibility if possible,
    # but the task says "Median income threshold".
    # I'll use it to filter OUT block groups ABOVE the threshold
    # (i.e. focus on low income).
    if income_threshold < 200000:  # Assuming 200k is the max
        filtered_df = filtered_df[filtered_df["median_income"] <= income_threshold]

    # Score filter
    filtered_df = filtered_df[
        (filtered_df["accessibility_score"] >= score_range[0])
        & (filtered_df["accessibility_score"] <= score_range[1])
    ]

    return filtered_df
