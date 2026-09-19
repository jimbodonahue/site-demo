"""Harden the exercise notebook sandbox against FS/env escapes via libraries."""

from __future__ import annotations

import os
import resource
from functools import wraps
from pathlib import Path
from typing import Any


BLOCKED_IO_MESSAGE = (
	"File and network I/O are blocked in the exercise sandbox. "
	"Use the preloaded `df` / `task` data instead of reading or writing files."
)

SECRET_ENV_PREFIXES = (
	"DJANGO_",
	"DB_",
	"DATABASE_",
	"SECRET",
	"PASSWORD",
	"TOKEN",
	"API_KEY",
	"AWS_",
	"GOOGLE_",
	"GCP_",
	"EMAIL_HOST_",
	"CLOUD_",
)
SECRET_ENV_EXACT = {
	"DJANGO_SECRET_KEY",
	"SECRET_KEY",
	"DB_PWD",
	"DB_PASSWORD",
	"DB_USER",
	"DB_NAME",
	"DB_HOST",
	"DATABASE_URL",
	"EMAIL_HOST_USER",
	"EMAIL_HOST_PASSWORD",
	"ADMIN_EMAIL",
	"FEEDBACK_TO_EMAIL",
	"DEFAULT_FROM_EMAIL",
}


def _is_pathlike(value: Any) -> bool:
	if value is None:
		return False
	if isinstance(value, bool):
		return False
	if isinstance(value, (str, bytes, Path)):
		return True
	try:
		return isinstance(value, os.PathLike)
	except Exception:
		return False


def _blocked(*_args: Any, **_kwargs: Any) -> None:
	raise PermissionError(BLOCKED_IO_MESSAGE)


def _guard_path_args(func: Any, *, path_param_names: tuple[str, ...] = ("path_or_buf", "path", "buf", "filename", "fname")) -> Any:
	"""Allow in-memory use; block when a filesystem path is supplied."""
	if func is None or not callable(func):
		return _blocked

	@wraps(func)
	def wrapper(*args: Any, **kwargs: Any) -> Any:
		if args and _is_pathlike(args[0]):
			raise PermissionError(BLOCKED_IO_MESSAGE)
		for name in path_param_names:
			if name in kwargs and _is_pathlike(kwargs[name]):
				raise PermissionError(BLOCKED_IO_MESSAGE)
		return func(*args, **kwargs)

	return wrapper


def _patch_callable(owner: Any, name: str, replacement: Any | None = None) -> None:
	if owner is None or not hasattr(owner, name):
		return
	try:
		setattr(owner, name, replacement or _blocked)
	except Exception:
		pass


def harden_pandas(pd_module: Any) -> None:
	"""Disable pandas path-based I/O entry points in the student namespace."""
	if pd_module is None:
		return
	read_names = (
		"read_csv",
		"read_table",
		"read_fwf",
		"read_excel",
		"read_json",
		"read_html",
		"read_xml",
		"read_feather",
		"read_parquet",
		"read_orc",
		"read_pickle",
		"read_sas",
		"read_spss",
		"read_stata",
		"read_hdf",
		"read_sql",
		"read_sql_query",
		"read_sql_table",
		"read_gbq",
		"read_clipboard",
	)
	for name in read_names:
		_patch_callable(pd_module, name, _blocked)

	frame = getattr(pd_module, "DataFrame", None)
	series = getattr(pd_module, "Series", None)
	# Fully block writers that are almost always path/network based.
	hard_block_write = (
		"to_csv",
		"to_excel",
		"to_feather",
		"to_parquet",
		"to_orc",
		"to_pickle",
		"to_hdf",
		"to_sql",
		"to_gbq",
		"to_clipboard",
	)
	# Display helpers may return strings; only block path targets.
	guarded_write = ("to_html", "to_json", "to_xml", "to_latex", "to_markdown", "to_string")
	for target in (frame, series):
		for name in hard_block_write:
			_patch_callable(target, name, _blocked)
		for name in guarded_write:
			original = getattr(target, name, None)
			_patch_callable(target, name, _guard_path_args(original))


