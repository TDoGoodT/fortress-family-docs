"""Fortress Codebase Indexer — builds a structured index of the codebase.

Scans fortress/src/ (and migrations/) to produce a layered Codebase_Index
persisted as JSON at fortress/data/codebase_index.json.

Supports running both inside the Docker container (cwd = fortress/)
and from the repo root (cwd = project root with fortress/ subfolder).
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path resolution — detect whether we're inside the container or at repo root
# ---------------------------------------------------------------------------

def _resolve_base_path() -> Path:
    """Return the base path to the fortress directory.

    Inside Docker the working directory is fortress/ itself, so src/ and
    data/ are direct children.  When running from the repo root (e.g. in
    tests) the fortress/ prefix is needed.
    """
    cwd = Path.cwd()
    # If src/ exists directly, we're inside the container
    if (cwd / "src").is_dir():
        return cwd
    # Otherwise try fortress/ subfolder
    if (cwd / "fortress" / "src").is_dir():
        return cwd / "fortress"
    # Fallback — assume container layout
    return cwd


def _get_paths(base: Path | None = None) -> tuple[Path, Path, Path]:
    """Return (SRC_ROOT, MIGRATIONS_DIR, INDEX_PATH) relative to *base*."""
    if base is None:
        base = _resolve_base_path()
    return (
        base / "src",
        base / "migrations",
        base / "data" / "codebase_index.json",
    )


# ---------------------------------------------------------------------------
# AST helpers — extract module-level information from a single .py file
# ---------------------------------------------------------------------------

def _extract_classes(tree: ast.Module) -> list[dict[str, Any]]:
    """Extract top-level class definitions from an AST."""
    classes: list[dict[str, Any]] = []
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(ast.unparse(base))
        methods = [
            n.name
            for n in ast.iter_child_nodes(node)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        is_dataclass = any(
            _decorator_name(d) in ("dataclass", "dataclasses.dataclass")
            for d in node.decorator_list
        )
        classes.append({
            "name": node.name,
            "bases": bases,
            "methods": methods,
            "is_dataclass": is_dataclass,
        })
    return classes


def _decorator_name(node: ast.expr) -> str:
    """Best-effort name of a decorator node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return ast.unparse(node)
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return ""


