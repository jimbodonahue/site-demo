# %%
# --- Use a reusable generator on any clean dataset ---
# The goal is to reproduce a dirty version of a known-clean dataframe.
# We can control difficulty and seed to create repeatable tasks.

rng = np.random.default_rng(data.get('seed', 42))

records = [
    {"customer_id": "C-001", "region": "North", "channel": "email", "status": "active", "sales": 1200, "score": 8.7},
    {"customer_id": "C-002", "region": "South", "channel": "sms", "status": "active", "sales": 980, "score": 7.4},
    {"customer_id": "C-003", "region": "West", "channel": "phone", "status": "inactive", "sales": 640, "score": 6.1},
    {"customer_id": "C-004", "region": "East", "channel": "email", "status": "active", "sales": 1350, "score": 9.2},
    {"customer_id": "C-005", "region": "North", "channel": "email", "status": "active", "sales": 810, "score": 5.8},
    {"customer_id": "C-006", "region": "South", "channel": "call_center", "status": "active", "sales": 1180, "score": 6.5},
    {"customer_id": "C-007", "region": "West", "channel": "sms", "status": "active", "sales": 780, "score": 7.9},
    {"customer_id": "C-008", "region": "East", "channel": "email", "status": "active", "sales": 900, "score": 8.1},
    {"customer_id": "C-009", "region": "North", "channel": "email", "status": "active", "sales": 850, "score": 8.4},
    {"customer_id": "C-010", "region": "South", "channel": "phone", "status": "active", "sales": 1100, "score": 6.3},
]

clean_df = pd.DataFrame(records)

# Reproducible issue generation by seed and difficulty
# Easy: 3-5 issues, Medium: 6-9, Hard: 12-15
# Each issue is tracked in issue_log so you can inspect exactly what was changed.
dirty_df, issue_log = introduce_data_quality_issues(
    clean_df,
    difficulty=data.get('difficulty', 'medium'),
    seed=data.get('seed', 42),
)

print('Difficulty:', data.get('difficulty', 'medium'))
print('Seed:', data.get('seed', 42))
print('Issue count:', len(issue_log))
print(issue_log)
dirty_df.head()
# %%
# TODO for students:
# 1) Fix OCR-like replacements: O -> 0, ! -> 1, etc.
# 2) Remove duplicate rows.
# 3) Convert weird type strings like '1,200' or 'nan' to actual numbers.
# 4) Fix categorical inconsistencies and null values.
# 5) Return a clean dataframe ready for analysis.

clean_df = dirty_df.copy()

# Example starting points:
# clean_df['sales'] = clean_df['sales'].astype(str).str.replace(',', '', regex=False)
# clean_df['sales'] = clean_df['sales'].replace({'O': '0', 'o': '0', '!': '1', 'N/A': np.nan, 'nan': np.nan})
# clean_df['sales'] = pd.to_numeric(clean_df['sales'], errors='coerce')
# clean_df['channel'] = clean_df['channel'].str.lower().str.replace(' ', '_', regex=False)
# clean_df['status'] = clean_df['status'].str.lower()
# clean_df = clean_df.drop_duplicates().reset_index(drop=True)
# clean_df = clean_df.dropna(subset=['customer_id', 'sales', 'score']).reset_index(drop=True)

clean_df.head()
# %%
plt.figure(figsize=(6, 4))
plt.scatter(clean_df['sales'], clean_df['score'], alpha=0.7)
plt.title('Sales vs. Score after cleanup')
plt.xlabel('Sales')
plt.ylabel('Score')
plt.tight_layout()

rows_after_cleaning = len(clean_df)
missing_after = int(clean_df.isna().sum().sum())
print('Rows after cleaning:', rows_after_cleaning)
print('Missing values after cleaning:', missing_after)
missing_after
