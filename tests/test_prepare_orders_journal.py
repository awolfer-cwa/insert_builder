from pathlib import Path
from unittest.mock import MagicMock
from insert_builder.database.tenant import (
    TblPublicationFormat, TblPublicationFormatSize, TblPublication, TblEdition,
    TblRegion, TblOrderRegion, TblAdvertisementSizeDimension, TblAdvertisementSize,
    TblOrder, TblPrelimOrderStatusType, TblPrelimOrderStatus, TblPrelimOrder,
    TblDistribution, TblRegionalDistribution,
)
from insert_builder.builder.prepare_orders import prepare_journal_orders


def _base_fixture(session):
    session.add_all([
        TblPublicationFormat(iID=1, StoreByAdSize=False),
        TblPublicationFormatSize(iID=1, PublicationFormatID=1, PrintWidth="210", PrintHeight="297"),
        TblPublication(PublicationID=1, Name="Herald Sun", PublicationFormatID=1),
        TblEdition(EditionID=1, PublicationID=1, Name="Tuesday Edition"),
        TblRegion(RegionID=1, Name="Nationwide"),
        TblAdvertisementSizeDimension(
            IDAdvertisemntSizeDimension=1, Height="100", Width="50", Units="mm",
            StartingPageXPos="0", StartingPageYPos="0", InsertSpacingX="5", InsertSpacingY="5",
        ),
        TblAdvertisementSize(AdvertisementSizeID=1, SizeName="Quarter Page", Units="mm", AdvertisementSizeDimensionID=1),
        TblDistribution(DistributionID=1, EditionID=1, Name="Dist 1", DistributionName="Dist1", ReadyToRun=True),
        TblRegionalDistribution(DistributionID=1, RegionID=1),
    ])
    session.commit()


def _add_order(session, order_id, invoice, approved, cancelled, in_cancellation_cycle):
    session.add_all([
        TblOrder(OrderID=order_id, EditionID=1, AdvertisementSizeID=1, UserInvoiceNumber=invoice, PageNumber="99"),
        TblOrderRegion(OrderID=order_id, RegionID=1),
        TblPrelimOrderStatusType(
            iId=order_id, Approved=approved, Cancelled=cancelled, InCancellationCycle=in_cancellation_cycle,
        ),
        TblPrelimOrderStatus(iId=order_id, StatusTypeId=order_id),
        TblPrelimOrder(OrderId=order_id, CurrentStatusId=order_id),
    ])
    session.commit()


def _stub_local_fs(found_filename="12345.final.indd"):
    local_fs = MagicMock()
    local_fs.find_file.return_value = found_filename
    return local_fs


def test_approved_uncancelled_order_is_included(tenant_session):
    _base_fixture(tenant_session)
    _add_order(tenant_session, 1, "00123", approved=True, cancelled=False, in_cancellation_cycle=False)
    distribution = tenant_session.get(TblDistribution, 1)

    orders = prepare_journal_orders(
        tenant_session, _stub_local_fs(), distribution, Path("/tmp/scratch"),
        file_ads_by_region=False, file_ads_by_format=False,
    )

    assert len(orders) == 1
    assert orders[0]["invoice_number"] == "00123"


def test_cancelled_order_not_in_cancellation_cycle_is_excluded(tenant_session):
    _base_fixture(tenant_session)
    _add_order(tenant_session, 1, "00123", approved=True, cancelled=True, in_cancellation_cycle=False)
    distribution = tenant_session.get(TblDistribution, 1)

    orders = prepare_journal_orders(
        tenant_session, _stub_local_fs(), distribution, Path("/tmp/scratch"),
        file_ads_by_region=False, file_ads_by_format=False,
    )

    assert orders == []


def test_cancelled_order_in_cancellation_cycle_is_still_included(tenant_session):
    # Matches the Ruby OR clause: InCancellationCycle = 1 includes the order
    # even though Approved/Cancelled alone would have excluded it.
    _base_fixture(tenant_session)
    _add_order(tenant_session, 1, "00123", approved=False, cancelled=True, in_cancellation_cycle=True)
    distribution = tenant_session.get(TblDistribution, 1)

    orders = prepare_journal_orders(
        tenant_session, _stub_local_fs(), distribution, Path("/tmp/scratch"),
        file_ads_by_region=False, file_ads_by_format=False,
    )

    assert len(orders) == 1


def test_unapproved_order_is_excluded(tenant_session):
    _base_fixture(tenant_session)
    _add_order(tenant_session, 1, "00123", approved=False, cancelled=False, in_cancellation_cycle=False)
    distribution = tenant_session.get(TblDistribution, 1)

    orders = prepare_journal_orders(
        tenant_session, _stub_local_fs(), distribution, Path("/tmp/scratch"),
        file_ads_by_region=False, file_ads_by_format=False,
    )

    assert orders == []


def test_order_in_different_region_is_excluded(tenant_session):
    _base_fixture(tenant_session)
    tenant_session.add(TblRegion(RegionID=2, Name="Other Region"))
    tenant_session.add(TblOrder(OrderID=1, EditionID=1, AdvertisementSizeID=1, UserInvoiceNumber="00123"))
    tenant_session.add(TblOrderRegion(OrderID=1, RegionID=2))  # distribution only covers RegionID=1
    tenant_session.add(TblPrelimOrderStatusType(iId=1, Approved=True, Cancelled=False, InCancellationCycle=False))
    tenant_session.add(TblPrelimOrderStatus(iId=1, StatusTypeId=1))
    tenant_session.add(TblPrelimOrder(OrderId=1, CurrentStatusId=1))
    tenant_session.commit()
    distribution = tenant_session.get(TblDistribution, 1)

    orders = prepare_journal_orders(
        tenant_session, _stub_local_fs(), distribution, Path("/tmp/scratch"),
        file_ads_by_region=False, file_ads_by_format=False,
    )

    assert orders == []


def test_page_number_is_cleared_when_order_is_prepared(tenant_session):
    _base_fixture(tenant_session)
    _add_order(tenant_session, 1, "00123", approved=True, cancelled=False, in_cancellation_cycle=False)
    distribution = tenant_session.get(TblDistribution, 1)

    prepare_journal_orders(
        tenant_session, _stub_local_fs(), distribution, Path("/tmp/scratch"),
        file_ads_by_region=False, file_ads_by_format=False,
    )

    order = tenant_session.get(TblOrder, 1)
    assert order.PageNumber is None


def test_order_skipped_when_no_file_found(tenant_session):
    _base_fixture(tenant_session)
    _add_order(tenant_session, 1, "00123", approved=True, cancelled=False, in_cancellation_cycle=False)
    distribution = tenant_session.get(TblDistribution, 1)

    local_fs = _stub_local_fs(found_filename=None)
    orders = prepare_journal_orders(
        tenant_session, local_fs, distribution, Path("/tmp/scratch"),
        file_ads_by_region=False, file_ads_by_format=False,
    )

    assert orders == []
    local_fs.download_file.assert_not_called()


def test_dimension_fields_are_converted_to_float(tenant_session):
    _base_fixture(tenant_session)
    _add_order(tenant_session, 1, "00123", approved=True, cancelled=False, in_cancellation_cycle=False)
    distribution = tenant_session.get(TblDistribution, 1)

    orders = prepare_journal_orders(
        tenant_session, _stub_local_fs(), distribution, Path("/tmp/scratch"),
        file_ads_by_region=False, file_ads_by_format=False,
    )

    assert orders[0]["width"] == 50.0
    assert orders[0]["height"] == 100.0
    assert isinstance(orders[0]["width"], float)
