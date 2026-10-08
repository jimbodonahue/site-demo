from __future__ import annotations

import ast
import base64
import hashlib
import importlib
import io
import json
import os
import subprocess
import sys
import traceback
import types
from contextlib import redirect_stdout
from copy import deepcopy

from apps.exercises.ab_testing import ab_testing_passes, prepare_ab_testing, welch_ttest
from apps.exercises.data_quality import data_quality_cleanup_passes, introduce_data_quality_issues
from apps.exercises.data_transformation import (
	build_product_dataframe,
	data_transformation_passes,
	generate_data_transformation_task,
)
from apps.exercises.dataframe_providers import (
	DATAFRAME_NAME,
	dataframe_head_html,
	prepare_exercise_namespace,
)
from apps.exercises.descriptive_statistics import (
	descriptive_statistics_passes,
	prepare_descriptive_statistics,
)
from apps.exercises.markdown_utils import render_markdown_html
from apps.exercises.messy_dataset import messy_dataset_passes, prepare_messy_dataset, repair_messy_number
from apps.exercises.missing_values import (
	DatasetUnavailableError,
	UNAVAILABLE_MESSAGE,
	missing_values_imputation_passes,
)
try:
	from apps.exercises.ml_advanced_classification import (
		ml_advanced_classification_passes,
		prepare_ml_advanced_classification,
	)
	from apps.exercises.ml_classification import ml_classification_passes, prepare_ml_classification
	from apps.exercises.ml_data_prep import ml_data_prep_passes, prepare_ml_data_prep
	from apps.exercises.ml_ensembles import ml_ensembles_passes, prepare_ml_ensembles
	from apps.exercises.ml_regression import ml_regression_passes, prepare_ml_regression
	from apps.exercises.ml_unsupervised import ml_unsupervised_passes, prepare_ml_unsupervised

	ML_STACK_AVAILABLE = True
except ImportError:  # pragma: no cover - lite hosts omit sklearn/xgboost
	ML_STACK_AVAILABLE = False

	def _ml_unavailable(*_args, **_kwargs):
		raise RuntimeError(
			"Machine learning packages (scikit-learn / xgboost) are not installed on this host."
		)

	prepare_ml_data_prep = _ml_unavailable
	ml_data_prep_passes = _ml_unavailable
	prepare_ml_regression = _ml_unavailable
	ml_regression_passes = _ml_unavailable
	prepare_ml_classification = _ml_unavailable
	ml_classification_passes = _ml_unavailable
	prepare_ml_advanced_classification = _ml_unavailable
	ml_advanced_classification_passes = _ml_unavailable
	prepare_ml_ensembles = _ml_unavailable
	ml_ensembles_passes = _ml_unavailable
	prepare_ml_unsupervised = _ml_unavailable
	ml_unsupervised_passes = _ml_unavailable

from apps.exercises.pandas_intro import (
	build_patient_dataframe,
	dataframes_match,
	generate_pandas_intro_task,
	pandas_intro_task_passes,
	scalars_match,
)
from apps.exercises.plotting_bonus import evaluate_plotting_bonus, format_plotting_bonus_prompt
from apps.exercises.grading import (
	MODE_EVALUATE,
	MODE_RUN,
	BAND_INCOMPLETE,
	evaluate_with_graders,
	second_seed_config,
)
from apps.exercises.sandbox_hardening import (
	apply_resource_limits,
	blocked_path_attr_guard,
	harden_namespace_modules,
	restore_library_io_patches,
	scrub_worker_env,
)

