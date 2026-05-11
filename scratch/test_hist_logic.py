import pandas as pd

# Mock data
scores = [10.5, 20.3, 20.8, 45.0, 99.9, 5.0, 15.0]
df = pd.DataFrame({"accessibility_score": scores})

# Logic from app.py
bins = pd.cut(df["accessibility_score"], bins=10)
hist_data = bins.value_counts().sort_index()
hist_data.index = hist_data.index.astype(str)
print(hist_data)

# Automated Assertions
# Expected bins with bins=10 over range [5.0, 99.9]:
# Bin 1: [5.0, ~14.5) -> 2 items (5.0, 10.5)
# Bin 2: [~14.5, ~24.0) -> 3 items (15.0, 20.3, 20.8)
# Bin ~5: [~42.5, ~52.0) -> 1 item (45.0)
# Bin 10: [~90.5, 99.9] -> 1 item (99.9)
assert hist_data.sum() == len(df), f"Expected {len(df)}, got {hist_data.sum()}"
assert hist_data.iloc[0] == 2, f"Expected 2, got {hist_data.iloc[0]}"
assert hist_data.iloc[1] == 3, f"Expected 3, got {hist_data.iloc[1]}"
assert hist_data[hist_data > 0].size == 4, (
    f"Expected 4 non-empty bins, got "
    f"{hist_data[hist_data > 0].size}"
)
print("All assertions passed!")
