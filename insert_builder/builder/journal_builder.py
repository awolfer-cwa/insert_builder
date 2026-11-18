import json
import logging
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session
from insert_builder.builder.prepare_orders import prepare_journal_orders
from insert_builder.builder.update_page_number import apply_page_numbers
from insert_builder.builder.filler_catalog import get_filler_catalog
from insert_builder.indesign import bridge

logger = logging.getLogger(__name__)


def build_journal(
    session: Session, settings, local_fs, distribution,
    file_ads_by_region: bool, file_ads_by_format: bool,
) -> tuple[bool, str | None]:
    """Port of JournalBuilder#build. Fixes the live production bug in
    journal_builder.rb lines 52-61 (undefined edition_directory/subdistribution,
    undefined upload_insert_hiresPDF/loresPDF) by giving journal its own
    distribution-scoped destination directory — mirroring the pattern
    handbook_builder.rb already got right — instead of carrying the
    copy-paste error forward."""
    scratch_dir = Path(settings.storage_path) / f"Distribution {distribution.DistributionID}"
    scratch_dir.mkdir(parents=True, exist_ok=True)

    try:
        template_path = _retrieve_template(local_fs, distribution, scratch_dir)
        if template_path is None:
            return False, "No insert template found"

        orders = prepare_journal_orders(
            session, local_fs, distribution, scratch_dir, file_ads_by_region, file_ads_by_format
        )
        logger.info("There are %d orders ready to be laid out", len(orders))
        if not orders:
            return True, None

        insert_dir = local_fs.create_remote_insert_directory(distribution.publication.Name, distribution.edition.Name)
        output_indd = insert_dir / "files" / f"{distribution.Name}.indd"
        hi_pdf = insert_dir / "Hi-Res PDFs" / f"{distribution.Name}.pdf"
        lo_pdf = insert_dir / "Lo-Res PDFs" / f"{distribution.Name}.pdf"

        # New capability, no Ruby precedent — journal picks filler sizes
        # live during layout rather than from pre-allocated rows the way
        # handbook does. See filler_catalog.py.
        filler_catalog = get_filler_catalog(session, local_fs)

        format_size = distribution.publication.publication_format_size
        job = {
            "mode": "journal",
            "template_path": str(template_path),
            "output_path": str(output_indd),
            "hi_res_pdf_path": str(hi_pdf),
            "lo_res_pdf_path": str(lo_pdf),
            "tags": {
                "Edition_Name": distribution.edition.Name,
                "Distribution_Name": distribution.Name,
            },
            "page_x_size": float(format_size.PrintWidth),
            "page_y_size": float(format_size.PrintHeight),
            "valid_page_counts": [0, 4, 8],
            "filler_master_spread_name": "C-Front Page",
            "left_master_spread_name": "A-Master A",
            "right_master_spread_name": "B-Master B",
            "orders": [{"index": i, **o} for i, o in enumerate(orders)],
            "filler_catalog": filler_catalog,
        }

        # Fixed paths, not scratch_dir-relative: the bridge's app.doScript()
        # call passes no parameters into journal_layout.jsx, so the script
        # must read/write a well-known location it has hardcoded itself.
        job_path = Path(settings.storage_path) / "journal_job.json"
        result_path = Path(settings.storage_path) / "journal_result.json"
        job_path.write_text(json.dumps(job))

        bridge.run_script(bridge.SCRIPTS_DIR / "journal_layout.jsx", result_path, timeout=180)
        result = json.loads(result_path.read_text())
        if not result.get("ok"):
            return False, result.get("error", "Unknown InDesign error")

        apply_page_numbers(session, orders, result)
        distribution.InDesignCreateDate = datetime.now()
        return True, None
    finally:
        local_fs.delete_local_directory(scratch_dir)


def _retrieve_template(local_fs, distribution, scratch_dir: Path) -> Path | None:
    """Direct port of journal_builder.rb's second (live) retrieve_template —
    the first definition in that file is dead code, silently overwritten by
    Ruby's method redefinition, and not ported here."""
    template_file = f"Ad_Insert_{distribution.Name}.indt"
    publication_name = distribution.edition.publication.Name

    remote_path = f"CarmaProduction/Print Ready/{publication_name}/Templates/Alternate Insert Templates"
    found = local_fs.find_file(remote_path, template_file)
    if found is None:
        remote_path = f"CarmaProduction/Print Ready/{publication_name}/Templates"
        found = local_fs.find_file(remote_path, template_file)
        if found is None:
            template_file = "Ad_Insert.indt"
            found = local_fs.find_file(remote_path, template_file)

    if found is None:
        return None

    local_path = scratch_dir / "inserts" / "Ad_Insert.indt"
    local_fs.download_file(f"{remote_path}/{found}", local_path)
    return local_path