SANDBOX_HELPERS = {
	"introduce_data_quality_issues": introduce_data_quality_issues,
	"data_quality_cleanup_passes": data_quality_cleanup_passes,
	"build_patient_dataframe": build_patient_dataframe,
	"generate_pandas_intro_task": generate_pandas_intro_task,
	"build_product_dataframe": build_product_dataframe,
	"generate_data_transformation_task": generate_data_transformation_task,
	"prepare_messy_dataset": prepare_messy_dataset,
	"repair_messy_number": repair_messy_number,
	"messy_dataset_passes": messy_dataset_passes,
	"prepare_ab_testing": prepare_ab_testing,
	"welch_ttest": welch_ttest,
	"ab_testing_passes": ab_testing_passes,
	"prepare_descriptive_statistics": prepare_descriptive_statistics,
	"descriptive_statistics_passes": descriptive_statistics_passes,
	"prepare_ml_data_prep": prepare_ml_data_prep,
	"ml_data_prep_passes": ml_data_prep_passes,
	"prepare_ml_regression": prepare_ml_regression,
	"ml_regression_passes": ml_regression_passes,
	"prepare_ml_classification": prepare_ml_classification,
	"ml_classification_passes": ml_classification_passes,
	"prepare_ml_advanced_classification": prepare_ml_advanced_classification,
	"ml_advanced_classification_passes": ml_advanced_classification_passes,
	"prepare_ml_ensembles": prepare_ml_ensembles,
	"ml_ensembles_passes": ml_ensembles_passes,
	"prepare_ml_unsupervised": prepare_ml_unsupervised,
	"ml_unsupervised_passes": ml_unsupervised_passes,
	"dataframes_match": dataframes_match,
	"scalars_match": scalars_match,
	"pandas_intro_task_passes": pandas_intro_task_passes,
	"data_transformation_passes": data_transformation_passes,
	"missing_values_imputation_passes": missing_values_imputation_passes,
}


DISALLOWED_NAMES = {
    "__builtins__",
    "__import__",
    "compile",
    "eval",
    "exec",
    "open",
    "globals",
    "locals",
    "vars",
    "help",
    "dir",
    "getattr",
    "setattr",
    "delattr",
    "object",
    "type",
    "input",
    "raw_input",
}

ALLOWED_AST_NODES = {
    ast.Add,
    ast.And,
    ast.Or,
    ast.Assign,
    ast.AugAssign,
    ast.Attribute,
    ast.BinOp,
    ast.BitAnd,
    ast.BitOr,
    ast.BitXor,
    ast.BoolOp,
    ast.Call,
    ast.Compare,
    ast.Constant,
    ast.Dict,
    ast.Div,
    ast.Eq,
    ast.Expr,
    ast.FloorDiv,
    ast.For,
    ast.Gt,
    ast.GtE,
    ast.If,
    ast.IfExp,
    ast.In,
    ast.Is,
    ast.IsNot,
    ast.List,
    ast.ListComp,
    ast.Load,
    ast.LShift,
    ast.Lt,
    ast.LtE,
    ast.Mod,
    ast.Module,
    ast.Mult,
    ast.Name,
    ast.Not,
    ast.NotIn,
    ast.Pow,
    ast.Raise,
    ast.RShift,
    ast.Slice,
    ast.Store,
    ast.Sub,
    ast.Subscript,
    ast.Tuple,
    ast.UnaryOp,
    ast.UAdd,
    ast.USub,
    # `lambda` powers .apply()/.agg()/sorted(key=...); its body is walked by the
    # same validator, so it inherits every other restriction.
    ast.Lambda,
    # `~` is the standard pandas mask negation: df[~df["a"].isna()].
    ast.Invert,
    ast.While,
    ast.comprehension,
    ast.keyword,
    ast.arguments,
    ast.arg,
    ast.DictComp,
    ast.Set,
    ast.SetComp,
    ast.GeneratorExp,
    ast.JoinedStr,
    ast.FormattedValue,
    ast.Assert,
    ast.Try,
    ast.ExceptHandler,
    ast.Return,
    ast.Pass,
    ast.Break,
    ast.Continue,
    ast.Starred,
    ast.Index,
    ast.NamedExpr,
}

# Learner-facing guidance for the AST features this sandbox does not allow.
BLOCKED_FEATURE_HELP = {
    "FunctionDef": (
        "Defining functions with `def` is not available here. Write the steps "
        "directly in the cell, or use a `lambda` inside .apply()."
    ),
    "AsyncFunctionDef": "Async code is not available in this exercise.",
    "ClassDef": "Defining classes is not available here. Work with `df` directly.",
    "With": (
        "`with` blocks are not available because file handling is disabled. "
        "Use the preloaded `df` instead of opening files."
    ),
    "Delete": "`del` is not available. Assign a new variable instead of deleting one.",
    "Global": "`global` is not available. Assign the variable directly in the cell.",
    "Nonlocal": "`nonlocal` is not available in this exercise.",
    "Await": "Async code is not available in this exercise.",
    "Yield": "Generators with `yield` are not available. Use a list comprehension.",
    "YieldFrom": "Generators with `yield` are not available. Use a list comprehension.",
    "MatMult": "The `@` matrix operator is not available. Use `.dot()` instead.",
}


