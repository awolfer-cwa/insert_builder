import logging
from pathlib import Path
from sqlalchemy import text, or_, and_
from sqlalchemy.orm import Session
from insert_builder.database.tenant import (
    TblOrder,
    TblOrderRegion,
    TblAdvertisementSize,
    TblPrelimOrder,
    TblPrelimOrderStatus,
    TblPrelimOrderStatusType,
    TblSubdistributionOrder,
    TblRegionalDistribution,
)
from insert_builder.builder.dimensions import dimension_fields

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------

def prepare_journal_orders(
    session: Session, local_fs, distribution, scratch_dir: Path,
    file_ads_by_region: bool, file_ads_by_format: bool,
) -> list[dict]:
    """Direct port of JournalPrepareOrdersTask — queries orders, clears each
    one's page number, downloads its .indd into the local scratch directory."""
    region_ids = [
        rd.RegionID
        for rd in session.query(TblRegionalDistribution).filter_by(DistributionID=distribution.DistributionID).all()
    ]

    orders = (
        session.query(TblOrder)
        .join(TblOrderRegion, TblOrder.OrderID == TblOrderRegion.OrderID)
        .join(TblAdvertisementSize, TblOrder.AdvertisementSizeID == TblAdvertisementSize.AdvertisementSizeID)
        .join(TblPrelimOrder, TblOrder.OrderID == TblPrelimOrder.OrderId)
        .join(TblPrelimOrderStatus, TblPrelimOrder.CurrentStatusId == TblPrelimOrderStatus.iId)
        .join(TblPrelimOrderStatusType, TblPrelimOrderStatus.StatusTypeId == TblPrelimOrderStatusType.iId)
        .filter(TblOrder.EditionID == distribution.EditionID)
        .filter(TblOrderRegion.RegionID.in_(region_ids))
        .filter(or_(
            and_(TblPrelimOrderStatusType.Approved == True, TblPrelimOrderStatusType.Cancelled == False),  # noqa: E712
            TblPrelimOrderStatusType.InCancellationCycle == True,  # noqa: E712
        ))
        .order_by(TblAdvertisementSize.Units.desc(), TblOrder.OrderID.asc())
        .all()
    )

    logger.info("There are %d orders in this distribution", len(orders))
    prepared = []
    for i, order in enumerate(orders, start=1):
        logger.info("Preparing order %d of %d: %s", i, len(orders), order.UserInvoiceNumber)
        order.PageNumber = None

        document_filename = _retrieve_order_indd(local_fs, order, scratch_dir, file_ads_by_region, file_ads_by_format)
        if document_filename is None:
            logger.warning("No InDesign document found for order %s", order.UserInvoiceNumber)
            continue

        prepared.append({
            "order_id": order.OrderID,
            "invoice_number": order.UserInvoiceNumber,
            "document_path": str(scratch_dir / document_filename),
            "is_dummy": 0,
            **dimension_fields(order.advertisement_size_dimension),
        })
    return prepared


def _order_directory(order, file_ads_by_region: bool, file_ads_by_format: bool) -> str:
    parts = ["CarmaProduction", "Print Ready", order.publication.Name, order.edition.Name]
    if file_ads_by_region:
        parts.append(order.region.Name)
    if order.publication.publication_format and order.publication.publication_format.StoreByAdSize:
        parts.append(order.ad_size.SizeName.replace("/", "-"))
    if file_ads_by_format:
        parts.append("files")
    return "/".join(parts)


def _retrieve_order_indd(
    local_fs, order, scratch_dir: Path, file_ads_by_region: bool, file_ads_by_format: bool,
) -> str | None:
    directory = _order_directory(order, file_ads_by_region, file_ads_by_format)
    pattern = f"{order.UserInvoiceNumber}.*.indd"
    document_filename = local_fs.find_file(directory, pattern)
    if document_filename is None:
        return None
    local_fs.download_file(f"{directory}/{document_filename}", scratch_dir / document_filename)
    return document_filename


# ---------------------------------------------------------------------------
# Handbook
# ---------------------------------------------------------------------------

