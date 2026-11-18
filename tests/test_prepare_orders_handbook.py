from unittest.mock import MagicMock
from insert_builder.database.tenant import (
    TblRegion, TblAdvertisementSizeDimension, TblAdvertisementSize,
    TblPublication, TblEdition, TblOrder, TblSubdistribution, TblSubdistributionOrder,
)
from insert_builder.builder import prepare_orders


def _mock_sub_order_ids(session, ids):
    """Stands in for the raw T-SQL query in prepare_orders.py, which SQLite
    can't run (ISNULL, SQL Server join syntax). Everything downstream of ID
    selection — the real target of these tests — still runs against real
    ORM objects. The raw query itself needs testing against real SQL Server,
    not here.

    Only intercepts that one specific statement — SQLAlchemy 2.0's
    session.get() and relationship lazy-loading both route through
    execute() internally, so replacing it wholesale breaks everything else
    on the session, not just this query."""
    real_execute = session.execute
    fake_result = MagicMock()
    fake_result.all.return_value = [(i,) for i in ids]

    def fake_execute(statement, *args, **kwargs):
        if statement is prepare_orders._SUBDISTRIBUTION_ORDER_SQL:
            return fake_result
        return real_execute(statement, *args, **kwargs)

    session.execute = fake_execute


def _base_fixture(session):
    session.add_all([
        TblPublication(PublicationID=1, Name="Herald Sun"),
        TblEdition(EditionID=1, PublicationID=1, Name="Tuesday Edition"),
        TblRegion(RegionID=1, Name="Nationwide"),
        TblAdvertisementSizeDimension(
            IDAdvertisemntSizeDimension=1, Height="100", Width="50", Units="mm",
            StartingPageXPos="0", StartingPageYPos="0", InsertSpacingX="5", InsertSpacingY="5",
        ),
        TblAdvertisementSizeDimension(
            IDAdvertisemntSizeDimension=2, Height="40", Width="40", Units="mm",
            StartingPageXPos="0", StartingPageYPos="0", InsertSpacingX="2", InsertSpacingY="2",
        ),
        TblAdvertisementSize(AdvertisementSizeID=1, SizeName="Quarter Page", Units="mm", AdvertisementSizeDimensionID=1),
        TblAdvertisementSize(AdvertisementSizeID=2, SizeName="Filler Size", Units="mm", AdvertisementSizeDimensionID=2),
        TblSubdistribution(iSubDistributionID=1, EditionID=1, RegionID=1, SubDistributionName="Sub 1"),
    ])
    session.commit()


def _stub_local_fs(jpg_path="found.jpg"):
    local_fs = MagicMock()
    local_fs.find_file_path.return_value = jpg_path
    return local_fs


def test_real_order_is_prepared_and_page_number_cleared(tenant_session):
    _base_fixture(tenant_session)
    tenant_session.add(TblOrder(OrderID=1, EditionID=1, AdvertisementSizeID=1, UserInvoiceNumber="00123", PageNumber="99"))
    tenant_session.add(TblSubdistributionOrder(iSubDistributionOrderID=1, SubDistributionID=1, OrderID=1, isDummy=0))
    tenant_session.commit()
    _mock_sub_order_ids(tenant_session, [1])
    subdistribution = tenant_session.get(TblSubdistribution, 1)

    orders = prepare_orders.prepare_handbook_orders(tenant_session, _stub_local_fs(), subdistribution)

    assert len(orders) == 1
    assert orders[0]["invoice_number"] == "00123"
    assert orders[0]["is_dummy"] == 0
    assert tenant_session.get(TblOrder, 1).PageNumber is None