def _blocked_feature_message(node_name: str) -> str:
    help_text = BLOCKED_FEATURE_HELP.get(node_name)
    if help_text:
        return help_text
    return (
        f"`{node_name}` is not available in this exercise sandbox. "
        "Stick to pandas, numpy, and matplotlib operations on the preloaded data."
    )


CANONICAL_ALIASES = {
    "numpy": "np",
    "pandas": "pd",
    "matplotlib.pyplot": "plt",
}
# Optional on full hosts; omitted from lite requirements to stay under disk quota.
if ML_STACK_AVAILABLE:
    CANONICAL_ALIASES["seaborn"] = "sns"


SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "next": next,
    "print": print,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "ValueError": ValueError,
    "TypeError": TypeError,
    "Exception": Exception,
}


def split_notebook_source(source: str) -> list[dict[str, str]]:
    source = (source or "").strip()
    if not source:
        return [{"source": ""}]

    cells: list[str] = []
    current: list[str] = []
    for line in source.splitlines():
        if line.strip() == "# %%":
            cells.append("\n".join(current).strip("\n"))
            current = []
            continue
        current.append(line)
    cells.append("\n".join(current).strip("\n"))

    return [{"source": cell} for cell in cells if cell.strip()] or [{"source": ""}]


def _source_hash(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _import_is_allowed(module_name: str | None, allowed_imports: list[str]) -> bool:
    if not module_name:
        return False
    name = module_name.lstrip(".")
    allowed = [str(item).strip() for item in (allowed_imports or []) if str(item).strip()]
    for entry in allowed:
        if name == entry or name.startswith(f"{entry}.") or entry.startswith(f"{name}."):
            return True
        if name.split(".", 1)[0] == entry.split(".", 1)[0]:
            return True
    return False


def _make_safe_import(allowed_imports: list[str]):
    def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
        if level:
            raise ImportError("Relative imports are not available in this exercise.")
        if not _import_is_allowed(name, allowed_imports):
            raise ImportError(
                f"Import of `{name}` is not allowed for this exercise. "
                "Use the preloaded libraries listed in the task prompt."
            )
        module = importlib.import_module(name)
        # Match builtin __import__: dotted `import pkg.mod` returns the top-level package
        # unless fromlist is non-empty (as with `from pkg.mod import ...`).
        if fromlist:
            return module
        if "." in name:
            return importlib.import_module(name.split(".", 1)[0])
        return module

    return _safe_import


def _validate_imports(tree: ast.AST, allowed_imports: list[str]) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.alias):
            # Visited as children of Import / ImportFrom; validated on the parent.
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not _import_is_allowed(alias.name, allowed_imports):
                    raise ImportError(
                        f"Import of `{alias.name}` is not allowed for this exercise. "
                        "Use the preloaded libraries listed in the task prompt."
                    )
            continue
        if isinstance(node, ast.ImportFrom):
            if not _import_is_allowed(node.module, allowed_imports):
                raise ImportError(
                    f"Import from `{node.module or '?'}` is not allowed for this exercise. "
                    "Use the preloaded libraries listed in the task prompt."
                )
            continue
        if type(node) not in ALLOWED_AST_NODES:
            raise ValueError(_blocked_feature_message(type(node).__name__))
        if isinstance(node, ast.Name) and node.id in DISALLOWED_NAMES and node.id != "__import__":
            raise ValueError(
                f"`{node.id}` is not available in this exercise sandbox."
            )
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise ValueError(
                "Attributes starting with `_` are internal and blocked in this exercise."
            )
        if isinstance(node, ast.Attribute) and blocked_path_attr_guard(node.attr):
            raise ValueError(f"This code uses a blocked attribute: {node.attr}.")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in DISALLOWED_NAMES and node.func.id != "__import__":
                raise ValueError(f"This code calls a blocked function: {node.func.id}.")
            if isinstance(node.func, ast.Attribute) and node.func.attr.startswith("_"):
                raise ValueError("Private methods are blocked in this exercise.")
            if isinstance(node.func, ast.Attribute) and blocked_path_attr_guard(node.func.attr):
                raise ValueError(f"This code calls a blocked method: {node.func.attr}.")


def _load_allowed_modules(allowed_imports: list[str]) -> dict[str, object]:
    namespace: dict[str, object] = {}
    for import_name in allowed_imports:
        module = importlib.import_module(import_name)
        alias = CANONICAL_ALIASES.get(import_name, import_name.rsplit(".", 1)[-1])
        namespace[alias] = module
        namespace[import_name.rsplit(".", 1)[-1]] = module
        if import_name == "matplotlib.pyplot":
            namespace["matplotlib"] = importlib.import_module("matplotlib")
    return namespace