_SUBDISTRIBUTION_ORDER_SQL = text("""
    SELECT TblSubDistributionOrder.iSubDistributionOrderID
    FROM tblSubDistributionOrder AS TblSubDistributionOrder
    LEFT OUTER JOIN tblOrder ON tblSubDistributionOrder.OrderID = tblOrder.OrderID
    LEFT OUTER JOIN tblOrderRegion ON tblOrderRegion.OrderID = tblOrder.OrderID
    LEFT OUTER JOIN tblRegion ON tblOrderRegion.RegionID = tblRegion.RegionID
    LEFT OUTER JOIN tblAdvertisementSize ON tblOrder.AdvertisementSizeID = tblAdvertisementSize.AdvertisementSizeID
    LEFT OUTER JOIN tblPrelimOrder ON tblOrder.OrderID = tblPrelimOrder.OrderId
    LEFT OUTER JOIN tblPrelimOrderStatus ON tblPrelimOrder.CurrentStatusId = tblPrelimOrderStatus.iId
    LEFT OUTER JOIN tblPrelimOrderStatusType ON tblPrelimOrderStatus.StatusTypeId = tblPrelimOrderStatusType.iId
    LEFT OUTER JOIN tblAdvertisementSize AS dummySize
        ON TblSubDistributionOrder.AdvertisementSizeID = dummySize.AdvertisementSizeID
    WHERE TblSubDistributionOrder.SubDistributionID = :sub_id
      AND (
        ((tblPrelimOrderStatusType.Approved = 1 AND tblPrelimOrderStatusType.Cancelled = 0)
         OR tblPrelimOrderStatusType.InCancellationCycle = 1)
        OR tblOrder.OrderID IS NULL
      )
    ORDER BY ISNULL(tblAdvertisementSize.Units, dummySize.Units) DESC, TblSubDistributionOrder.guid DESC
""")


def prepare_handbook_orders(session: Session, local_fs, subdistribution) -> list[dict]:
    """Direct port of HandbookPrepareOrdersTask. NOTE — preserved faithfully,
    not harmonized with the journal path: handbook places files straight from
    their Dropbox-mapped location (find_file_path's result used directly),
    it never copies them into a local scratch directory first the way the
    journal path does. Flagging this for review rather than silently
    'fixing' it into consistency."""
    sub_order_ids = [
        row[0] for row in session.execute(_SUBDISTRIBUTION_ORDER_SQL, {"sub_id": subdistribution.iSubDistributionID}).all()
    ]
    subs = [session.get(TblSubdistributionOrder, sub_id) for sub_id in sub_order_ids]

    logger.info("There are %d orders in this subdistribution", len(subs))
    prepared = []
    for i, sub in enumerate(subs, start=1):
        order = sub.order
        logger.info("Is it a dummy: %s %s", sub.isDummy, sub.iSubDistributionOrderID)

        if sub.isDummy == 1:
            logger.info("Preparing order %d of %d: %s", i, len(subs), order.UserInvoiceNumber)
            document_path = _retrieve_order_jpg(local_fs, order)
            dimension = order.advertisement_size_dimension
            invoice_number = order.UserInvoiceNumber
            order_id = order.OrderID
        elif sub.isDummy == 2:
            document_path = _retrieve_filler_jpg(local_fs, sub.FileData)
            dimension = sub.advertisement_size.dimension if sub.advertisement_size else None
            invoice_number = None
            order_id = None
        else:
            logger.info("Preparing order %d of %d: %s", i, len(subs), order.UserInvoiceNumber)
            order.PageNumber = None
            document_path = _retrieve_order_jpg(local_fs, order)
            dimension = order.advertisement_size_dimension
            invoice_number = order.UserInvoiceNumber
            order_id = order.OrderID

        if document_path is None:
            logger.warning("No InDesign document found for order")
            continue

        prepared.append({
            "order_id": order_id,
            "invoice_number": invoice_number,
            "document_path": document_path,
            "is_dummy": sub.isDummy,
            **dimension_fields(dimension),
        })
    return prepared


def _retrieve_order_jpg(local_fs, order) -> str | None:
    directory = f"CarmaProduction/Print Ready/{order.publication.Name}"
    invoice = order.UserInvoiceNumber
    prefix = invoice.lstrip("0") if invoice.startswith("0") else invoice
    return local_fs.find_file_path(directory, f"{prefix}*.jpg")


def _retrieve_filler_jpg(local_fs, file_data: str) -> str | None:
    directory = "CarmaProduction/Print Ready/Safety Inserts"
    return local_fs.find_file_path(directory, file_data)
