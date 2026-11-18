#!/usr/bin/env python3
"""Run the Python unit tests one file per process, several files at a time.

CI used `python3 -m unittest discover -s tests -p 'test_*.py' -v`: one process, one file after another,
about 10 minutes on a 4-CPU runner while 3 CPUs sat idle. This runs the same files, found by the same
discover call, each in its own `unittest discover -s tests -p <file>` process, with up to --jobs at once.

Nothing is skipped or retried. It fails (exit 1) when any file fails, and when the tests that ran do not
add up to the tests that discover loads, so a lost file or a file that stopped loading can't pass quietly.
Each file's -v output is printed whole when the file ends, so the logs do not interleave.

  python3 tests/run_parallel.py [--jobs N]     # N defaults to the CPU count
"""
import argparse
import os
import re
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PATTERN = "test_*.py"
RAN = re.compile(r"^Ran (\d+) tests? in ", re.M)


def discovered():
    """{module: test count} exactly as `unittest discover -s tests -p test_*.py` loads them."""
    suite = unittest.TestLoader().discover(HERE, pattern=PATTERN, top_level_dir=HERE)
    counts = {}

    def walk(s):
        for t in s:
            if isinstance(t, unittest.TestSuite):
                walk(t)
            else:
                mod = type(t).__module__
                if mod == "unittest.loader":   # a file that failed to import: run it so its error shows
                    mod = t.id().split(".")[-1]
                counts[mod] = counts.get(mod, 0) + 1

    walk(suite)
    return counts


def run(module):
    if "." in module:
        raise SystemExit(f"run_parallel: {module} is in a package; this runner only runs top-level test files")
    start = time.monotonic()
    p = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", f"{module}.py", "-v"],
                       cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    ran = RAN.findall(p.stdout)
    return module, time.monotonic() - start, p.returncode, int(ran[-1]) if ran else 0, p.stdout


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    args = ap.parse_args()
    if args.jobs < 1:
        ap.error("--jobs must be 1 or more")
    sys.path.insert(0, HERE)
    expected = discovered()
    sys.path.remove(HERE)
    # Largest files first, so a long file does not start last and set the wall time on its own.
    order = sorted(expected, key=lambda m: -os.path.getsize(os.path.join(HERE, m + ".py")))
    start = time.monotonic()
    results = []
    with ThreadPoolExecutor(args.jobs) as pool:
        for module, secs, rc, ran, out in pool.map(run, order):
            print(f"\n===== {module}.py: {'ok' if rc == 0 else 'FAILED'} in {secs:.1f}s, {ran} tests", flush=True)
            print(out, end="" if out.endswith("\n") else "\n", flush=True)
            results.append((module, secs, rc, ran))
    wall = time.monotonic() - start
    failed = [m for m, _, rc, _ in results if rc != 0]
    ran = sum(r[3] for r in results)
    want = sum(expected.values())
    print(f"\n===== {len(results)} files, {ran} tests, {wall:.0f}s wall, {sum(r[1] for r in results):.0f}s summed, "
          f"{args.jobs} at a time")
    print("Slowest files: " + ", ".join(f"{m}.py {s:.0f}s" for m, s, _, _ in sorted(results, key=lambda r: -r[1])[:8]))
    if ran != want:
        print(f"FAILED: discover loads {want} tests but {ran} ran", file=sys.stderr)
        return 1
    if failed:
        print("FAILED: " + ", ".join(f"{m}.py" for m in failed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