def _build_namespace(allowed_imports: list[str], data_state: dict) -> dict[str, object]:
    # Inline sandboxes mutate process-global pandas/numpy; restore before host
    # dataset prep so read_csv / to_csv caching still works.
    restore_library_io_patches()
    builtins = SAFE_BUILTINS.copy()
    builtins["__import__"] = _make_safe_import(allowed_imports)
    namespace: dict[str, object] = {"__builtins__": builtins}
    namespace.update(_load_allowed_modules(allowed_imports))
    namespace.update(SANDBOX_HELPERS)
    namespace["data"] = deepcopy(data_state)
    namespace["state"] = namespace["data"]
    namespace["features"] = deepcopy(data_state.get("features", {})) if isinstance(data_state, dict) else {}
    # Always expose the working table as `df` when the exercise provides one.
    prepared = prepare_exercise_namespace(data_state)
    reference_plot = prepared.pop("reference_plot", None)
    namespace.update(prepared)
    if DATAFRAME_NAME in prepared:
        namespace[DATAFRAME_NAME] = prepared[DATAFRAME_NAME]
    if reference_plot is not None:
        namespace["data"]["reference_plot"] = reference_plot
        namespace["data"].pop("dataset_preview_html", None)
    else:
        namespace["data"].pop("reference_plot", None)
        preview_html = dataframe_head_html(prepared.get(DATAFRAME_NAME))
        if preview_html:
            namespace["data"]["dataset_preview_html"] = preview_html
        else:
            namespace["data"].pop("dataset_preview_html", None)
    if "target" in prepared:
        namespace["data"]["target"] = prepared["target"]
    if "outcome" in prepared:
        namespace["data"]["outcome"] = prepared["outcome"]
    # Patch library I/O only after server-side dataset prep/caching is done.
    harden_namespace_modules(namespace)
    return namespace


def _unavailable_result(data_state: dict | None, message: str = UNAVAILABLE_MESSAGE) -> dict[str, object]:
    return {
        "success": False,
        "ran": False,
        "core_passed": False,
        "band": BAND_INCOMPLETE,
        "cells": [
            {
                "source": "",
                "source_hash": "",
                "stdout": "",
                "value_repr": None,
                "html": None,
                "error": message,
                "figures": [],
                "figure_reused": False,
            }
        ],
        "namespace": {},
        "completed_cells": 0,
        "evaluation": {
            "passed": False,
            "core_passed": False,
            "band": BAND_INCOMPLETE,
            "summary": message,
            "checks": [],
            "rubric": {},
            "mode": MODE_EVALUATE,
        },
        "progress": {"summary": message, "passed": False, "completed_cells": 0, "ran": False},
        "data_state": data_state or {},
        "task_prompt": "",
        "task_prompt_html": "",
        "plotting_bonus": {
            "attempted": False,
            "passed": False,
            "kind_matched": False,
            "plots_created": 0,
            "modifications_count": 0,
            "modification_categories": [],
            "modifications_required": 0,
            "message": message,
        },
        "error": message,
    }


def _capture_figures(namespace: dict[str, object]) -> list[dict[str, str]]:
    plt = namespace.get("plt")
    if plt is None:
        return []

    figures = []
    for figure_number in plt.get_fignums():
        figure = plt.figure(figure_number)
        from matplotlib.backends.backend_agg import FigureCanvasAgg

        buffer = io.BytesIO()
        FigureCanvasAgg(figure).print_png(buffer)
        figures.append(
            {
                "figure_number": figure_number,
                "mime_type": "image/png",
                "base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
            }
        )
    return figures


def _value_to_html(value: object) -> str | None:
    pandas = sys.modules.get("pandas")
    if pandas is None:
        try:
            pandas = importlib.import_module("pandas")
        except Exception:
            return None

    frame = None
    if isinstance(value, pandas.DataFrame):
        frame = value
    elif isinstance(value, pandas.Series):
        frame = value.to_frame()
    if frame is None:
        return None

    preview = frame.head(10)
    return preview.to_html(
        classes="dataframe-preview",
        border=0,
        index=True,
        justify="left",
        max_cols=12,
        escape=True,
    )


def _empty_cell_result(source: str, *, cell_type: str = "code") -> dict[str, object]:
    return {
        "source": source,
        "source_hash": _source_hash(source),
        "stdout": "",
        "value_repr": None,
        "html": None,
        "error": None,
        "figures": [],
        "figure_reused": False,
        "cell_type": cell_type,
    }


