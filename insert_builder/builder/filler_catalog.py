import logging
from insert_builder.database.tenant import TblAdvertisementSize
from insert_builder.builder.dimensions import dimension_fields

logger = logging.getLogger(__name__)

SAFETY_INSERTS_DIRECTORY = "CarmaProduction/Print Ready/Safety Inserts"


def get_filler_catalog(session, local_fs) -> list[dict]:
    """New capability — journal builds have no Ruby precedent for this at
    all (only handbook, via pre-allocated tblSubDistributionOrder rows with
    isDummy=2). Per direction: journal picks a filler's size live during
    layout based on whatever fits the remaining space, matched to a Safety
    Insert image by ad size name. This builds that pool of
    (size, matching image) pairs once per build; journal_layout.jsx picks
    from it candidate-by-candidate while laying out.

    Every TblAdvertisementSize in the system is a candidate — there's no
    existing table restricting which sizes are valid for a given
    publication, so this doesn't filter by publication. Worth confirming
    that's actually correct once there's a real template to check against."""
    catalog = []
    for ad_size in session.query(TblAdvertisementSize).all():
        dimension = ad_size.dimension
        if dimension is None:
            continue
        filler_path = _find_filler_image(local_fs, ad_size.SizeName)
        if filler_path is None:
            logger.debug("No Safety Insert filler found for size '%s' — excluded from catalog", ad_size.SizeName)
            continue
        catalog.append({
            "size_name": ad_size.SizeName,
            "document_path": filler_path,
            "order_id": None,
            "invoice_number": None,
            "is_dummy": 2,
            **dimension_fields(dimension),
        })

    # Largest first — matches the existing convention of placing bigger real
    # ads before smaller ones (TblAdvertisementSize.Units DESC in the
    # original order-selection query).
    catalog.sort(key=lambda c: c["width"] * c["height"], reverse=True)
    logger.info("Built filler catalog with %d usable size(s)", len(catalog))
    return catalog


def _find_filler_image(local_fs, size_name: str) -> str | None:
    sanitised = size_name.replace("/", "-")
    return local_fs.find_file_path(SAFETY_INSERTS_DIRECTORY, f"*{sanitised}*")
