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
from apps.exercises.dataframe_providers import DATAFRAME_NAME, prepare_exercise_namespace
from apps.exercises.pandas_intro import (
	build_patient_dataframe,
	dataframes_match,
	generate_pandas_intro_task,
	pandas_intro_task_passes,
	scalars_match,
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
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in DISALLOWED_NAMES:
                raise ValueError(f"This code calls a blocked function: {node.func.id}.")
            if isinstance(node.func, ast.Attribute) and node.func.attr.startswith("_"):
                raise ValueError("Private methods are blocked in this exercise.")


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
    if "target" in prepared:
        namespace["data"]["target"] = prepared["target"]
    if "outcome" in prepared:
        namespace["data"]["outcome"] = prepared["outcome"]
    return namespace


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
    plt.close("all")
    return figures


def _snapshot_namespace(namespace: dict[str, object]) -> dict[str, object]:
    snapshot: dict[str, object] = {}
    for key, value in namespace.items():
        if key in {"__builtins__"}:
            continue
        if isinstance(value, types.ModuleType):
            continue
        try:
            snapshot[key] = deepcopy(value)
        except Exception:
            snapshot[key] = value
    return snapshot


def _restore_namespace(base_namespace: dict[str, object], snapshot: dict[str, object]) -> dict[str, object]:
    restored = dict(base_namespace)
    for key, value in snapshot.items():
        try:
            restored[key] = deepcopy(value)
        except Exception:
            restored[key] = value
    return restored


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
) -> dict[str, object]:
    previous_by_hash = {cell.get("source_hash"): cell for cell in previous_results or [] if cell.get("source_hash")}
    namespace = _build_namespace(allowed_imports, data_state or {})

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

    evaluation = evaluate_notebook(namespace, evaluation_rules or {}) if evaluation_rules else {"passed": True, "summary": "", "checks": []}
    success = not last_error and evaluation.get("passed", True)
    progress = {
        "summary": evaluation.get("summary", "") if success else evaluation.get("summary", "Review the notebook and try again."),
        "passed": bool(success),
        "completed_cells": completed_cells,
    }
    task = namespace.get("task")
    task_prompt = ""
    if isinstance(task, dict):
        task_prompt = str(task.get("prompt") or "").strip()

    return {
        "success": success,
        "cells": results,
        "namespace": {key: repr(value) for key, value in namespace.items() if key not in {"__builtins__"}},
        "completed_cells": completed_cells,
        "evaluation": evaluation,
        "progress": progress,
        "data_state": namespace.get("data", data_state or {}),
        "task_prompt": task_prompt,
        "error": last_error,
    }


def evaluate_notebook(namespace: dict[str, object], evaluation_rules: dict) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    passed = True

    for variable_name in evaluation_rules.get("required_variables", []):
        has_variable = variable_name in namespace
        checks.append(
            {
                "type": "required_variable",
                "name": variable_name,
                "passed": has_variable,
                "message": "Variable is available." if has_variable else f"Missing variable: {variable_name}.",
            }
        )
        passed = passed and has_variable

    for variable_name, expected_value in evaluation_rules.get("expected_values", {}).items():
        actual_value = namespace.get(variable_name)
        is_match = actual_value == expected_value
        checks.append(
            {
                "type": "expected_value",
                "name": variable_name,
                "passed": is_match,
                "message": "Value matched." if is_match else f"Expected {expected_value!r}, got {actual_value!r}.",
            }
        )
        passed = passed and is_match

    for expression in evaluation_rules.get("assertions", []):
        try:
            is_match = bool(eval(expression, namespace, namespace))
            error = None
        except Exception as exc:
            is_match = False
            error = str(exc)
        checks.append(
            {
                "type": "assertion",
                "expression": expression,
                "passed": is_match,
                "message": "Assertion passed." if is_match else error or "Assertion failed.",
            }
        )
        passed = passed and is_match

    summary = evaluation_rules.get("success_message", "Exercise checks complete.") if passed else evaluation_rules.get(
        "failure_message", "Review the notebook and try again."
    )
    return {"passed": passed, "summary": summary, "checks": checks}


def run_notebook(
    cells: list[dict[str, str]],
    allowed_imports: list[str],
    data_state: dict | None = None,
    previous_results: list[dict[str, object]] | None = None,
    evaluation_rules: dict | None = None,
) -> dict[str, object]:
    payload = {
        "cells": cells,
        "allowed_imports": allowed_imports,
        "data_state": data_state or {},
        "previous_results": previous_results or [],
        "evaluation_rules": evaluation_rules or {},
    }

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = project_root if not pythonpath else f"{project_root}{os.pathsep}{pythonpath}"

    command = [
        sys.executable,
        "-c",
        (
            "import json, sys; "
            "payload = json.loads(sys.stdin.read()); "
            "from apps.exercises.services import _run_notebook_payload; "
            "result = _run_notebook_payload(**payload); "
            "print(json.dumps(result))"
        ),
    ]

    try:
        completed = subprocess.run(
            command,
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=30,
            cwd=project_root,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "cells": [],
            "namespace": {},
            "completed_cells": 0,
            "evaluation": {"passed": False, "summary": "Notebook execution timed out.", "checks": []},
            "progress": {"summary": "Notebook execution timed out.", "passed": False, "completed_cells": 0},
            "data_state": data_state or {},
            "error": "Execution timed out in isolated worker.",
        }

    if completed.returncode != 0:
        stderr = completed.stderr.strip() or "Notebook worker exited without returning a result."
        return {
            "success": False,
            "cells": [],
            "namespace": {},
            "completed_cells": 0,
            "evaluation": {"passed": False, "summary": stderr, "checks": []},
            "progress": {"summary": stderr, "passed": False, "completed_cells": 0},
            "data_state": data_state or {},
            "error": stderr,
        }

    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {
            "success": False,
            "cells": [],
            "namespace": {},
            "completed_cells": 0,
            "evaluation": {"passed": False, "summary": "Notebook worker returned invalid JSON.", "checks": []},
            "progress": {"summary": "Notebook worker returned invalid JSON.", "passed": False, "completed_cells": 0},
            "data_state": data_state or {},
            "error": "Notebook worker returned invalid JSON.",
        }