def _execute_cell_local(
    source: str,
    namespace: dict[str, object],
    allowed_imports: list[str],
    *,
    cell_type: str = "code",
) -> dict[str, object]:
    if (cell_type or "code") == "markdown":
        return _empty_cell_result(source, cell_type="markdown")

    result = _empty_cell_result(source, cell_type="code")

    stdout = io.StringIO()
    try:
        tree = ast.parse(source or "", mode="exec")
        _validate_imports(tree, allowed_imports)

        with redirect_stdout(stdout):
            if tree.body and isinstance(tree.body[-1], ast.Expr):
                prefix = ast.Module(body=tree.body[:-1], type_ignores=[])
                if prefix.body:
                    exec(compile(prefix, "<exercise-cell>", "exec"), namespace, namespace)
                expression = ast.Expression(tree.body[-1].value)
                value = eval(compile(expression, "<exercise-cell>", "eval"), namespace, namespace)
                if value is not None:
                    result["html"] = _value_to_html(value)
                    if result["html"]:
                        result["value_repr"] = f"{type(value).__name__} shape={getattr(value, 'shape', '')}"
                    else:
                        result["value_repr"] = repr(value)
            else:
                exec(compile(tree, "<exercise-cell>", "exec"), namespace, namespace)
    except Exception:
        result["error"] = traceback.format_exc()
        result["stdout"] = stdout.getvalue()
        return result

    result["stdout"] = stdout.getvalue()
    result["figures"] = _capture_figures(namespace)
    return result


def _run_notebook_payload(
    cells: list[dict[str, str]],
    allowed_imports: list[str],
    data_state: dict,
    previous_results: list[dict[str, object]] | None,
    evaluation_rules: dict | None,
    mode: str = MODE_EVALUATE,
    soft_skill_response: str | None = None,
    soft_skill_prompt: str | None = None,
    skip_second_seed: bool = False,
    reveal_expected: bool = False,
) -> dict[str, object]:
    try:
        return _run_notebook_payload_impl(
            cells=cells,
            allowed_imports=allowed_imports,
            data_state=data_state,
            previous_results=previous_results,
            evaluation_rules=evaluation_rules,
            mode=mode,
            soft_skill_response=soft_skill_response,
            soft_skill_prompt=soft_skill_prompt,
            skip_second_seed=skip_second_seed,
            reveal_expected=reveal_expected,
        )
    finally:
        # Inline sandbox patches process-global pandas/numpy; always undo.
        restore_library_io_patches()


