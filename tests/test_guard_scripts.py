import importlib.util
import pathlib

SCRIPT_PATH = (
    pathlib.Path(__file__).parent.parent / "scripts" / "check_no_secrets.py"
)
KODI_GUARD_PATH = (
    pathlib.Path(__file__).parent.parent / "scripts" / "check_no_kodi_imports.py"
)


def _load_check_no_secrets():
    spec = importlib.util.spec_from_file_location("check_no_secrets", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_check_no_kodi_imports():
    spec = importlib.util.spec_from_file_location(
        "check_no_kodi_imports", KODI_GUARD_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PATTERNS = _load_check_no_secrets().PATTERNS

# Built at runtime, not written as literals, so these example addresses never
# appear as matchable text in this file's own source - the guard scans this
# tree too, and a literal private IP here would defeat the point of the test.
PRIVATE_IPS = [
    ".".join(parts)
    for parts in (
        ("10", "0", "0", "5"),
        ("10", "1", "2", "3"),
        ("192", "168", "1", "8"),
        ("172", "16", "0", "1"),
        ("172", "31", "5", "5"),
    )
]
PUBLIC_IP = ".".join(("8", "8", "8", "8"))


def test_private_ip_detects_full_ranges():
    pattern = PATTERNS["private-ip"]
    for address in PRIVATE_IPS:
        assert pattern.search(address), f"expected {address} to be detected"


def test_private_ip_does_not_flag_public_address():
    pattern = PATTERNS["private-ip"]
    assert not pattern.search(PUBLIC_IP)


def test_api_key_ish_detects_base64url_secrets():
    pattern = PATTERNS["api-key-ish"]
    token = "A-B_C" * 13  # 65 chars, contains '-' and '_', base64url-shaped
    assert len(token) >= 60
    assert pattern.search(token)


def test_api_key_ish_no_false_positives():
    pattern = PATTERNS["api-key-ish"]
    prose = "This is just ordinary prose describing the Couchseerr addon in plain English."
    assert not pattern.search(prose)
    assert not pattern.search("fixture-key")


def test_main_detects_a_realistic_secret_in_a_scanned_file(tmp_path, monkeypatch, capsys):
    """End-to-end: exercises main()'s scanning/reporting path, not just the compiled
    patterns in isolation. SCAN is monkeypatched to an empty tmp_path so this does not
    depend on -- and cannot be defeated by -- anything already in the repo tree."""
    module = _load_check_no_secrets()
    monkeypatch.setattr(module, "SCAN", [str(tmp_path)])

    # Realistic key shape: mixed case, digits, and base64url punctuation throughout --
    # the thing the guard exists to catch, not an English identifier. Built from parts
    # at runtime, not written as one literal, so it never appears as matchable text in
    # this file's own source -- the guard scans this tree too (see PRIVATE_IPS above for
    # the same technique).
    secret = "sk_live_" + "4Kj9pQ2xL7mN5rT8vW1yB3d" + "F6hJ0aC4eG7iK9oS2uX5zA8bC1dE3fG5h"
    assert len(secret) >= 60
    planted = tmp_path / "settings.py"
    planted.write_text('API_KEY = "{0}"\n'.format(secret))

    exit_code = module.main()
    captured = capsys.readouterr()
    assert exit_code == 1
    assert secret in captured.out
    assert "api-key-ish" in captured.out

    planted.write_text("API_KEY = None\n")

    exit_code = module.main()
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "no secrets found" in captured.out


def test_kodi_guard_catches_new_pure_module_kodi_import(tmp_path):
    """The guard must scan every .py file it finds, not a fixed list of filenames --
    a brand new module is covered the moment it exists, with no list to update."""
    module = _load_check_no_kodi_imports()
    (tmp_path / "brand_new.py").write_text("import xbmc\n")
    # Adapter-layer paths stay exempt even though they are new to this tree too.
    (tmp_path / "routes.py").write_text("import xbmc\n")
    (tmp_path / "kodi").mkdir()
    (tmp_path / "kodi" / "adapter.py").write_text("import xbmcgui\n")

    failures = module.find_violations(tmp_path)
    assert any("brand_new.py" in line for line in failures)
    assert not any("routes.py" in line for line in failures)
    assert not any(line.startswith("kodi") for line in failures)


def test_kodi_guard_catches_a_bare_relative_kodi_import(tmp_path):
    """`from . import xbmc` has node.module is None; the banned name lives in
    node.names, not node.module, so it must be checked too."""
    module = _load_check_no_kodi_imports()
    (tmp_path / "sneaky.py").write_text("from . import xbmc\n")

    failures = module.find_violations(tmp_path)
    assert any("sneaky.py" in line for line in failures)


def test_kodi_guard_catches_a_pure_import_of_an_adapter(tmp_path):
    """routes.py imports xbmc, so importing routes from pure core is exactly as fatal as
    importing xbmc directly -- and it used to sail straight past this guard."""
    module = _load_check_no_kodi_imports()
    # Named like the real package, so the absolute spelling below is the same import the
    # relative ones are -- the guard has to see through both.
    root = tmp_path / "couchseerr"
    root.mkdir()
    (root / "sideways.py").write_text("from .routes import dispatch\n")
    (root / "bare.py").write_text("from . import routes\n")
    (root / "deep.py").write_text("from .kodi.adapter import render\n")
    (root / "absolute.py").write_text("from couchseerr.routes import dispatch\n")
    (root / "routes.py").write_text("import xbmc\n")

    failures = module.find_violations(root)
    for name in ("sideways.py", "bare.py", "deep.py", "absolute.py"):
        assert any(name in line for line in failures), name
    # The adapter itself stays exempt: it is allowed to be Kodi-facing.
    assert not any(line.startswith("routes.py") for line in failures)


def test_kodi_guard_allows_ordinary_pure_imports(tmp_path):
    """The adapter rule must not fire on every core module that imports a sibling."""
    module = _load_check_no_kodi_imports()
    (tmp_path / "pure.py").write_text(
        "from .detail import available_actions\nfrom .ui.spec import ListItemSpec\n"
    )
    (tmp_path / "ui").mkdir()
    (tmp_path / "ui" / "spec.py").write_text("import json\n")

    assert module.find_violations(tmp_path) == []


def test_kodi_guard_passes_on_the_real_core_tree():
    module = _load_check_no_kodi_imports()
    assert module.find_violations(module.ROOT) == []


def test_kodi_guard_exempts_adapter_by_path_not_basename(tmp_path):
    """The exemption is for the two known adapter locations, not for every file that
    happens to share their name. A future ui/routes.py or ui/kodi/helper.py is pure-core
    code, and matching on the basename alone would hand it a silent free pass."""
    module = _load_check_no_kodi_imports()
    (tmp_path / "ui").mkdir()
    (tmp_path / "ui" / "routes.py").write_text("import xbmc\n")
    (tmp_path / "ui" / "kodi").mkdir()
    (tmp_path / "ui" / "kodi" / "helper.py").write_text("import xbmcgui\n")

    failures = module.find_violations(tmp_path)
    assert any("ui/routes.py" in line.replace("\\", "/") for line in failures)
    assert any("ui/kodi/helper.py" in line.replace("\\", "/") for line in failures)


def test_kodi_guard_fails_when_it_scans_nothing(tmp_path, capsys):
    """Run from the wrong directory, ROOT does not exist, the walk yields no files and
    the guard reports success. A gate that passes because it checked nothing is worse
    than no gate: CI stays green while the boundary goes unenforced."""
    module = _load_check_no_kodi_imports()
    assert module.main(root=tmp_path / "does-not-exist") != 0
    assert "scanned no files" in capsys.readouterr().out


def test_secrets_guard_fails_when_it_scans_nothing(tmp_path, monkeypatch, capsys):
    module = _load_check_no_secrets()
    monkeypatch.chdir(tmp_path)
    assert module.main() != 0
    assert "scanned no files" in capsys.readouterr().out