def test_dummy_order_is_prepared_without_clearing_page_number(tenant_session):
    # Matches the Ruby original: isDummy == 1 skips clear_page_number entirely.
    _base_fixture(tenant_session)
    tenant_session.add(TblOrder(OrderID=1, EditionID=1, AdvertisementSizeID=1, UserInvoiceNumber="00456", PageNumber="7"))
    tenant_session.add(TblSubdistributionOrder(iSubDistributionOrderID=1, SubDistributionID=1, OrderID=1, isDummy=1))
    tenant_session.commit()
    _mock_sub_order_ids(tenant_session, [1])
    subdistribution = tenant_session.get(TblSubdistribution, 1)

    orders = prepare_orders.prepare_handbook_orders(tenant_session, _stub_local_fs(), subdistribution)

    assert len(orders) == 1
    assert orders[0]["is_dummy"] == 1
    assert tenant_session.get(TblOrder, 1).PageNumber == "7"


def test_filler_order_has_no_invoice_or_order_id_and_uses_sub_dimensions(tenant_session):
    _base_fixture(tenant_session)
    tenant_session.add(TblSubdistributionOrder(
        iSubDistributionOrderID=1, SubDistributionID=1, OrderID=None,
        AdvertisementSizeID=2, isDummy=2, FileData="safety-filler.jpg",
    ))
    tenant_session.commit()
    _mock_sub_order_ids(tenant_session, [1])
    subdistribution = tenant_session.get(TblSubdistribution, 1)

    orders = prepare_orders.prepare_handbook_orders(tenant_session, _stub_local_fs(), subdistribution)

    assert len(orders) == 1
    assert orders[0]["invoice_number"] is None
    assert orders[0]["order_id"] is None
    assert orders[0]["is_dummy"] == 2
    # Filler dimensions come from the sub's own AdvertisementSizeID (40x40),
    # not any real order's size.
    assert orders[0]["width"] == 40.0
    assert orders[0]["height"] == 40.0


def test_filler_order_looks_up_file_by_file_data_not_invoice_number(tenant_session):
    _base_fixture(tenant_session)
    tenant_session.add(TblSubdistributionOrder(
        iSubDistributionOrderID=1, SubDistributionID=1, OrderID=None,
        AdvertisementSizeID=2, isDummy=2, FileData="safety-filler.jpg",
    ))
    tenant_session.commit()
    _mock_sub_order_ids(tenant_session, [1])
    subdistribution = tenant_session.get(TblSubdistribution, 1)
    local_fs = _stub_local_fs()

    prepare_orders.prepare_handbook_orders(tenant_session, local_fs, subdistribution)

    local_fs.find_file_path.assert_called_once_with(
        "CarmaProduction/Print Ready/Safety Inserts", "safety-filler.jpg"
    )


def test_order_skipped_when_no_jpg_found(tenant_session):
    _base_fixture(tenant_session)
    tenant_session.add(TblOrder(OrderID=1, EditionID=1, AdvertisementSizeID=1, UserInvoiceNumber="00123"))
    tenant_session.add(TblSubdistributionOrder(iSubDistributionOrderID=1, SubDistributionID=1, OrderID=1, isDummy=0))
    tenant_session.commit()
    _mock_sub_order_ids(tenant_session, [1])
    subdistribution = tenant_session.get(TblSubdistribution, 1)

    orders = prepare_orders.prepare_handbook_orders(tenant_session, _stub_local_fs(jpg_path=None), subdistribution)

    assert orders == []


def test_invoice_number_leading_zeros_stripped_for_jpg_lookup(tenant_session):
    _base_fixture(tenant_session)
    tenant_session.add(TblOrder(OrderID=1, EditionID=1, AdvertisementSizeID=1, UserInvoiceNumber="00123"))
    tenant_session.add(TblSubdistributionOrder(iSubDistributionOrderID=1, SubDistributionID=1, OrderID=1, isDummy=0))
    tenant_session.commit()
    _mock_sub_order_ids(tenant_session, [1])
    subdistribution = tenant_session.get(TblSubdistribution, 1)
    local_fs = _stub_local_fs()

    prepare_orders.prepare_handbook_orders(tenant_session, local_fs, subdistribution)

    local_fs.find_file_path.assert_called_once_with(
        "CarmaProduction/Print Ready/Herald Sun", "123*.jpg"
    )