def _run_notebook_payload_impl(
    cells: list[dict[str, str]],
    allowed_imports: list[str],
    data_state: dict,
    previous_results: list[dict[str, object]] | None,
    evaluation_rules: dict | None,
    mode: str = MODE_EVALUATE,
    soft_skill_response: str | None = None,
    soft_skill_prompt: str | None = None,
    skip_second_seed: bool = False,
    reveal_expected: bool = False,
) -> dict[str, object]:
    from django.conf import settings as django_settings

    if getattr(django_settings, "EXERCISE_ENABLE_RESOURCE_LIMITS", True):
        # Keep the CPU budget just above the wall-clock timeout so runaway code
        # hits the rlimit rather than only being killed from the parent side.
        apply_resource_limits(
            cpu_seconds=int(getattr(django_settings, "EXERCISE_RUN_TIMEOUT", 45)) + 15
        )
    previous_by_hash = {
        cell.get("source_hash"): cell
        for cell in previous_results or []
        if cell.get("source_hash")
    }
    mode = MODE_RUN if mode == MODE_RUN else MODE_EVALUATE
    try:
        namespace = _build_namespace(allowed_imports, data_state or {})
    except DatasetUnavailableError as exc:
        return _unavailable_result(data_state, str(exc) or UNAVAILABLE_MESSAGE)

    if soft_skill_prompt and isinstance(namespace.get("data"), dict):
        namespace["data"]["soft_skill_prompt"] = soft_skill_prompt

    results = []
    completed_cells = 0
    last_error = None

    for cell in cells:
        source = cell.get("source", "")
        cell_type = str(cell.get("cell_type") or "code")
        result = _execute_cell_local(
            source,
            namespace,
            allowed_imports,
            cell_type=cell_type,
        )
        cached_cell = previous_by_hash.get(result["source_hash"])
        if cached_cell and cached_cell.get("figures") and not result["error"]:
            result["figures"] = cached_cell["figures"]
            result["figure_reused"] = True
        results.append(result)
        completed_cells += 1
        if result["error"]:
            last_error = result["error"]
            break

    ran = last_error is None
    cell_sources = [
        cell.get("source", "")
        for cell in cells[:completed_cells]
        if str(cell.get("cell_type") or "code") != "markdown"
    ]
    # Optional exercise outputs — avoid NameError in assertion expressions.
    for optional in (
        "answer",
        "different",
        "relevant",
        "p_value",
        "plotted",
        "df0",
        "df1",
        "df2",
        "numeric_columns",
    ):
        namespace.setdefault(optional, None)
    task = namespace.get("task")
    from apps.exercises.notebook_layout import with_preloaded_libraries_note

    task_prompt = ""
    plotting_bonus_prompt = ""
    if isinstance(task, dict):
        task_prompt = str(task.get("prompt") or "").strip()
        plotting_bonus_prompt = format_plotting_bonus_prompt(task.get("plotting_bonus"))
    task_prompt = with_preloaded_libraries_note(task_prompt, allowed_imports)

    # Run executes code only. Grading / rubric / soft feedback happen on Evaluate.
    if mode == MODE_RUN:
        summary = (
            "Notebook ran successfully. Click Evaluate Exercise when you want credit."
            if ran
            else "Notebook stopped on an error. Fix it, then run again."
        )
        evaluation = {
            "mode": MODE_RUN,
            "passed": False,
            "core_passed": False,
            "band": BAND_INCOMPLETE,
            "summary": summary,
            "checks": [],
            "rubric": None,
            "soft_feedback": None,
            "plotting_bonus": None,
            "reveal_expected": False,
            "answer_feedback": {"revealed": False, "can_reveal": False, "policy": "hide", "items": []},
        }
        progress = {
            "summary": summary,
            "passed": False,
            "completed_cells": completed_cells,
            "ran": ran,
            "band": BAND_INCOMPLETE,
            "mode": MODE_RUN,
        }
        return {
            "success": bool(ran),
            "ran": ran,
            "core_passed": False,
            "band": BAND_INCOMPLETE,
            "mode": MODE_RUN,
            "cells": results,
            "namespace": {
                key: repr(value)
                for key, value in namespace.items()
                if key not in {"__builtins__"}
            },
            "completed_cells": completed_cells,
            "evaluation": evaluation,
            "progress": progress,
            "data_state": namespace.get("data", data_state or {}),
            "task_prompt": task_prompt,
            "task_prompt_html": str(render_markdown_html(task_prompt)) if task_prompt else "",
            "plotting_bonus_prompt": plotting_bonus_prompt,
            "plotting_bonus_prompt_html": (
                str(render_markdown_html(plotting_bonus_prompt)) if plotting_bonus_prompt else ""
            ),
            "plotting_bonus": None,
            "soft_feedback": None,
            "error": last_error,
        }

    bonus_spec = task.get("plotting_bonus") if isinstance(task, dict) else None
    figure_count = sum(len(item.get("figures") or []) for item in results)
    plotting_bonus = evaluate_plotting_bonus(
        bonus=bonus_spec if isinstance(bonus_spec, dict) else None,
        cell_sources=cell_sources,
        figure_count=figure_count,
    )

    evaluation = evaluate_with_graders(
        namespace,
        evaluation_rules or {},
        mode=MODE_EVALUATE,
        cell_sources=cell_sources,
        soft_skill_response=soft_skill_response,
        plotting_bonus=plotting_bonus,
        reveal_expected=reveal_expected,
        second_seed_ok=None,
        soft_skill_prompt=soft_skill_prompt,
    )

    from django.conf import settings as django_settings

    if (
        ran
        and not skip_second_seed
        and evaluation.get("core_passed")
        and second_seed_config(evaluation_rules).get("enabled")
        and getattr(django_settings, "EXERCISE_ENABLE_SECOND_SEED", True)
    ):
        offset = int(second_seed_config(evaluation_rules).get("seed_offset") or 10007)
        alt_state = deepcopy(data_state or {})
        alt_state["seed"] = int(alt_state.get("seed", 42) or 42) + offset
        for key in ("reference_plot", "dataset_preview_html"):
            alt_state.pop(key, None)
        try:
            alt = _run_notebook_payload(
                cells=cells,
                allowed_imports=allowed_imports,
                data_state=alt_state,
                previous_results=None,
                evaluation_rules=evaluation_rules,
                mode=MODE_EVALUATE,
                soft_skill_response=soft_skill_response,
                soft_skill_prompt=soft_skill_prompt,
                skip_second_seed=True,
                reveal_expected=False,
            )
            second_seed_ok = bool(alt.get("core_passed") or alt.get("evaluation", {}).get("core_passed"))
        except Exception:
            second_seed_ok = False
        if second_seed_ok is False:
            evaluation = evaluate_with_graders(
                namespace,
                evaluation_rules or {},
                mode=MODE_EVALUATE,
                cell_sources=cell_sources,
                soft_skill_response=soft_skill_response,
                plotting_bonus=plotting_bonus,
                reveal_expected=reveal_expected,
                second_seed_ok=False,
                soft_skill_prompt=soft_skill_prompt,
            )

    core_passed = bool(evaluation.get("core_passed")) if ran else False
    success = bool(ran and core_passed)

    progress = {
        "summary": evaluation.get("summary", ""),
        "passed": bool(core_passed),
        "completed_cells": completed_cells,
        "ran": ran,
        "band": evaluation.get("band") or BAND_INCOMPLETE,
        "mode": MODE_EVALUATE,
    }

    return {
        "success": success,
        "ran": ran,
        "core_passed": core_passed,
        "band": evaluation.get("band") or BAND_INCOMPLETE,
        "mode": MODE_EVALUATE,
        "cells": results,
        "namespace": {
            key: repr(value)
            for key, value in namespace.items()
            if key not in {"__builtins__"}
        },
        "completed_cells": completed_cells,
        "evaluation": evaluation,
        "progress": progress,
        "data_state": namespace.get("data", data_state or {}),
        "task_prompt": task_prompt,
        "task_prompt_html": str(render_markdown_html(task_prompt)) if task_prompt else "",
        "plotting_bonus_prompt": plotting_bonus_prompt,
        "plotting_bonus_prompt_html": (
            str(render_markdown_html(plotting_bonus_prompt)) if plotting_bonus_prompt else ""
        ),
        "plotting_bonus": plotting_bonus,
        "soft_feedback": None,
        "error": last_error,
    }


