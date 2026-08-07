#!/usr/bin/env python3
# scripts/run_addon_checker.py
"""Run kodi-addon-checker, tolerating only its failure to reach the Kodi mirrors.

Before it looks at this addon at all, and regardless of --branch, kodi-addon-checker
downloads addons.xml.gz for all ten Kodi branches. mirrors.kodi.tv is a redirector that
hands each request to a different volunteer mirror, so every run is ten dice rolls against
ten different hosts. When one of them is slow or rate-limiting, the checker dies on its own
half-built state after a five-step retry ladder, and CI goes red for a reason that has
nothing to do with this addon.

So this wrapper exits 0 on exactly two literal signatures, both of them a mirror fetch
failing, and fails on everything else - including a checker that will not start, and a
checker that runs and reports problems. It never inspects the report itself.

The signatures are matched literally rather than by exit code because the checker uses the
same exit code for "this addon has problems" and "I crashed".
"""
import subprocess
import sys

MIRROR_FAILURES = (
    # Repository.__init__ returns from its `except requests.exceptions.RequestException`
    # before it ever assigns self.addons, so the object survives half-built and raises
    # only later, in check_addon_branches. Unreported upstream, and xbmc/addon-check has
    # had no CI run since 2025-08-24, so assume it stays unfixed.
    "'Repository' object has no attribute 'addons'",
    # A mirror served a truncated addons.xml.gz. xbmc/addon-check#218, open since 2020.
    "Compressed file ended before the end-of-stream marker was reached",
)

USAGE = "usage: run_addon_checker.py <kodi-addon-checker arguments...>"


def run(argv, runner):
    """Run the checker with argv appended, merging its stderr into its stdout.

    The traceback we match on goes to stderr while the checker's own report goes to
    stdout; captured separately they interleave unpredictably, and a signature split
    across two buffers would not match.
    """
    completed = runner(
        ["kodi-addon-checker"] + list(argv),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    return completed.returncode, completed.stdout or ""


def classify(returncode, output):
    """Return (exit code, tolerated signature or None) for a finished checker run."""
    if returncode == 0:
        # A checker that exits 0 having printed nothing did not check anything, and
        # reporting success for it is worse than no gate at all: it is indistinguishable
        # from a clean run right up until something real slips through.
        if not output.strip():
            return 2, None
        return 0, None
    for signature in MIRROR_FAILURES:
        if signature in output:
            return 0, signature
    return returncode, None


def main(argv, runner=subprocess.run):
    if not argv:
        print(USAGE, file=sys.stderr)
        return 2

    try:
        returncode, output = run(argv, runner)
    except OSError as exc:
        # Not tolerated. A missing checker means this job checked nothing, which is the
        # one outcome that must never read as a pass.
        print("FAIL cannot run kodi-addon-checker: {0}".format(exc), file=sys.stderr)
        return 127

    sys.stdout.write(output)

    code, tolerated = classify(returncode, output)
    if tolerated:
        # ::warning:: puts this in the run summary. Buried in an eight-minute log body,
        # a skipped check is a check nobody knows was skipped.
        print("::warning::kodi-addon-checker could not reach the Kodi mirrors ({0}) - "
              "this addon was never checked".format(tolerated))
    elif code == 2 and returncode == 0:
        print("FAIL kodi-addon-checker exited 0 without producing any output",
              file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
