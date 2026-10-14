import pandas as pd
sample = pd.read_csv("data/pypi_lsh_matches_sample.csv")
print(sample["popular_name"].head(10).tolist())