def harden_numpy(np_module: Any) -> None:
	if np_module is None:
		return
	for name in (
		"load",
		"save",
		"savez",
		"savez_compressed",
		"loadtxt",
		"savetxt",
		"genfromtxt",
		"fromfile",
		"tofile",
	):
		_patch_callable(np_module, name, _blocked)


def harden_matplotlib(plt_module: Any) -> None:
	if plt_module is None:
		return
	for name in ("savefig", "imsave"):
		_patch_callable(plt_module, name, _blocked)
	try:
		import matplotlib.figure as figure_mod

		_patch_callable(getattr(figure_mod, "Figure", None), "savefig", _blocked)
	except Exception:
		pass


def harden_namespace_modules(namespace: dict[str, Any]) -> None:
	"""Apply I/O patches to modules already loaded into the sandbox namespace."""
	pd_module = namespace.get("pd") or namespace.get("pandas")
	np_module = namespace.get("np") or namespace.get("numpy")
	plt_module = namespace.get("plt") or namespace.get("pyplot")
	harden_pandas(pd_module)
	harden_numpy(np_module)
	harden_matplotlib(plt_module)
	if pd_module is not None:
		namespace["pd"] = pd_module
		namespace["pandas"] = pd_module
	if np_module is not None:
		namespace["np"] = np_module
		namespace["numpy"] = np_module
	if plt_module is not None:
		namespace["plt"] = plt_module


def scrub_worker_env(env: dict[str, str] | None = None) -> dict[str, str]:
	"""Return a reduced environment for the notebook subprocess."""
	source = dict(env if env is not None else os.environ)
	kept: dict[str, str] = {}
	allow_exact = {
		"PATH",
		"HOME",
		"USER",
		"LANG",
		"LC_ALL",
		"LC_CTYPE",
		"TZ",
		"TMPDIR",
		"TMP",
		"TEMP",
		"PYTHONPATH",
		"PYTHONHOME",
		"VIRTUAL_ENV",
		"DJANGO_SETTINGS_MODULE",
		"SERVER",
		"MPLCONFIGDIR",
		"MPLBACKEND",
		"EXERCISE_SANDBOX_WORKER",
		"EXERCISE_ENABLE_RESOURCE_LIMITS",
		"EXERCISE_ENABLE_SECOND_SEED",
	}
	for key, value in source.items():
		upper = key.upper()
		if upper in SECRET_ENV_EXACT:
			continue
		if any(upper.startswith(prefix) for prefix in SECRET_ENV_PREFIXES):
			if upper not in {"DJANGO_SETTINGS_MODULE", "SERVER"}:
				continue
		if upper in allow_exact or upper.startswith("LC_"):
			kept[key] = value
	kept.setdefault("MPLBACKEND", "Agg")
	kept.setdefault("DJANGO_SETTINGS_MODULE", source.get("DJANGO_SETTINGS_MODULE", "project_core.settings"))
	return kept


def apply_resource_limits(
	*,
	cpu_seconds: int = 90,
	address_space_mb: int = 1536,
	file_size_mb: int = 128,
	open_files: int = 256,
) -> None:
	"""Best-effort rlimits for the notebook worker (no-op if unsupported)."""
	try:
		resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
	except Exception:
		pass
	try:
		bytes_limit = address_space_mb * 1024 * 1024
		resource.setrlimit(resource.RLIMIT_AS, (bytes_limit, bytes_limit))
	except Exception:
		pass
	try:
		file_bytes = file_size_mb * 1024 * 1024
		resource.setrlimit(resource.RLIMIT_FSIZE, (file_bytes, file_bytes))
	except Exception:
		pass
	try:
		resource.setrlimit(resource.RLIMIT_NOFILE, (open_files, open_files))
	except Exception:
		pass
	try:
		resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))
	except Exception:
		pass


def blocked_path_attr_guard(attr: str) -> bool:
	"""Return True when an attribute access looks like an FS/env escape hatch."""
	blocked = {
		"open",
		"__import__",
		"__builtins__",
		"__loader__",
		"__spec__",
		"system",
		"popen",
		"environ",
		"getenv",
		"putenv",
		"unsetenv",
		"remove",
		"unlink",
		"rmdir",
		"mkdir",
		"makedirs",
		"rename",
		"replace",
		"listdir",
		"scandir",
		"walk",
		"chdir",
		"fchdir",
	}
	return attr in blocked
