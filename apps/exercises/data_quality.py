from __future__ import annotations

import numpy as np
import pandas as pd


def data_quality_cleanup_passes(df: pd.DataFrame, numeric_columns: list[str] | None = None) -> bool:
    """Return True when a cleaned frame has no nulls/duplicates and restored numeric dtypes."""
    if df is None or not isinstance(df, pd.DataFrame):
        return False
    if int(df.isna().sum().sum()) != 0:
        return False
    if int(df.duplicated().sum()) != 0:
        return False
    for column in numeric_columns or []:
        if column not in df.columns:
            return False
        if not pd.api.types.is_numeric_dtype(df[column]):
            return False
    return True


def difficulty_issue_count(difficulty: str | None, seed: int | None = 42) -> int:
    rng = np.random.default_rng(seed)
    buckets = {
        "easy": (3, 5),
        "medium": (6, 9),
        "hard": (12, 15),
    }
    difficulty_key = (difficulty or "medium").lower()
    if difficulty_key not in buckets:
        raise ValueError(f"Unknown difficulty: {difficulty_key}. Use easy, medium, or hard.")
    low, high = buckets[difficulty_key]
    return int(rng.integers(low, high + 1))


def normalize_string(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def introduce_data_quality_issues(df: pd.DataFrame, difficulty: str = "medium", seed: int = 42):
    """Return a dirty copy of a dataframe and a reproducible issue log.

    The generator is intentionally opaque to the learner: it changes the data based on
    seeded difficulty, but it does not expose the exact issue count or change list in the UI.
    """
    rng = np.random.default_rng(seed)
    dirty = df.copy()
    original_dtypes = dirty.dtypes.to_dict()
    dirty = dirty.astype(object)
    issue_log = []

    if dirty.empty:
        return dirty, issue_log

    issue_budget = difficulty_issue_count(difficulty, seed)
    target_cells = [(row_idx, col_name) for row_idx in range(len(dirty)) for col_name in dirty.columns]
    rng.shuffle(target_cells)

    replacements = {
        "string": {
            "O": "0",
            "o": "0",
            "!": "1",
            "I": "1",
            "l": "1",
            "S": "5",
            "B": "8",
            "@": "a",
            "-": "",
            " ": "",
            "_": "",
        },
        "category": {
            "Active": "active",
            "Inactive": "inactive",
            "Email": "email",
            "email": "email",
            "SMS": "sms",
            "Phone": "phone",
            "call center": "call_center",
            "Call Center": "call_center",
            "North": "north",
            "South": "south",
            "West": "west",
            "East": "east",
        },
    }

    used_cells = set()
    issue_count = 0

    def record_issue(issue_type, row_idx, col_name, before, after, note=""):
        issue_log.append(
            {
                "type": issue_type,
                "row": int(row_idx),
                "column": col_name,
                "before": before,
                "after": after,
                "note": note,
            }
        )

    for row_idx, col_name in target_cells:
        if issue_count >= issue_budget:
            break
        if (row_idx, col_name) in used_cells:
            continue

        value = dirty.iloc[row_idx, dirty.columns.get_loc(col_name)]
        original_value = value

        if isinstance(value, (str, object)) and rng.random() < 0.5:
            chosen_map = replacements["string" if any(k in str(value) for k in ["O", "o", "!", "@", "-", " "]) else "category"]
            text = normalize_string(value)
            candidate = next((old for old in chosen_map if old in text), None)
            if candidate is not None:
                new_value = text.replace(candidate, chosen_map[candidate], 1)
                dirty.iloc[row_idx, dirty.columns.get_loc(col_name)] = new_value
                record_issue(
                    "string_replacement",
                    row_idx,
                    col_name,
                    original_value,
                    new_value,
                    f"Replaced '{candidate}' with '{chosen_map[candidate]}'",
                )
                used_cells.add((row_idx, col_name))
                issue_count += 1
                continue

        if pd.api.types.is_numeric_dtype(original_dtypes.get(col_name, dirty[col_name].dtype)) and rng.random() < 0.4:
            new_value = str(value)
            if "." in new_value:
                new_value = new_value.replace(".", "")
            if rng.random() < 0.5:
                new_value = f"{new_value},000"
            else:
                new_value = f"{new_value}x"
            dirty.iloc[row_idx, dirty.columns.get_loc(col_name)] = new_value
            record_issue(
                "type_error",
                row_idx,
                col_name,
                original_value,
                new_value,
                "Converted numeric value to an invalid string representation.",
            )
            used_cells.add((row_idx, col_name))
            issue_count += 1
            continue

        if rng.random() < 0.25:
            dirty.iloc[row_idx, dirty.columns.get_loc(col_name)] = np.nan
            record_issue(
                "missing_value",
                row_idx,
                col_name,
                original_value,
                np.nan,
                "Inserted a null/missing value.",
            )
            used_cells.add((row_idx, col_name))
            issue_count += 1
            continue

        if isinstance(value, str):
            if any(token.lower() in value.lower() for token in ["active", "inactive", "email", "sms", "phone", "north", "south", "west", "east"]):
                new_value = value
                if value.lower() in {"north", "south", "west", "east"}:
                    new_value = value.lower()
                elif value.lower() in {"active", "inactive"}:
                    new_value = value.lower()
                elif "@" in value:
                    new_value = value.lower()
                else:
                    new_value = value.lower().replace(" ", "_")

                dirty.iloc[row_idx, dirty.columns.get_loc(col_name)] = new_value
                record_issue(
                    "inconsistent_category",
                    row_idx,
                    col_name,
                    original_value,
                    new_value,
                    "Normalized a categorical value to a consistent label.",
                )
                used_cells.add((row_idx, col_name))
                issue_count += 1
                continue

        if issue_count + 1 <= issue_budget and rng.random() < 0.15 and len(dirty) > 2:
            duplicated_row = dirty.iloc[row_idx].copy()
            dirty = pd.concat([dirty, duplicated_row.to_frame().T], ignore_index=True)
            record_issue(
                "duplicate_row",
                row_idx,
                col_name,
                original_value,
                "row duplicated",
                "Added a full duplicate row.",
            )
            issue_count += 1
            break

        if issue_count + 1 <= issue_budget and rng.random() < 0.1 and len(dirty) > 2:
            duplicated_row = dirty.iloc[row_idx].copy()
            duplicated_row[col_name] = f"{duplicated_row[col_name]}_duplicate"
            dirty = pd.concat([dirty, duplicated_row.to_frame().T], ignore_index=True)
            record_issue(
                "partial_duplicaterow",
                row_idx,
                col_name,
                original_value,
                duplicated_row[col_name],
                "Appended a row that matches most values but differs in one field.",
            )
            issue_count += 1
            break

    while issue_count < issue_budget and len(target_cells) > 0:
        row_idx, col_name = target_cells[issue_count % len(target_cells)]
        if (row_idx, col_name) in used_cells:
            continue
        value = dirty.iloc[row_idx, dirty.columns.get_loc(col_name)]
        dirty.iloc[row_idx, dirty.columns.get_loc(col_name)] = np.nan if isinstance(value, (int, float, str)) else value
        record_issue(
            "missing_value",
            row_idx,
            col_name,
            value,
            np.nan,
            "Extra null inserted to reach the requested issue count.",
        )
        used_cells.add((row_idx, col_name))
        issue_count += 1

    dirty = dirty.reset_index(drop=True)
    dirty.attrs["data_quality_issue_log"] = issue_log
    dirty.attrs["data_quality_seed"] = seed
    dirty.attrs["difficulty"] = difficulty
    return dirty, issue_log
