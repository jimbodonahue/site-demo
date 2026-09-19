"""Spotter snippets: short, non-spoilery tool reminders per exercise difficulty.

Medium/hard intentionally omit earlier-level tips. Snippets use placeholders
like ``df['column']`` so they are not paste-ready solutions.
"""

from __future__ import annotations

from typing import Any

# Each entry is a short line students can glance at — patterns, not answers.
SPOTTER_TIPS: dict[str, dict[str, list[str]]] = {
	"pandas_intro": {
		"easy": [
			"df['column'].mean()",
			"df['column'].median()",
			"df['column'].max()  # or .min()",
			"(df['column'] == value).sum()",
			"answer = …",
			"plt.plot(df['column'])  # plotting bonus: any chart",
		],
		"medium": [
			"mask = df['column'] > value",
			"df.loc[mask, ['col_a', 'col_b']]",
			"df = result.reset_index(drop=True)",
			"plt.scatter(..., color='teal')  # +1 style change",
		],
		"hard": [
			"df.sort_values('column', ascending=False)",
			"df.loc[mask].sort_values('column').reset_index(drop=True)",
			"# combine filter + sort in one pipeline",
			"plt.plot(..., color='navy', marker='o'); plt.title('…', fontsize=12)",
		],
	},
	"data_transformation": {
		"easy": [
			"df.loc[df['column'] <= threshold, ['col_a', 'col_b']]",
			"df0 = …; df1 = …; df2 = …",
			"result.reset_index(drop=True)",
			"plt.bar(labels, values)  # plotting bonus",
		],
		"medium": [
			"series.map(mapping_dict)",
			"series.apply(lambda x: …)",
			"series.str.strip().str.lower()",
			"df0 / df1 / df2 with encoded columns",
			"plt.bar(..., color='orchid')",
		],
		"hard": [
			"pd.get_dummies(df['column'], prefix='…')",
			"# bit columns via integer codes & bitwise ops",
			"category_to_code = {'label': 1, …}",
			"plt.bar(..., color='steelblue'); plt.xlabel('…', fontsize=11)",
		],
	},
	"messy_dataset": {
		"easy": [
			"df.columns = df.iloc[0]; df = df.iloc[1:]",
			"df.dropna(how='all')",
			"df.drop_duplicates()",
			"series.map(task['word_to_int'])",
			"plt.hist(df['column'])  # plotting bonus",
		],
		"medium": [
			"repair_messy_number(value)",
			"df.drop(columns=[c for c in df.columns if c.endswith('_dup')])",
			"df.merge(df_extra, on='key_column', how='left')",
			"plt.hist(..., color='seagreen')",
		],
		"hard": [
			"df['key'] = pd.to_numeric(df['key'], errors='coerce')",
			"# align dtypes on both sides before the merge",
			"df_extra['key'] = df_extra['key'].astype(df['key'].dtype)",
			"plt.hist(..., color='slateblue'); plt.title('…', fontsize=12)",
		],
	},
	"ab_testing": {
		"easy": [
			"welch_ttest(group_a, group_b)",
			"result['p_value']",
			"different = p_value < 0.05",
			"# bonus: plt.hist(group_a, alpha=0.5); plt.hist(group_b, alpha=0.5)  OR  plt.violinplot([...])",
		],
		"medium": [
			"# Bayes: P(A|B) = P(B|A) * P(A) / P(B)",
			"P(B) = P(B|A)*P(A) + P(B|not A)*P(not A)",
			"answer = posterior",
			"plt.hist(..., alpha=0.5, color='tomato')  # or violinplot with color",
		],
		"hard": [
			"relevant = …  # practical + statistical judgment",
			"# a non-significant p-value can still look 'close'",
			"# weigh mean gap against noise / effect size",
			"plt.hist(..., alpha=0.45, color='navy'); plt.title('…', fontsize=12)",
		],
	},
	"descriptive_statistics": {
		"easy": [
			"df['column'].mean()",
			"df['column'].median()",
			"df['column'].mode().iloc[0]  # not for float columns here",
			"df['column'].std()  # sample SD",
			"df['column'].var()",
			"answer = {'q1': …, 'q2': …}",
			"plt.boxplot(df['column'])  # plotting bonus",
		],
		"medium": [
			"df.groupby('group_col')['value_col'].mean()",
			"grouped.median()",
			"grouped.std()",
			"(means - medians).abs().idxmax()",
			"answer = {'q1': 'group_label', …}",
			"plt.boxplot(..., patch_artist=True);  # set color / font for bonus",
		],
		"hard": [
			"plt.hist(df['column'])  # then plotted = True",
			"df['column'].round().mode().iloc[0]",
			"df.corr()",
			"plt.imshow(df.select_dtypes('number').corr())",
			"plotted = True",
			"plt.boxplot(..., widths=0.5); plt.title('…', fontsize=12)  # bonus",
		],
	},
	"data_quality": {
		"easy": [
			"df[target].isna().sum()",
			"df[target] = df[target].fillna(df[target].median())",
			"# or .mean() / a constant",
			"missing = df.isna().sum(); plt.bar(missing.index, missing.values)",
		],
		"medium": [
			"df.groupby(outcome)[target].transform('median')",
			"df[target] = df[target].fillna(grouped_fill)",
			"# impute using the outcome groups",
			"plt.bar(..., color='crimson')  # missingness bonus",
		],
		"hard": [
			"# build a mask from related columns / self-patterns",
			"df.loc[mask, target] = fill_values",
			"# finish remaining gaps after conditional fills",
			"plt.bar(..., color='indigo'); plt.xticks(rotation=45, fontsize=9)",
		],
	},
	"missing_values": {
		"easy": [
			"df[target].isna().sum()",
			"df[target] = df[target].fillna(df[target].median())",
			"# or .mean() / a constant",
			"missing = df.isna().sum(); plt.bar(missing.index, missing.values)",
		],
		"medium": [
			"df.groupby(outcome)[target].transform('median')",
			"df[target] = df[target].fillna(grouped_fill)",
			"# impute using the outcome groups",
			"plt.bar(..., color='crimson')  # missingness bonus",
		],
		"hard": [
			"# build a mask from related columns / self-patterns",
			"df.loc[mask, target] = fill_values",
			"# finish remaining gaps after conditional fills",
			"plt.bar(..., color='indigo'); plt.xticks(rotation=45, fontsize=9)",
		],
	},
}


def get_spotter_tips(
	dataframe_source: str | None,
	difficulty: str | None = None,
) -> dict[str, list[str]] | list[str]:
	"""Return all difficulty tips for a source, or one difficulty's list."""
	source = (dataframe_source or "").strip()
	by_level = SPOTTER_TIPS.get(source) or {}
	if difficulty is None:
		return {
			"easy": list(by_level.get("easy") or []),
			"medium": list(by_level.get("medium") or []),
			"hard": list(by_level.get("hard") or []),
		}
	key = (difficulty or "easy").lower().strip()
	if key not in {"easy", "medium", "hard"}:
		key = "easy"
	return list(by_level.get(key) or [])


def spotter_tips_for_data_state(data_state: dict[str, Any] | None) -> list[str]:
	"""Resolve tips for the current exercise data_state."""
	state = data_state or {}
	source = state.get("dataframe_source") or ""
	difficulty = state.get("selected_feature") or state.get("difficulty") or "easy"
	tips = get_spotter_tips(source, difficulty)
	return tips if isinstance(tips, list) else []
