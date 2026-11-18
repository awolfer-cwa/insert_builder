import json
import logging
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session
from insert_builder.builder.prepare_orders import prepare_handbook_orders
from insert_builder.builder.update_page_number import apply_page_numbers
from insert_builder.indesign import bridge

logger = logging.getLogger(__name__)


def build_handbook(session: Session, settings, local_fs, subdistribution) -> tuple[bool, str | None]:
    """Port of HandbookBuilder#build. Unlike journal, this never copies files
    into a local scratch directory — the template and order jpgs are opened
    straight from their Dropbox-mapped path, matching the Ruby original
    exactly (retrieve_template returns the remote path directly; there's no
    'Cleaning up local files' step to port because nothing local was ever
    created)."""
    insert_dir = local_fs.create_remote_insert_directory(subdistribution.publication.Name, subdistribution.edition.Name)

    template_path = _retrieve_template(local_fs, subdistribution)
    if template_path is None:
        return False, "No insert template found"

    orders = prepare_handbook_orders(session, local_fs, subdistribution)
    logger.info("There are %d orders ready to be laid out", len(orders))
    if not orders:
        return True, None

    output_indd = insert_dir / "files" / f"{subdistribution.SubDistributionName}.indd"
    hi_pdf = insert_dir / "Hi-Res PDFs" / f"{subdistribution.SubDistributionName}.pdf"
    lo_pdf = insert_dir / "Lo-Res PDFs" / f"{subdistribution.SubDistributionName}.pdf"

    format_size = subdistribution.publication.publication_format_size
    job = {
        "mode": "handbook",
        "template_path": template_path,
        "output_path": str(output_indd),
        "hi_res_pdf_path": str(hi_pdf),
        "lo_res_pdf_path": str(lo_pdf),
        "tags": {
            "Region_SubDistribution": str(subdistribution.iSubDistributionID),
            "JobCode": (
                f"Job Code {subdistribution.edition.Name}"
                f" {subdistribution.region.Name if subdistribution.region else ''}"
                f" {subdistribution.SubDistributionName}"
            ),
        },
        "page_x_size": float(format_size.PrintWidth),
        "page_y_size": float(format_size.PrintHeight),
        "ad_insert_master_spread_name": "A-AD INSERT",
        "orders": [{"index": i, **o} for i, o in enumerate(orders)],
    }

    # Fixed paths, not insert_dir-relative — see the same note in
    # journal_builder.py: app.doScript() passes no parameters, so
    # handbook_layout.jsx must read/write a location it hardcodes itself.
    job_path = Path(settings.storage_path) / "handbook_job.json"
    result_path = Path(settings.storage_path) / "handbook_result.json"
    job_path.write_text(json.dumps(job))

    bridge.run_script(bridge.SCRIPTS_DIR / "handbook_layout.jsx", result_path, timeout=180)
    result = json.loads(result_path.read_text())
    if not result.get("ok"):
        return False, result.get("error", "Unknown InDesign error")

    apply_page_numbers(session, orders, result)
    subdistribution.InDesignCreateDate = datetime.now()
    return True, None


def _retrieve_template(local_fs, subdistribution) -> str | None:
    """Direct port of handbook_builder.rb's retrieve_template — returns the
    remote (Dropbox-mapped) path directly, no local copy, matching the
    original exactly."""
    if subdistribution.region is None:
        template_file = "Ad_Insert.indt"
    elif subdistribution.TemplateAdSize is None:
        template_file = f"Ad_Insert_{subdistribution.region.Name}.indt".replace(" ", "_")
    else:
        template_file = f"Ad_Insert_{subdistribution.region.Name}_{subdistribution.TemplateAdSize}.indt".replace(" ", "_")

    publication_name = subdistribution.edition.publication.Name
    remote_path = f"CarmaProduction/Print Ready/{publication_name}/Templates/Alternate Insert Templates"
    found = local_fs.find_file_exact(remote_path, template_file)
    if found is None:
        remote_path = f"CarmaProduction/Print Ready/{publication_name}/Templates"
        found = local_fs.find_file_exact(remote_path, template_file)
        if found is None:
            found = local_fs.find_file_exact(remote_path, "Ad_Insert.indt")

    return found