def evaluate_notebook(namespace: dict[str, object], evaluation_rules: dict) -> dict[str, object]:
    """Backward-compatible wrapper around the typed grading engine."""
    return evaluate_with_graders(
        namespace,
        evaluation_rules or {},
        mode=MODE_EVALUATE,
        cell_sources=[],
        plotting_bonus=None,
    )


class _WorkerResult:
    __slots__ = ("returncode", "stdout", "stderr")

    def __init__(self, returncode: int, stdout: str, stderr: str):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _looks_like_python_executable(path: str) -> bool:
    base = os.path.basename(path or "").lower()
    return "python" in base and "uwsgi" not in base


def _resolve_worker_python() -> str:
    """Return a real Python binary.

    Under PythonAnywhere web workers ``sys.executable`` is often uWSGI, which
    cannot run ``python -c ...`` notebook workers. Prefer the virtualenv.
    """
    candidates: list[str] = []
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        candidates.extend(
            [
                os.path.join(venv, "bin", "python"),
                os.path.join(venv, "bin", "python3"),
            ]
        )
    candidates.extend(
        [
            os.path.join(sys.prefix, "bin", "python"),
            os.path.join(sys.prefix, "bin", "python3"),
        ]
    )
    exe = sys.executable or ""
    if _looks_like_python_executable(exe):
        candidates.append(exe)
    for path in candidates:
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return exe or "python3"


