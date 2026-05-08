import pandas as pd
import numpy as np

# Mock data
scores = [10.5, 20.3, 20.8, 45.0, 99.9, 5.0, 15.0]
df = pd.DataFrame({"accessibility_score": scores})

# Logic from app.py
bins = pd.cut(df["accessibility_score"], bins=10)
hist_data = bins.value_counts().sort_index()
hist_data.index = hist_data.index.astype(str)
print(hist_data)
