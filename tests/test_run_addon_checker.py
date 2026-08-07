import importlib.util
import pathlib
import subprocess

WRAPPER_PATH = (
    pathlib.Path(__file__).parent.parent / "scripts" / "run_addon_checker.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("run_addon_checker", WRAPPER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


wrapper = _load()

# The real crash, verbatim from a failed run of this repo's own CI.
MIRROR_TRACEBACK = """INFO: Checking add-on plugin.video.couchseerr
Traceback (most recent call last):
  File "/opt/hostedtoolcache/Python/3.11.15/x64/bin/kodi-addon-checker", line 6, in <module>
    sys.exit(main())
  File "/.../kodi_addon_checker/addons/Repository.py", line 78, in __contains__
    for addon in self.addons:
AttributeError: 'Repository' object has no attribute 'addons'
"""

TRUNCATED_GZIP = """INFO: Checking add-on plugin.video.couchseerr
Traceback (most recent call last):
  File "/.../gzip.py", line 501, in read
EOFError: Compressed file ended before the end-of-stream marker was reached
"""

REAL_PROBLEMS = """INFO: Checking add-on plugin.video.couchseerr
PROBLEM: Complex entry point
ERROR: We found 1 problems and 0 warnings, please check the logfile.
"""

CLEAN = """INFO: Checking add-on plugin.video.couchseerr
INFO: We found no problems and no warnings, please enjoy your day.
"""


class _Completed:
    def __init__(self, returncode, stdout):
        self.returncode = returncode
        self.stdout = stdout


def _runner(returncode, stdout, calls=None):
    def _run(cmd, **kwargs):
        if calls is not None:
            calls.append((cmd, kwargs))
        return _Completed(returncode, stdout)

    return _run


def test_clean_run_passes():
    assert wrapper.main(["--branch=omega", "addon"], _runner(0, CLEAN)) == 0


def test_mirror_crash_is_tolerated(capsys):
    code = wrapper.main(["--branch=matrix", "addon"], _runner(1, MIRROR_TRACEBACK))
    assert code == 0
    out = capsys.readouterr().out
    # The whole checker output is still surfaced, and the skip is annotated.
    assert "AttributeError: 'Repository' object has no attribute 'addons'" in out
    assert "::warning::" in out
    assert "this addon was never checked" in out


def test_truncated_mirror_gzip_is_tolerated(capsys):
    code = wrapper.main(["--branch=matrix", "addon"], _runner(1, TRUNCATED_GZIP))
    assert code == 0
    assert "::warning::" in capsys.readouterr().out


def test_real_problems_still_fail(capsys):
    # Same exit code as the crash, so only the signature separates them. This is the
    # assertion the whole wrapper exists to keep true.
    code = wrapper.main(["--branch=omega", "addon"], _runner(1, REAL_PROBLEMS))
    assert code == 1
    assert "::warning::" not in capsys.readouterr().out


def test_unrecognised_crash_still_fails():
    other = "Traceback (most recent call last):\nSyntaxError: invalid syntax\n"
    assert wrapper.main(["--branch=omega", "addon"], _runner(1, other)) == 1


def test_signature_in_a_passing_run_is_not_treated_as_a_skip(capsys):
    # returncode 0 wins outright: nothing is annotated as skipped just because the text
    # appears somewhere in an otherwise successful run's output.
    code = wrapper.main(["--branch=omega", "addon"], _runner(0, MIRROR_TRACEBACK))
    assert code == 0
    assert "::warning::" not in capsys.readouterr().out


def test_silent_success_is_a_failure(capsys):
    code = wrapper.main(["--branch=omega", "addon"], _runner(0, "   \n"))
    assert code == 2
    assert "without producing any output" in capsys.readouterr().err


def test_missing_checker_is_not_tolerated(capsys):
    def _explode(cmd, **kwargs):
        raise OSError(2, "No such file or directory: 'kodi-addon-checker'")

    assert wrapper.main(["--branch=omega", "addon"], _explode) == 127
    assert "cannot run kodi-addon-checker" in capsys.readouterr().err


def test_no_arguments_is_a_usage_error(capsys):
    assert wrapper.main([], _runner(0, CLEAN)) == 2
    assert "usage:" in capsys.readouterr().err


def test_arguments_are_forwarded_verbatim_with_merged_streams():
    calls = []
    wrapper.main(["--branch=matrix", "plugin.video.couchseerr"], _runner(0, CLEAN, calls))
    (cmd, kwargs), = calls
    assert cmd == ["kodi-addon-checker", "--branch=matrix", "plugin.video.couchseerr"]
    # Merged, or a signature spanning both streams would never match.
    assert kwargs["stderr"] is subprocess.STDOUT
    assert kwargs["universal_newlines"] is True
