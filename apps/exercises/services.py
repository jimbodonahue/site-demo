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
from apps.exercises.pandas_intro import (
	build_patient_dataframe,
	dataframes_match,
	generate_pandas_intro_task,
	pandas_intro_task_passes,
	scalars_match,
)
from apps.exercises.plotting_bonus import evaluate_plotting_bonus
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
	scrub_worker_env,
)

SANDBOX_HELPERS = {
	"build_patient_dataframe": build_patient_dataframe,
	"generate_pandas_intro_task": generate_pandas_intro_task,
	"build_product_dataframe": build_product_dataframe,
	"generate_data_transformation_task": generate_data_transformation_task,
	"dataframes_match": dataframes_match,
	"scalars_match": scalars_match,
	"pandas_intro_task_passes": pandas_intro_task_passes,
	"data_transformation_passes": data_transformation_passes,
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

CANONICAL_ALIASES = {
    "numpy": "np",
    "pandas": "pd",
    "matplotlib.pyplot": "plt",
}

SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "int": int,
    "isinstance": isinstance,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "next": next,
    "print": print,
    "range": range,
    "reversed": reversed,
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
    "KeyError": KeyError,
    "IndexError": IndexError,
    "NameError": NameError,
    "ZeroDivisionError": ZeroDivisionError,
}

# Marker so the parent can find the worker payload even if libraries write to stdout.
WORKER_RESULT_PREFIX = "EXERCISE_RESULT_JSON:"


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


def _validate_imports(tree: ast.AST, allowed_imports: list[str]) -> None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise ImportError(
                "Import statements are blocked for this exercise. Use the preloaded libraries instead."
            )
        if type(node) not in ALLOWED_AST_NODES:
            raise ValueError(
                f"This code uses a blocked language feature: {type(node).__name__}."
            )
        if isinstance(node, ast.Name) and node.id in DISALLOWED_NAMES:
            raise ValueError(f"This code uses a blocked name: {node.id}.")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise ValueError("Private attributes are blocked in this exercise.")
        if isinstance(node, ast.Attribute) and blocked_path_attr_guard(node.attr):
            raise ValueError(f"This code uses a blocked attribute: {node.attr}.")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in DISALLOWED_NAMES:
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
    namespace: dict[str, object] = {"__builtins__": SAFE_BUILTINS.copy()}
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


def _unavailable_result(data_state: dict | None, message: str = "Dataset unavailable.") -> dict[str, object]:
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
    try:
        plt.close("all")
    except Exception:
        pass
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
    try:
        return preview.to_html(
            classes="dataframe-preview",
            border=0,
            index=True,
            justify="left",
            max_cols=12,
            escape=True,
        )
    except Exception:
        return None


def _install_cell_print(namespace: dict[str, object], stdout: io.StringIO):
    """Force sandbox print() into the cell capture buffer (not the worker pipe)."""
    real_print = print

    def cell_print(*args, **kwargs):
        file = kwargs.get("file", stdout)
        if file is None or file is sys.stdout:
            kwargs = dict(kwargs)
            kwargs["file"] = stdout
        real_print(*args, **kwargs)

    builtins = namespace.get("__builtins__")
    if isinstance(builtins, dict):
        builtins = dict(builtins)
        builtins["print"] = cell_print
        namespace["__builtins__"] = builtins
    namespace["print"] = cell_print
    return cell_print