def _extract_functions(tree: ast.Module) -> list[str]:
    """Extract top-level function names from an AST."""
    return [
        node.name
        for node in ast.iter_child_nodes(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _extract_internal_imports(tree: ast.Module) -> list[str]:
    """Extract import targets that reference fortress src modules.

    Looks for patterns like:
      from src.services.foo import bar
      import src.config
    """
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            # Match "src." prefix (container-relative) or "fortress.src."
            if node.module.startswith("src.") or node.module.startswith("fortress.src."):
                # Normalise to src.* form
                mod = node.module
                if mod.startswith("fortress."):
                    mod = mod[len("fortress."):]
                if mod not in imports:
                    imports.append(mod)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("src.") or alias.name.startswith("fortress.src."):
                    mod = alias.name
                    if mod.startswith("fortress."):
                        mod = mod[len("fortress."):]
                    if mod not in imports:
                        imports.append(mod)
    return imports


# ---------------------------------------------------------------------------
# Layer scanners
# ---------------------------------------------------------------------------

def _scan_python_modules(src_root: Path) -> list[dict[str, Any]]:
    """Scan all .py files under *src_root* and return module entries.

    Each entry contains: file_path, mtime, classes, functions, imports.
    Files that fail to parse (syntax/encoding errors) are skipped with a
    warning log.
    """
    modules: list[dict[str, Any]] = []
    if not src_root.is_dir():
        logger.warning("Source root does not exist: %s", src_root)
        return modules

    for py_file in sorted(src_root.rglob("*.py")):
        rel_path = str(py_file)
        try:
            source = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Skipping %s — read error: %s", rel_path, exc)
            continue

        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError as exc:
            logger.warning("Skipping %s — syntax error: %s", rel_path, exc)
            continue

        modules.append({
            "file_path": rel_path,
            "mtime": py_file.stat().st_mtime,
            "classes": _extract_classes(tree),
            "functions": _extract_functions(tree),
            "imports": _extract_internal_imports(tree),
        })

    return modules


# --- Stub scanners for layers implemented in later tasks ---

def _extract_property_string(cls_node: ast.ClassDef, prop_name: str) -> str | None:
    """Extract the string literal returned by a @property method on *cls_node*.

    Looks for a method decorated with ``@property`` whose name matches
    *prop_name* and whose body contains a ``return <string>`` statement.
    Returns the string value or ``None`` if not found.
    """
    for node in ast.iter_child_nodes(cls_node):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != prop_name:
            continue
        # Verify it has @property decorator
        is_property = any(
            (isinstance(d, ast.Name) and d.id == "property")
            or (isinstance(d, ast.Attribute) and d.attr == "property")
            for d in node.decorator_list
        )
        if not is_property:
            continue
        # Walk the body for a Return node with a string Constant
        for child in ast.walk(node):
            if isinstance(child, ast.Return) and child.value is not None:
                if isinstance(child.value, ast.Constant) and isinstance(child.value.value, str):
                    return child.value.value
    return None


def _extract_commands_from_property(
    cls_node: ast.ClassDef,
    regex_map: dict[str, str],
) -> list[dict[str, str]]:
    """Extract command entries from the ``commands`` property of a skill class.

    Each command is a tuple of ``(re.compile(<pattern>), <action_string>)``
    inside a list literal.  We parse the AST to pull out the pattern string
    and the action string for each tuple.  Module-level compiled patterns
    (e.g. ``_DEPLOY_TRIGGER``) are resolved via *regex_map*.
    """
    commands: list[dict[str, str]] = []
    for node in ast.iter_child_nodes(cls_node):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != "commands":
            continue
        is_property = any(
            (isinstance(d, ast.Name) and d.id == "property")
            or (isinstance(d, ast.Attribute) and d.attr == "property")
            for d in node.decorator_list
        )
        if not is_property:
            continue
        # Find the return statement containing a list
        for child in ast.walk(node):
            if not isinstance(child, ast.Return) or child.value is None:
                continue
            list_node = child.value
            if not isinstance(list_node, ast.List):
                continue
            for elt in list_node.elts:
                if not isinstance(elt, ast.Tuple) or len(elt.elts) < 2:
                    continue
                pattern_str = _resolve_pattern_from_tuple_element(
                    elt.elts[0], regex_map,
                )
                action_node = elt.elts[1]
                action_str: str | None = None
                if isinstance(action_node, ast.Constant) and isinstance(action_node.value, str):
                    action_str = action_node.value
                if pattern_str is not None and action_str is not None:
                    commands.append({"pattern": pattern_str, "action": action_str})
    return commands


def _extract_regex_pattern(node: ast.expr) -> str | None:
    """Extract the regex pattern string from a ``re.compile(...)`` call node."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    is_re_compile = (
        isinstance(func, ast.Attribute)
        and func.attr == "compile"
        and isinstance(func.value, ast.Name)
        and func.value.id == "re"
    )
    if not is_re_compile:
        return None
    if not node.args:
        return None
    first_arg = node.args[0]
    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
        return first_arg.value
    return None


def _build_module_regex_map(tree: ast.Module) -> dict[str, str]:
    """Build a mapping of module-level variable names to their regex patterns.

    Finds assignments like ``_FOO = re.compile(r"^pattern$")`` and returns
    ``{"_FOO": "^pattern$"}``.
    """
    regex_map: dict[str, str] = {}
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        pattern = _extract_regex_pattern(node.value)
        if pattern is not None:
            regex_map[target.id] = pattern
    return regex_map


def _resolve_pattern_from_tuple_element(
    node: ast.expr,
    regex_map: dict[str, str],
) -> str | None:
    """Resolve a regex pattern from a tuple element in the commands list.

    Handles both inline ``re.compile(...)`` calls and references to
    module-level variables that hold compiled patterns.
    """
    # Inline re.compile(...)
    if isinstance(node, ast.Call):
        return _extract_regex_pattern(node)
    # Module-level variable reference
    if isinstance(node, ast.Name) and node.id in regex_map:
        return regex_map[node.id]
    return None


def _scan_skills(src_root: Path) -> list[dict[str, Any]]:
    """Scan the skills layer by analysing AST of skill files.

    Identifies classes that inherit from ``BaseSkill``, then extracts
    ``name``, ``description``, ``commands``, source file, and internal
    imports for each.
    """
    skills: list[dict[str, Any]] = []
    skills_dir = src_root / "skills"
    if not skills_dir.is_dir():
        return skills

    for py_file in sorted(skills_dir.rglob("*.py")):
        try:
            source = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.iter_child_nodes(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            # Check if any base is "BaseSkill"
            base_names: list[str] = []
            for base in node.bases:
                if isinstance(base, ast.Name):
                    base_names.append(base.id)
                elif isinstance(base, ast.Attribute):
                    base_names.append(ast.unparse(base))
            if "BaseSkill" not in base_names:
                continue

            regex_map = _build_module_regex_map(tree)
            name = _extract_property_string(node, "name")
            description = _extract_property_string(node, "description")
            commands = _extract_commands_from_property(node, regex_map)
            imports = _extract_internal_imports(tree)

            skills.append({
                "name": name or node.name,
                "description": description or "",
                "commands": commands,
                "source_file": str(py_file),
                "imports": imports,
            })

    return skills


def _scan_tools(src_root: Path) -> list[dict[str, Any]]:
    """Scan the tools layer by parsing ``engine/tool_registry.py``.

    Extracts ``_TOOL_MAP`` (tool_name → (skill, action)) and
    ``_TOOL_SCHEMAS`` (list of toolSpec dicts), then merges them into a
    unified list of tool entries.
    """
    registry_path = src_root / "engine" / "tool_registry.py"
    if not registry_path.is_file():
        logger.warning("tool_registry.py not found at %s", registry_path)
        return []

    try:
        source = registry_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Cannot read tool_registry.py: %s", exc)
        return []

    try:
        tree = ast.parse(source, filename=str(registry_path))
    except SyntaxError as exc:
        logger.warning("Syntax error in tool_registry.py: %s", exc)
        return []

    tool_map = _extract_tool_map(tree)
    schema_map = _extract_tool_schemas(tree)

    tools: list[dict[str, Any]] = []
    for tool_name, (skill, action) in sorted(tool_map.items()):
        entry: dict[str, Any] = {
            "tool_name": tool_name,
            "skill": skill,
            "action": action,
            "description": "",
            "input_schema_summary": {"required": [], "optional": []},
        }
        if tool_name in schema_map:
            schema_info = schema_map[tool_name]
            entry["description"] = schema_info.get("description", "")
            entry["input_schema_summary"] = schema_info.get(
                "input_schema_summary", {"required": [], "optional": []},
            )
        tools.append(entry)
    return tools


def _extract_tool_map(tree: ast.Module) -> dict[str, tuple[str, str]]:
    """Extract ``_TOOL_MAP`` dict from the AST of tool_registry.py.

    Returns a mapping of tool_name → (skill, action).
    Handles both plain ``Assign`` and annotated ``AnnAssign`` nodes.
    """
    tool_map: dict[str, tuple[str, str]] = {}
    for node in ast.iter_child_nodes(tree):
        # Resolve the target name and value from Assign or AnnAssign
        target_name: str | None = None
        value_node: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            t = node.targets[0]
            if isinstance(t, ast.Name):
                target_name = t.id
            value_node = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            t = node.target
            if isinstance(t, ast.Name):
                target_name = t.id
            value_node = node.value

        if target_name != "_TOOL_MAP" or value_node is None:
            continue
        if not isinstance(value_node, ast.Dict):
            continue
        for key, value in zip(value_node.keys, value_node.values):
            if key is None:
                continue
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                continue
            tool_name = key.value
            # Value should be a tuple of two strings
            if isinstance(value, ast.Tuple) and len(value.elts) == 2:
                e0, e1 = value.elts
                if (
                    isinstance(e0, ast.Constant) and isinstance(e0.value, str)
                    and isinstance(e1, ast.Constant) and isinstance(e1.value, str)
                ):
                    tool_map[tool_name] = (e0.value, e1.value)
    return tool_map


def _extract_tool_schemas(tree: ast.Module) -> dict[str, dict[str, Any]]:
    """Extract ``_TOOL_SCHEMAS`` list from the AST of tool_registry.py.

    Returns a mapping of tool_name → {description, input_schema_summary}.
    Handles both plain ``Assign`` and annotated ``AnnAssign`` nodes.
    """
    schema_map: dict[str, dict[str, Any]] = {}
    for node in ast.iter_child_nodes(tree):
        target_name: str | None = None
        value_node: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            t = node.targets[0]
            if isinstance(t, ast.Name):
                target_name = t.id
            value_node = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            t = node.target
            if isinstance(t, ast.Name):
                target_name = t.id
            value_node = node.value

        if target_name != "_TOOL_SCHEMAS" or value_node is None:
            continue
        if not isinstance(value_node, ast.List):
            continue
        for elt in value_node.elts:
            info = _parse_tool_spec_element(elt)
            if info is not None:
                schema_map[info["tool_name"]] = {
                    "description": info["description"],
                    "input_schema_summary": info["input_schema_summary"],
                }
    return schema_map


def _parse_tool_spec_element(node: ast.expr) -> dict[str, Any] | None:
    """Parse a single element of ``_TOOL_SCHEMAS`` (a dict with a ``toolSpec`` key).

    Returns ``{tool_name, description, input_schema_summary}`` or None.
    """
    if not isinstance(node, ast.Dict):
        return None

    # Find the "toolSpec" key
    tool_spec_node: ast.expr | None = None
    for key, value in zip(node.keys, node.values):
        if (
            key is not None
            and isinstance(key, ast.Constant)
            and key.value == "toolSpec"
        ):
            tool_spec_node = value
            break

    if tool_spec_node is None or not isinstance(tool_spec_node, ast.Dict):
        return None

    # Extract name, description, inputSchema from the toolSpec dict
    name: str | None = None
    description: str = ""
    input_schema_summary: dict[str, list[str]] = {"required": [], "optional": []}

    for key, value in zip(tool_spec_node.keys, tool_spec_node.values):
        if key is None or not isinstance(key, ast.Constant):
            continue
        if key.value == "name" and isinstance(value, ast.Constant) and isinstance(value.value, str):
            name = value.value
        elif key.value == "description":
            description = _extract_string_value(value)
        elif key.value == "inputSchema":
            input_schema_summary = _extract_input_schema_summary(value)

    if name is None:
        return None

    return {
        "tool_name": name,
        "description": description,
        "input_schema_summary": input_schema_summary,
    }


def _extract_string_value(node: ast.expr) -> str:
    """Extract a string value from an AST node, handling concatenation and JoinedStr."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    # Handle implicit string concatenation via ast.JoinedStr or BinOp
    # For parenthesised multi-line strings, Python's parser produces a single Constant.
    # But just in case, try ast.literal_eval on the unparsed form.
    try:
        return str(ast.literal_eval(node))
    except (ValueError, TypeError):
        return ""


def _extract_input_schema_summary(node: ast.expr) -> dict[str, list[str]]:
    """Extract required/optional field names from an ``inputSchema`` dict node.

    The expected structure is ``{"json": {"type": "object", "properties": {...}, "required": [...]}}``.
    """
    required: list[str] = []
    optional: list[str] = []

    # Unwrap the outer {"json": ...} dict
    json_node = _dict_get(node, "json")
    if json_node is None:
        return {"required": required, "optional": optional}

    # Get "properties" and "required" from the inner dict
    props_node = _dict_get(json_node, "properties")
    req_node = _dict_get(json_node, "required")

    # Collect required field names
    req_names: set[str] = set()
    if isinstance(req_node, ast.List):
        for elt in req_node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                req_names.add(elt.value)

    # Collect all property names and classify
    if isinstance(props_node, ast.Dict):
        for key in props_node.keys:
            if key is not None and isinstance(key, ast.Constant) and isinstance(key.value, str):
                if key.value in req_names:
                    required.append(key.value)
                else:
                    optional.append(key.value)

    return {"required": required, "optional": optional}


def _dict_get(node: ast.expr, key_name: str) -> ast.expr | None:
    """Look up a string key in an AST Dict node and return its value node."""
    if not isinstance(node, ast.Dict):
        return None
    for key, value in zip(node.keys, node.values):
        if (
            key is not None
            and isinstance(key, ast.Constant)
            and key.value == key_name
        ):
            return value
    return None


def _scan_services(src_root: Path, modules: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Scan the services layer using already-scanned module data.

    For each file in ``src/services/``, extracts filename, classes,
    public methods (not starting with ``_``), and import dependencies.
    If *modules* is provided, filters from that list; otherwise falls
    back to scanning the services directory directly.
    """
    services: list[dict[str, Any]] = []
    services_dir = src_root / "services"

    if modules is not None:
        # Use pre-scanned module data — filter for services/ files
        services_prefix = str(services_dir) + os.sep
        for mod in modules:
            fp = mod["file_path"]
            # Match files inside the services directory
            if not (fp.startswith(services_prefix) or (os.sep + "services" + os.sep) in fp):
                continue
            filename = Path(fp).name
            if filename == "__init__.py":
                continue
            classes = [c["name"] for c in mod.get("classes", [])]
            public_methods: list[str] = []
            for cls in mod.get("classes", []):
                for method in cls.get("methods", []):
                    if not method.startswith("_") and method not in public_methods:
                        public_methods.append(method)
            # Also include top-level public functions
            for func in mod.get("functions", []):
                if not func.startswith("_") and func not in public_methods:
                    public_methods.append(func)
            services.append({
                "file_path": fp,
                "classes": classes,
                "public_methods": public_methods,
                "imports": mod.get("imports", []),
            })
    else:
        # Fallback: scan services directory directly
        if not services_dir.is_dir():
            return services
        for py_file in sorted(services_dir.glob("*.py")):
            if py_file.name == "__init__.py":
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            try:
                tree = ast.parse(source, filename=str(py_file))
            except SyntaxError:
                continue
            classes_data = _extract_classes(tree)
            classes = [c["name"] for c in classes_data]
            public_methods: list[str] = []
            for cls in classes_data:
                for method in cls.get("methods", []):
                    if not method.startswith("_") and method not in public_methods:
                        public_methods.append(method)
            for func in _extract_functions(tree):
                if not func.startswith("_") and func not in public_methods:
                    public_methods.append(func)
            services.append({
                "file_path": str(py_file),
                "classes": classes,
                "public_methods": public_methods,
                "imports": _extract_internal_imports(tree),
            })
    return services


def _scan_models(src_root: Path, modules: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Scan the models layer by AST-parsing ``models/schema.py``.

    Finds classes inheriting from ``Base`` with a ``__tablename__`` attribute.
    Extracts columns (from ``mapped_column()`` calls), relationships (from
    ``relationship()`` calls), and foreign keys.

    The ``referenced_by`` field is populated by cross-referencing which
    modules import from ``src.models.schema``.
    """
    schema_path = src_root / "models" / "schema.py"
    if not schema_path.is_file():
        return []

    try:
        source = schema_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source, filename=str(schema_path))
    except SyntaxError:
        return []

    # Build referenced_by from modules data
    referencing_files: list[str] = []
    if modules:
        for mod in modules:
            for imp in mod.get("imports", []):
                if "models.schema" in imp:
                    referencing_files.append(mod["file_path"])
                    break

    models: list[dict[str, Any]] = []
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        # Check if it inherits from Base
        base_names = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                base_names.append(base.id)
            elif isinstance(base, ast.Attribute):
                base_names.append(ast.unparse(base))
        if "Base" not in base_names:
            continue

        # Extract __tablename__
        table_name = _extract_tablename(node)
        if table_name is None:
            continue

        columns = _extract_columns(node)
        relationships = _extract_relationships(node)

        models.append({
            "class_name": node.name,
            "table_name": table_name,
            "columns": columns,
            "relationships": relationships,
            "referenced_by": referencing_files,
        })

    return models


def _extract_tablename(cls_node: ast.ClassDef) -> str | None:
    """Extract the ``__tablename__`` string from a class body."""
    for node in ast.iter_child_nodes(cls_node):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__tablename__":
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        return node.value.value
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "__tablename__":
                if node.value and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    return node.value.value
    return None


def _extract_columns(cls_node: ast.ClassDef) -> list[dict[str, Any]]:
    """Extract column definitions from ``mapped_column()`` calls in a class."""
    columns: list[dict[str, Any]] = []
    for node in ast.iter_child_nodes(cls_node):
        if not isinstance(node, ast.AnnAssign):
            continue
        if not isinstance(node.target, ast.Name):
            continue
        col_name = node.target.id
        if col_name.startswith("_") or col_name == "__tablename__" or col_name == "__table_args__":
            continue
        # Check if the value is a mapped_column() call
        if node.value is None:
            continue
        if not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        is_mapped_column = (
            (isinstance(func, ast.Name) and func.id == "mapped_column")
            or (isinstance(func, ast.Attribute) and func.attr == "mapped_column")
        )
        if not is_mapped_column:
            continue

        # Extract type from first positional arg (e.g., Text, UUID, Boolean)
        col_type = _extract_column_type(node)
        # Check for primary_key and nullable in keyword args
        primary_key = False
        nullable: bool | None = None
        for kw in node.value.keywords:
            if kw.arg == "primary_key" and isinstance(kw.value, ast.Constant):
                primary_key = bool(kw.value.value)
            elif kw.arg == "nullable" and isinstance(kw.value, ast.Constant):
                nullable = bool(kw.value.value)

        col_entry: dict[str, Any] = {
            "name": col_name,
            "type": col_type,
        }
        if primary_key:
            col_entry["primary_key"] = True
        if nullable is not None:
            col_entry["nullable"] = nullable

        columns.append(col_entry)
    return columns


def _extract_column_type(ann_node: ast.AnnAssign) -> str:
    """Extract the column type string from an annotated assignment.

    Tries the first positional arg of ``mapped_column()`` first (e.g., ``Text``,
    ``UUID(as_uuid=True)``), then falls back to the annotation hint.
    """
    if ann_node.value and isinstance(ann_node.value, ast.Call) and ann_node.value.args:
        first_arg = ann_node.value.args[0]
        if isinstance(first_arg, ast.Name):
            return first_arg.id
        if isinstance(first_arg, ast.Call):
            # e.g. UUID(as_uuid=True), DateTime(timezone=True)
            if isinstance(first_arg.func, ast.Name):
                return first_arg.func.id
            if isinstance(first_arg.func, ast.Attribute):
                return first_arg.func.attr
        if isinstance(first_arg, ast.Attribute):
            return first_arg.attr
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            return first_arg.value
    # Fallback: use annotation
    annotation = ann_node.annotation
    if annotation:
        if isinstance(annotation, ast.Name):
            return annotation.id
        if isinstance(annotation, ast.Subscript):
            # e.g. Mapped[str] -> str, Mapped[Optional[str]] -> Optional[str]
            return ast.unparse(annotation.slice)
    return "Unknown"


def _extract_relationships(cls_node: ast.ClassDef) -> list[dict[str, Any]]:
    """Extract ``relationship()`` calls from a class body."""
    rels: list[dict[str, Any]] = []
    for node in ast.iter_child_nodes(cls_node):
        if not isinstance(node, ast.AnnAssign):
            continue
        if not isinstance(node.target, ast.Name):
            continue
        if node.value is None or not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        is_relationship = (
            (isinstance(func, ast.Name) and func.id == "relationship")
            or (isinstance(func, ast.Attribute) and func.attr == "relationship")
        )
        if not is_relationship:
            continue

        rel_name = node.target.id
        # Extract target model from annotation (e.g. Mapped[Optional["FamilyMember"]])
        target = _extract_relationship_target(node.annotation)
        # Extract foreign_key from keywords
        foreign_key = _extract_foreign_key_kwarg(node.value)

        rel_entry: dict[str, Any] = {"name": rel_name, "target": target}
        if foreign_key:
            rel_entry["foreign_key"] = foreign_key
        rels.append(rel_entry)
    return rels


def _extract_relationship_target(annotation: ast.expr | None) -> str:
    """Extract the target model name from a relationship annotation.

    Handles patterns like ``Mapped["Model"]``, ``Mapped[Optional["Model"]]``,
    ``Mapped[list["Model"]]``.
    """
    if annotation is None:
        return "Unknown"
    # Unparse and extract the quoted model name
    unparsed = ast.unparse(annotation)
    # Look for quoted strings inside the annotation
    match = re.search(r"['\"](\w+)['\"]", unparsed)
    if match:
        return match.group(1)
    return "Unknown"


def _extract_foreign_key_kwarg(call_node: ast.Call) -> str | None:
    """Extract the foreign_keys keyword from a relationship() call.

    Returns the column name string (e.g. ``"assigned_to"``) or None.
    """
    for kw in call_node.keywords:
        if kw.arg == "foreign_keys":
            unparsed = ast.unparse(kw.value)
            # Extract column name from patterns like "[Task.assigned_to]" or "[assigned_to]"
            match = re.search(r"\.(\w+)\]", unparsed)
            if match:
                return match.group(1)
            match = re.search(r"\[(\w+)\]", unparsed)
            if match:
                return match.group(1)
    return None


def _scan_migrations(migrations_dir: Path) -> list[dict[str, Any]]:
    """Scan the migrations layer.

    For each ``.sql`` file in *migrations_dir*, extracts the filename and
    a one-line description from the first SQL comment or the filename itself.
    """
    migrations: list[dict[str, Any]] = []
    if not migrations_dir.is_dir():
        return migrations

    for sql_file in sorted(migrations_dir.glob("*.sql")):
        description = _extract_migration_description(sql_file)
        migrations.append({
            "filename": sql_file.name,
            "description": description,
        })
    return migrations


def _extract_migration_description(sql_file: Path) -> str:
    """Extract a one-line description from a SQL migration file.

    Reads the first comment line (``-- ...``) and returns its text.
    Falls back to deriving a description from the filename.
    """
    try:
        with sql_file.open(encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith("--"):
                    # Strip the comment prefix and return
                    desc = stripped.lstrip("-").strip()
                    if desc:
                        return desc
                # If first non-empty line is not a comment, stop
                break
    except (OSError, UnicodeDecodeError):
        pass

    # Fallback: derive from filename (e.g. "001_initial_schema.sql" -> "Initial schema")
    stem = sql_file.stem  # e.g. "001_initial_schema"
    # Remove leading number prefix
    parts = stem.split("_", 1)
    if len(parts) > 1:
        return parts[1].replace("_", " ").capitalize()
    return stem


def _scan_infrastructure(src_root: Path) -> dict[str, Any]:
    """Scan the infrastructure layer.

    Extracts entrypoints, routers (from ``include_router`` calls in main.py),
    scheduler jobs (from ``add_job`` calls), external integrations, and
    config keys from ``config.py``.
    """
    infra: dict[str, Any] = {
        "entrypoints": [],
        "routers": [],
        "scheduler_jobs": [],
        "external_integrations": [],
        "config_keys": [],
    }

    # --- main.py ---
    main_path = src_root / "main.py"
    if main_path.is_file():
        infra["entrypoints"].append(str(main_path))
        try:
            source = main_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(main_path))
            infra["routers"] = _extract_routers(tree)
            infra["scheduler_jobs"] = _extract_scheduler_jobs(tree)
        except (OSError, UnicodeDecodeError, SyntaxError):
            pass

    # --- config.py ---
    config_path = src_root / "config.py"
    if config_path.is_file():
        try:
            source = config_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(config_path))
            infra["config_keys"] = _extract_config_keys(tree)
        except (OSError, UnicodeDecodeError, SyntaxError):
            pass

    # --- External integrations (known files) ---
    known_integrations = ["whatsapp_client.py", "bedrock_client.py", "deploy_skill.py"]
    for filename in known_integrations:
        # Check services/ and skills/ directories
        for subdir in ("services", "skills"):
            candidate = src_root / subdir / filename
            if candidate.is_file():
                infra["external_integrations"].append(filename)
                break

    return infra


def _extract_routers(tree: ast.Module) -> list[str]:
    """Extract router names from ``app.include_router(X.router)`` calls."""
    routers: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Match app.include_router(...)
        if not (isinstance(func, ast.Attribute) and func.attr == "include_router"):
            continue
        if not node.args:
            continue
        arg = node.args[0]
        # Pattern: module.router (e.g. health.router)
        if isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name):
            routers.append(arg.value.id)
        elif isinstance(arg, ast.Name):
            routers.append(arg.id)
    return routers


