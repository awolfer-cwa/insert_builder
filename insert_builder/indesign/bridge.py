import time
from pathlib import Path
from uuid import uuid4

# Vendored from carma_controller/carma_controller/indesign.py rather than
# imported as a cross-repo dependency — production-insertbuilder is a
# standalone project with its own venv, same as production-templatebuilder
# and production-adfiler. Must stay pointed at the same queue/results paths
# carma_controller's indesign_job_bridge.jsx actually watches.
BRIDGE_ROOT = Path(r"C:\carma\indesign_bridge")
BRIDGE_QUEUE = BRIDGE_ROOT / "queue"
BRIDGE_RESULTS = BRIDGE_ROOT / "results"

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


class InDesignScriptError(RuntimeError):
    pass


def run_script(script_path: Path, result_path: Path | None = None, timeout: int = 120) -> dict:
    """Queues a JSX file for carma_controller's InDesign startup bridge to run.
    Identical contract to carma_controller.indesign.run_script — see that
    module for the ExtendScript side (indesign_job_bridge.jsx)."""
    script_path = Path(script_path)
    if result_path is not None:
        result_path = Path(result_path)

    BRIDGE_QUEUE.mkdir(parents=True, exist_ok=True)
    BRIDGE_RESULTS.mkdir(parents=True, exist_ok=True)

    job_id = uuid4().hex
    job_path = BRIDGE_QUEUE / f"{job_id}.job"
    status_path = BRIDGE_RESULTS / f"{job_id}.status"

    if result_path and result_path.exists():
        result_path.unlink()

    job_path.write_text(
        "\n".join([
            f"script={script_path}",
            f"status={status_path}",
            f"result={result_path or ''}",
        ]),
        encoding="utf-8",
    )

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if status_path.exists():
            status = _read_status(status_path)
            if status.get("ok") == "1":
                if result_path and not result_path.exists():
                    raise FileNotFoundError(
                        f"InDesign ran {script_path}, but {result_path} was not created"
                    )
                return status
            raise InDesignScriptError(status.get("error", "InDesign script failed"))

        if result_path and result_path.exists():
            return {"ok": "1", "result": str(result_path)}

        time.sleep(1)

    raise TimeoutError(
        f"Timed out waiting {timeout} seconds for InDesign to run {script_path}."
    )


def _read_status(status_path: Path) -> dict:
    status = {}
    for line in status_path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            status[key] = value
    return status


def close_orphaned_documents(timeout: int = 60) -> None:
    """Feature #3 — queues cleanup.jsx to close any document InDesign still
    has open from a previous failed build, before the next run starts."""
    run_script(SCRIPTS_DIR / "cleanup.jsx", timeout=timeout)