def _run_worker(command, stdin_payload, cwd, env, timeout_seconds):
    """Run the sandbox worker in its own process group so a timeout kills any children."""
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
        env=env,
        start_new_session=True,
        close_fds=True,
    )
    try:
        stdout, stderr = process.communicate(stdin_payload, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _terminate_process_group(process)
        process.communicate()
        raise
    return _WorkerResult(process.returncode, stdout, stderr)


def _terminate_process_group(process) -> None:
    try:
        os.killpg(os.getpgid(process.pid), 9)
    except Exception:
        process.kill()


def _worker_failure_result(data_state: dict | None, summary: str, error: str) -> dict[str, object]:
    return {
        "success": False,
        "ran": False,
        "core_passed": False,
        "band": BAND_INCOMPLETE,
        "cells": [],
        "namespace": {},
        "completed_cells": 0,
        "evaluation": {
            "passed": False,
            "core_passed": False,
            "summary": summary,
            "checks": [],
            "band": BAND_INCOMPLETE,
        },
        "progress": {"summary": summary, "passed": False, "completed_cells": 0, "ran": False},
        "data_state": data_state or {},
        "error": error,
    }


def run_notebook(
    cells: list[dict[str, str]],
    allowed_imports: list[str],
    data_state: dict | None = None,
    previous_results: list[dict[str, object]] | None = None,
    evaluation_rules: dict | None = None,
    mode: str = MODE_EVALUATE,
    soft_skill_response: str | None = None,
    soft_skill_prompt: str | None = None,
    reveal_expected: bool = False,
) -> dict[str, object]:
    from django.conf import settings as django_settings

    payload_kwargs = {
        "cells": cells,
        "allowed_imports": allowed_imports,
        "data_state": data_state or {},
        "previous_results": previous_results or [],
        "evaluation_rules": evaluation_rules or {},
        "mode": mode,
        "soft_skill_response": soft_skill_response,
        "soft_skill_prompt": soft_skill_prompt,
        "reveal_expected": reveal_expected,
    }

    # In-process path for hosts where web workers cannot spawn a real Python
    # child (notably PythonAnywhere, where sys.executable may be uWSGI).
    inline = bool(getattr(django_settings, "EXERCISE_INLINE_SANDBOX", False))
    worker_python = _resolve_worker_python()
    if inline or not _looks_like_python_executable(worker_python):
        try:
            return _run_notebook_payload(**payload_kwargs)
        except Exception as exc:
            return _worker_failure_result(
                data_state,
                f"Notebook execution failed: {exc}",
                traceback.format_exc(),
            )

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    env = scrub_worker_env(os.environ)
    pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = project_root if not pythonpath else f"{project_root}{os.pathsep}{pythonpath}"
    env["EXERCISE_SANDBOX_WORKER"] = "1"
    env["DJANGO_SETTINGS_MODULE"] = env.get("DJANGO_SETTINGS_MODULE") or "project_core.settings"

    env["EXERCISE_ENABLE_RESOURCE_LIMITS"] = (
        "1" if getattr(django_settings, "EXERCISE_ENABLE_RESOURCE_LIMITS", True) else "0"
    )
    env["EXERCISE_ENABLE_SECOND_SEED"] = (
        "1" if getattr(django_settings, "EXERCISE_ENABLE_SECOND_SEED", True) else "0"
    )
    # Never pass host secrets into the worker environment.
    for key in list(env):
        upper = key.upper()
        if upper == "DJANGO_SECRET_KEY" or upper.startswith("DB_") or upper in {
            "DATABASE_URL",
            "EMAIL_HOST_PASSWORD",
            "EMAIL_HOST_USER",
            "ADMIN_EMAIL",
        }:
            env.pop(key, None)

    command = [
        worker_python,
        "-c",
        (
            "import json, sys; "
            "payload = json.loads(sys.stdin.read()); "
            "from apps.exercises.services import _run_notebook_payload; "
            "result = _run_notebook_payload(**payload); "
            "print(json.dumps(result))"
        ),
    ]

    timeout_seconds = int(getattr(django_settings, "EXERCISE_RUN_TIMEOUT", 45))
    try:
        completed = _run_worker(
            command, json.dumps(payload_kwargs), project_root, env, timeout_seconds
        )
    except subprocess.TimeoutExpired:
        return _worker_failure_result(
            data_state,
            "Notebook execution timed out.",
            "Execution timed out in isolated worker.",
        )
    except OSError as exc:
        # Last resort on restricted hosts: run in-process.
        try:
            return _run_notebook_payload(**payload_kwargs)
        except Exception:
            return _worker_failure_result(
                data_state,
                f"Could not start notebook worker: {exc}",
                str(exc),
            )

    if completed.returncode != 0:
        stderr = completed.stderr.strip() or "Notebook worker exited without returning a result."
        # uWSGI mis-invocation still shows up if path resolution was wrong.
        if "unable to load configuration" in stderr.lower() or "uwsgi" in stderr.lower():
            return _run_notebook_payload(**payload_kwargs)
        return _worker_failure_result(data_state, stderr, stderr)

    try:
        return json.loads(completed.stdout.strip().splitlines()[-1])
    except Exception:
        return _worker_failure_result(
            data_state,
            "Invalid worker response.",
            completed.stdout or completed.stderr or "Invalid worker response.",
        )