def _execute_cell_local(source: str, namespace: dict[str, object], allowed_imports: list[str]) -> dict[str, object]:
    result = {
        "source": source,
        "source_hash": _source_hash(source),
        "stdout": "",
        "value_repr": None,
        "html": None,
        "error": None,
        "figures": [],
        "figure_reused": False,
    }

    stdout = io.StringIO()
    previous_print = namespace.get("print")
    previous_builtins = namespace.get("__builtins__")
    try:
        tree = ast.parse(source or "", mode="exec")
        _validate_imports(tree, allowed_imports)
        _install_cell_print(namespace, stdout)

        value = None
        with redirect_stdout(stdout):
            if tree.body and isinstance(tree.body[-1], ast.Expr):
                prefix = ast.Module(body=tree.body[:-1], type_ignores=[])
                if prefix.body:
                    exec(compile(prefix, "<exercise-cell>", "exec"), namespace, namespace)
                expression = ast.Expression(tree.body[-1].value)
                value = eval(compile(expression, "<exercise-cell>", "eval"), namespace, namespace)
            else:
                exec(compile(tree, "<exercise-cell>", "exec"), namespace, namespace)

        if value is not None:
            result["html"] = _value_to_html(value)
            if result["html"]:
                result["value_repr"] = f"{type(value).__name__} shape={getattr(value, 'shape', '')}"
            else:
                result["value_repr"] = repr(value)
    except Exception:
        result["error"] = traceback.format_exc()
        result["stdout"] = stdout.getvalue()
        return result
    finally:
        if previous_builtins is not None:
            namespace["__builtins__"] = previous_builtins
        if previous_print is not None:
            namespace["print"] = previous_print
        elif "print" in namespace:
            namespace.pop("print", None)

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
    from django.conf import settings as django_settings

    # Never apply rlimits in the web process — only inside the isolated worker.
    if (
        os.environ.get("EXERCISE_SANDBOX_WORKER") == "1"
        and getattr(django_settings, "EXERCISE_ENABLE_RESOURCE_LIMITS", True)
    ):
        apply_resource_limits()
    previous_by_hash = {
        cell.get("source_hash"): cell
        for cell in previous_results or []
        if cell.get("source_hash")
    }
    mode = MODE_RUN if mode == MODE_RUN else MODE_EVALUATE
    namespace = _build_namespace(allowed_imports, data_state or {})

    if soft_skill_prompt and isinstance(namespace.get("data"), dict):
        namespace["data"]["soft_skill_prompt"] = soft_skill_prompt

    results = []
    completed_cells = 0
    last_error = None

    for cell in cells:
        source = cell.get("source", "")
        result = _execute_cell_local(source, namespace, allowed_imports)
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
    cell_sources = [cell.get("source", "") for cell in cells[:completed_cells]]
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
        mode=mode,
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
        and mode == MODE_EVALUATE
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
                mode=mode,
                cell_sources=cell_sources,
                soft_skill_response=soft_skill_response,
                plotting_bonus=plotting_bonus,
                reveal_expected=reveal_expected,
                second_seed_ok=False,
                soft_skill_prompt=soft_skill_prompt,
            )

    core_passed = bool(evaluation.get("core_passed")) if ran else False
    success = bool(ran) if mode == MODE_RUN else bool(ran and core_passed)

    progress = {
        "summary": evaluation.get("summary", ""),
        "passed": bool(core_passed) if mode == MODE_EVALUATE else False,
        "completed_cells": completed_cells,
        "ran": ran,
        "band": evaluation.get("band") or BAND_INCOMPLETE,
        "mode": mode,
    }
    task_prompt = ""
    if isinstance(task, dict):
        task_prompt = str(task.get("prompt") or "").strip()

    return {
        "success": success,
        "ran": ran,
        "core_passed": core_passed,
        "band": evaluation.get("band") or BAND_INCOMPLETE,
        "mode": mode,
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
        "plotting_bonus": plotting_bonus,
        "soft_feedback": evaluation.get("soft_feedback"),
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
    payload = {
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

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    env = scrub_worker_env(os.environ)
    pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = project_root if not pythonpath else f"{project_root}{os.pathsep}{pythonpath}"
    env["EXERCISE_SANDBOX_WORKER"] = "1"
    env["DJANGO_SETTINGS_MODULE"] = env.get("DJANGO_SETTINGS_MODULE") or "project_core.settings"
    from django.conf import settings as django_settings

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
        sys.executable,
        "-c",
        (
            "import json, sys; "
            "payload = json.loads(sys.stdin.read()); "
            "from apps.exercises.services import WORKER_RESULT_PREFIX, _run_notebook_payload; "
            "result = _run_notebook_payload(**payload); "
            "sys.stdout.write(WORKER_RESULT_PREFIX + json.dumps(result) + '\\n'); "
            "sys.stdout.flush()"
        ),
    ]

    try:
        completed = subprocess.run(
            command,
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=120,
            cwd=project_root,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
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
                "summary": "Notebook execution timed out.",
                "checks": [],
                "band": BAND_INCOMPLETE,
            },
            "progress": {
                "summary": "Notebook execution timed out.",
                "passed": False,
                "completed_cells": 0,
                "ran": False,
            },
            "data_state": data_state or {},
            "error": "Execution timed out in isolated worker.",
        }

    if completed.returncode != 0:
        stderr = completed.stderr.strip() or "Notebook worker exited without returning a result."
        # Fall back to in-process execution when the isolated worker cannot run
        # (common on some shared hosts that restrict subprocesses).
        try:
            return _run_notebook_payload(**payload)
        except Exception:
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
                    "summary": stderr,
                    "checks": [],
                    "band": BAND_INCOMPLETE,
                },
                "progress": {"summary": stderr, "passed": False, "completed_cells": 0, "ran": False},
                "data_state": data_state or {},
                "error": stderr,
            }

    try:
        return _parse_worker_stdout(completed.stdout)
    except Exception:
        # Worker stdout was unusable; try in-process once before failing hard.
        try:
            return _run_notebook_payload(**payload)
        except Exception:
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
                    "summary": "Invalid worker response.",
                    "checks": [],
                    "band": BAND_INCOMPLETE,
                },
                "progress": {
                    "summary": "Invalid worker response.",
                    "passed": False,
                    "completed_cells": 0,
                    "ran": False,
                },
                "data_state": data_state or {},
                "error": completed.stdout or completed.stderr or "Invalid worker response.",
            }


def _parse_worker_stdout(stdout: str) -> dict[str, object]:
    """Extract the notebook result JSON from worker stdout."""
    lines = (stdout or "").strip().splitlines()
    for line in reversed(lines):
        if line.startswith(WORKER_RESULT_PREFIX):
            return json.loads(line[len(WORKER_RESULT_PREFIX) :])
    if not lines:
        raise ValueError("Worker returned no stdout.")
    # Backward-compatible: last line is bare JSON.
    return json.loads(lines[-1])