def _extract_scheduler_jobs(tree: ast.Module) -> list[dict[str, str]]:
    """Extract scheduler job entries from ``add_job(...)`` calls."""
    jobs: list[dict[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add_job"):
            continue
        # Extract job id from keywords
        job_id = ""
        trigger_str = ""
        for kw in node.keywords:
            if kw.arg == "id" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                job_id = kw.value.value
            elif kw.arg == "replace_existing":
                continue
        # Extract trigger from second positional arg
        if len(node.args) >= 2:
            trigger_str = ast.unparse(node.args[1])
        if job_id:
            jobs.append({"id": job_id, "trigger": trigger_str})
    return jobs


def _extract_config_keys(tree: ast.Module) -> list[str]:
    """Extract top-level variable names from config.py.

    Looks for module-level assignments (both plain and annotated) whose
    target is an UPPER_CASE name — the convention for config keys.
    """
    keys: list[str] = []
    for node in ast.iter_child_nodes(tree):
        target_name: str | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            t = node.targets[0]
            if isinstance(t, ast.Name):
                target_name = t.id
        elif isinstance(node, ast.AnnAssign):
            t = node.target
            if isinstance(t, ast.Name):
                target_name = t.id
        if target_name and target_name.isupper():
            keys.append(target_name)
    return keys


# ---------------------------------------------------------------------------
# Index assembly
# ---------------------------------------------------------------------------

def _build_layers(src_root: Path, migrations_dir: Path) -> dict[str, Any]:
    """Assemble all index layers into a single dict."""
    modules = _scan_python_modules(src_root)
    return {
        "modules": modules,
        "skills": _scan_skills(src_root),
        "tools": _scan_tools(src_root),
        "services": _scan_services(src_root, modules),
        "models": _scan_models(src_root, modules),
        "migrations": _scan_migrations(migrations_dir),
        "infrastructure": _scan_infrastructure(src_root),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _incremental_scan_modules(
    src_root: Path,
    existing_modules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Incrementally scan Python modules, reusing entries for unchanged files.

    Compares each ``.py`` file's current ``mtime`` against the stored
    ``mtime`` in *existing_modules*.  Files whose mtime has not changed
    are preserved as-is; new or modified files are re-scanned via AST.
    Files that no longer exist on disk are dropped.
    """
    # Build lookup: file_path → existing entry
    existing_by_path: dict[str, dict[str, Any]] = {
        m["file_path"]: m for m in existing_modules
    }

    modules: list[dict[str, Any]] = []
    if not src_root.is_dir():
        return modules

    for py_file in sorted(src_root.rglob("*.py")):
        rel_path = str(py_file)
        current_mtime = py_file.stat().st_mtime

        # Check if we have an existing entry with matching mtime
        existing = existing_by_path.get(rel_path)
        if existing is not None and existing.get("mtime") == current_mtime:
            # File unchanged — preserve existing entry
            modules.append(existing)
            continue

        # File is new or modified — re-scan
        try:
            source = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Skipping %s — read error: %s", rel_path, exc)
            continue

        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError as exc:
            logger.warning("Skipping %s — syntax error: %s", rel_path, exc)
            continue

        modules.append({
            "file_path": rel_path,
            "mtime": current_mtime,
            "classes": _extract_classes(tree),
            "functions": _extract_functions(tree),
            "imports": _extract_internal_imports(tree),
        })

    return modules


def build_index(
    *,
    force: bool = False,
    base_path: Path | None = None,
) -> dict[str, Any]:
    """Scan the codebase and build/update the Codebase_Index.

    Parameters
    ----------
    force:
        If True, rebuild from scratch even if an existing index is fresh.
    base_path:
        Override the auto-detected fortress base directory.  Useful for
        tests that operate on a temporary tree.

    Returns the complete index dict and persists it to disk.

    When *force* is False and an existing index exists on disk, performs
    an incremental update: only re-scans Python modules whose file mtime
    has changed since the last index.  Higher-level layers (skills, tools,
    services, models, migrations, infrastructure) are always re-scanned
    since they are fast.
    """
    src_root, migrations_dir, index_path = _get_paths(base_path)

    existing_index: dict[str, Any] | None = None
    if not force:
        existing_index = load_index(base_path=base_path)

    if existing_index is not None and not force:
        # Incremental update — reuse unchanged module entries
        existing_modules = existing_index.get("layers", {}).get("modules", [])
        modules = _incremental_scan_modules(src_root, existing_modules)
    else:
        # Full scan
        modules = _scan_python_modules(src_root)

    # Higher-level layers are always rebuilt (they're fast and depend on modules)
    layers: dict[str, Any] = {
        "modules": modules,
        "skills": _scan_skills(src_root),
        "tools": _scan_tools(src_root),
        "services": _scan_services(src_root, modules),
        "models": _scan_models(src_root, modules),
        "migrations": _scan_migrations(migrations_dir),
        "infrastructure": _scan_infrastructure(src_root),
    }

    index: dict[str, Any] = {
        "version": 1,
        "indexed_at": datetime.now(timezone.utc).isoformat(),
        "layers": layers,
    }

    # Persist
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Codebase index written to %s", index_path)

    return index


def load_index(*, base_path: Path | None = None) -> dict[str, Any] | None:
    """Load the persisted Codebase_Index from disk.

    Returns None if the file does not exist or cannot be read.
    """
    _, _, index_path = _get_paths(base_path)
    if not index_path.is_file():
        return None
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load index from %s: %s", index_path, exc)
        return None


def is_stale(
    max_age_hours: float = 24.0,
    *,
    base_path: Path | None = None,
) -> bool:
    """Return True if the index is missing or older than *max_age_hours*."""
    index = load_index(base_path=base_path)
    if index is None:
        return True
    indexed_at_str = index.get("indexed_at")
    if not indexed_at_str:
        return True
    try:
        indexed_at = datetime.fromisoformat(indexed_at_str)
    except (ValueError, TypeError):
        return True
    age_hours = (datetime.now(timezone.utc) - indexed_at).total_seconds() / 3600
    return age_hours > max_age_hours


def ensure_fresh(
    max_age_hours: float = 24.0,
    *,
    base_path: Path | None = None,
) -> dict[str, Any]:
    """Return a fresh index — load from disk if recent, rebuild otherwise."""
    if not is_stale(max_age_hours, base_path=base_path):
        existing = load_index(base_path=base_path)
        if existing is not None:
            return existing
    return build_index(base_path=base_path)


# ---------------------------------------------------------------------------
# Context retrieval — keyword-based search across index layers
# ---------------------------------------------------------------------------

def _tokenize_query(query: str) -> list[str]:
    """Tokenize a query string into lowercase keywords, filtering short tokens."""
    # Split on whitespace and punctuation
    tokens = re.split(r'[\s,;:?!.()\[\]{}"\']+', query.lower())
    # Filter out very short tokens and common stop words
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "do", "does",
                  "what", "which", "how", "who", "where", "when", "why",
                  "in", "on", "at", "to", "for", "of", "with", "and", "or",
                  "מה", "איזה", "איך", "של", "את", "על", "עם", "יש", "לי",
                  "זה", "הוא", "היא", "אני", "לך", "שלך", "כל", "גם"}
    return [t for t in tokens if len(t) >= 2 and t not in stop_words]


def _match_score(keywords: list[str], text: str) -> int:
    """Count how many keywords appear in the given text (case-insensitive)."""
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw in text_lower)


def retrieve_relevant_context(
    query: str,
    *,
    base_path: Path | None = None,
    max_entries: int = 15,
) -> list[dict[str, Any]]:
    """Retrieve index entries relevant to a natural-language query.

    Tokenizes the query into keywords and searches across all index layers
    (skills, services, models, tools, modules). Returns the top *max_entries*
    matching entries sorted by relevance score.
    """
    index = load_index(base_path=base_path)
    if index is None:
        return []

    layers = index.get("layers", {})
    keywords = _tokenize_query(query)
    if not keywords:
        return []

    scored: list[tuple[int, dict[str, Any]]] = []

    # Search skills
    for skill in layers.get("skills", []):
        text = f"{skill.get('name', '')} {skill.get('description', '')} {' '.join(c.get('action', '') for c in skill.get('commands', []))}"
        score = _match_score(keywords, text)
        if score > 0:
            scored.append((score, {"layer": "skill", **skill}))

    # Search services
    for svc in layers.get("services", []):
        text = f"{svc.get('file_path', '')} {' '.join(svc.get('classes', []))} {' '.join(svc.get('public_methods', []))}"
        score = _match_score(keywords, text)
        if score > 0:
            scored.append((score, {"layer": "service", **svc}))

    # Search models
    for model in layers.get("models", []):
        text = f"{model.get('class_name', '')} {model.get('table_name', '')} {' '.join(c.get('name', '') for c in model.get('columns', []))}"
        score = _match_score(keywords, text)
        if score > 0:
            scored.append((score, {"layer": "model", **model}))

    # Search tools
    for tool in layers.get("tools", []):
        text = f"{tool.get('tool_name', '')} {tool.get('description', '')} {tool.get('skill', '')} {tool.get('action', '')}"
        score = _match_score(keywords, text)
        if score > 0:
            scored.append((score, {"layer": "tool", **tool}))

    # Search modules (lower priority — only if few results from above)
    for mod in layers.get("modules", []):
        text = f"{mod.get('file_path', '')} {' '.join(c.get('name', '') for c in mod.get('classes', []))} {' '.join(mod.get('functions', []))}"
        score = _match_score(keywords, text)
        if score > 0:
            scored.append((score, {"layer": "module", **mod}))

    # Sort by score descending, take top N
    scored.sort(key=lambda x: x[0], reverse=True)
    return [entry for _, entry in scored[:max_entries]]
