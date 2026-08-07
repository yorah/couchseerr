#!/usr/bin/env python3
# scripts/check_no_kodi_imports.py
"""Fail if a pure-core module imports Kodi. The core must stay testable without a device.

"Imports Kodi" covers two spellings: naming an xbmc module directly, and importing one of
the adapter modules that name it. `from .routes import _labels` in a pure module is
exactly as fatal as `import xbmc` -- routes.py imports xbmc itself -- so a guard that
caught only the first would be weaker than the boundary it is trusted to enforce.

Every .py file under ROOT is scanned by default; only an explicit allow-list of
Kodi-facing paths is skipped. This is deliberately the inverse of a fixed "core" file
list: a new pure module is covered automatically the moment it is added, instead of
silently going unchecked until someone remembers to add it to a list.
"""
import ast
import pathlib
import sys

ROOT = pathlib.Path("plugin.video.couchseerr/resources/lib/couchseerr")
# Kodi-facing files/dirs, as paths relative to ROOT -- never as bare basenames. Matching
# on the name alone would exempt a future ui/routes.py or ui/kodi/helper.py, which are
# pure-core code, and it would do it silently.
ADAPTER_FILES = {"routes.py"}
ADAPTER_DIRS = {"kodi"}
BANNED = {"xbmc", "xbmcgui", "xbmcplugin", "xbmcaddon", "xbmcvfs"}
#: The same adapter locations as module names, since importing one from pure core drags
#: Kodi in transitively. Derived from the lists above rather than written out again: a new
#: adapter location is covered by adding it in one place.
ADAPTER_MODULES = {name[:-3] for name in ADAPTER_FILES} | set(ADAPTER_DIRS)


def _is_adapter_path(rel):
    if rel.as_posix() in ADAPTER_FILES:
        return True
    return rel.parts[0] in ADAPTER_DIRS if len(rel.parts) > 1 else False


def _imported_names(tree):
    """Yield (lineno, name) for every module named by an import statement.

    `from . import xbmc` has node.module is None (it's a bare relative import) --
    the banned name lives in node.names, not node.module, so that path must be
    checked too or it is silently invisible to this guard.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                yield node.lineno, node.module
            for alias in node.names:
                yield node.lineno, alias.name


def _module_head(name, package):
    """The first component of an imported module path, with the addon's own package name
    skipped. `from couchseerr.routes import x` and `from .routes import x` name the same
    module; only one of the two spellings is relative, and both must be caught.
    """
    parts = name.split(".")
    if len(parts) > 1 and parts[0] == package:
        parts = parts[1:]
    return parts[0]


def count_scanned(root):
    return sum(1 for path in root.rglob("*.py") if not _is_adapter_path(path.relative_to(root)))


def find_violations(root):
    failures = []
    package = root.name
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if _is_adapter_path(rel):
            continue
        tree = ast.parse(path.read_text())
        for lineno, name in _imported_names(tree):
            head = _module_head(name, package)
            if head in BANNED:
                failures.append("{0}:{1} imports {2}".format(rel, lineno, name))
            elif head in ADAPTER_MODULES:
                failures.append(
                    "{0}:{1} imports the Kodi adapter {2}".format(rel, lineno, name)
                )
    return failures


def main(root=ROOT):
    root = pathlib.Path(root)
    # ROOT is relative, so running from the wrong directory finds no files at all and
    # every check trivially passes. A gate that reports success because it scanned
    # nothing is worse than no gate: CI stays green while the boundary goes unchecked.
    if count_scanned(root) == 0:
        print("FAIL scanned no files under {0}".format(root))
        return 2

    failures = find_violations(root)
    for line in failures:
        print("FAIL {0}".format(line))
    print("no Kodi imports in core" if not failures else "{0} violation(s)".format(len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
