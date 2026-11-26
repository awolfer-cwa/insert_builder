"""One-off setup step for a new machine — copies the vendored InDesign
bridge script into InDesign's Startup Scripts folder, where InDesign only
reads it at launch, and optionally clears stale .job files left over from
before the bridge was installed (they'll never be picked up, since nothing
was polling the queue when they were written).

Run on production-bak after `git pull`:
    python -m tools.install_indesign_bridge
    python -m tools.install_indesign_bridge --clear-stale-jobs

Then fully quit and relaunch InDesign — the idle task this script installs
is only registered when InDesign starts.
"""
import argparse
import shutil
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent / "insert_builder" / "scripts" / "indesign_job_bridge.jsx"
STARTUP_SCRIPTS_DIR = Path(
    r"C:\Users\Admin\AppData\Roaming\Adobe\InDesign\Version 22.0\en_US\Scripts\startup scripts"
)
QUEUE_DIR = Path(r"C:\carma\indesign_bridge\queue")

parser = argparse.ArgumentParser()
parser.add_argument(
    "--clear-stale-jobs", action="store_true",
    help="Delete leftover *.job files from before the bridge was installed",
)
args = parser.parse_args()

if not STARTUP_SCRIPTS_DIR.exists():
    raise SystemExit(f"Startup Scripts folder not found: {STARTUP_SCRIPTS_DIR}")

destination = STARTUP_SCRIPTS_DIR / SOURCE.name
shutil.copy(SOURCE, destination)
print(f"Installed {destination}")

if args.clear_stale_jobs and QUEUE_DIR.exists():
    stale_jobs = list(QUEUE_DIR.glob("*.job"))
    for job in stale_jobs:
        job.unlink()
    print(f"Removed {len(stale_jobs)} stale .job file(s) from {QUEUE_DIR}")

print("Now fully quit and relaunch InDesign for the idle task to register.")
