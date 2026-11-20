from insert_builder.database.tenant import (
    TblCarmaSystem,
    TblPrelimOrderStatusType,
    TblPrelimOrderStatus,
    TblPrelimOrder,
    TblAdvertisementSizeDimension,
    TblAdvertisementSize,
    TblRegion,
    TblOrderRegion,
    TblPublicationFormatSize,
    TblPublicationFormat,
    TblPublication,
    TblEdition,
    TblOrder,
    TblDistribution,
    TblRegionalDistribution,
    TblSubdistributionOrder,
    TblSubdistribution,
    get_outstanding_distributions,
    get_outstanding_subdistributions,
    get_system_flag,
)


def _build_fixture(session):
    fmt = TblPublicationFormat(iID=1, StoreByAdSize=False)
    fmt_size = TblPublicationFormatSize(PublicationFormatSizeID=1, PublicationFormatID=1, PrintWidth=210, PrintHeight=297)
    pub = TblPublication(PublicationID=1, Name="Herald Sun", PublicationFormatID=1)
    edition = TblEdition(EditionID=1, PublicationID=1, Name="Tuesday Edition")
    region = TblRegion(RegionID=1, Name="Nationwide")

    dimension = TblAdvertisementSizeDimension(
        IDAdvertisemntSizeDimension=1, Height="100", Width="50",
        Units="mm", StartingPageXPos="0", StartingPageYPos="0",
        InsertSpacingX="5", InsertSpacingY="5",
    )
    ad_size = TblAdvertisementSize(AdvertisementSizeID=1, SizeName="Quarter Page", Units="mm", AdvertisementSizeDimensionID=1)

    order = TblOrder(OrderID=1, EditionID=1, AdvertisementSizeID=1, UserInvoiceNumber="00123")
    order_region = TblOrderRegion(OrderID=1, RegionID=1)

    status_type = TblPrelimOrderStatusType(iId=1, Approved=True, Cancelled=False, InCancellationCycle=False)
    status = TblPrelimOrderStatus(iId=1, StatusTypeId=1)
    prelim = TblPrelimOrder(OrderId=1, CurrentStatusId=1)

    distribution = TblDistribution(DistributionID=1, EditionID=1, Name="Dist 1", ReadyToRun=True)
    regional_distribution = TblRegionalDistribution(DistributionID=1, RegionID=1)

    sub = TblSubdistribution(iSubDistributionID=1, EditionID=1, RegionID=1, SubDistributionName="Sub 1", ReadyToRun=True)
    sub_order = TblSubdistributionOrder(iSubDistributionOrderID=1, SubDistributionID=1, OrderID=1, isDummy=0)

    flag = TblCarmaSystem(vKey="FileAdsByRegion", StringValue="true")

    session.add_all([
        fmt, fmt_size, pub, edition, region, dimension, ad_size, order, order_region,
        status_type, status, prelim, distribution, regional_distribution, sub, sub_order, flag,
    ])
    session.commit()


def test_order_resolves_publication_through_edition(tenant_session):
    _build_fixture(tenant_session)
    order = tenant_session.get(TblOrder, 1)

    assert order.edition.Name == "Tuesday Edition"
    assert order.publication.Name == "Herald Sun"


def test_order_resolves_region_through_order_region(tenant_session):
    _build_fixture(tenant_session)
    order = tenant_session.get(TblOrder, 1)

    assert order.region.Name == "Nationwide"


def test_order_resolves_advertisement_size_dimension_through_ad_size(tenant_session):
    _build_fixture(tenant_session)
    order = tenant_session.get(TblOrder, 1)

    assert order.advertisement_size_dimension.Height == "100"
    assert order.advertisement_size_dimension.Width == "50"


def test_order_resolves_prelim_order_status_type(tenant_session):
    _build_fixture(tenant_session)
    order = tenant_session.get(TblOrder, 1)

    status_type = order.prelim_order_status_type
    assert status_type is not None
    assert status_type.Approved is True
    assert status_type.Cancelled is False


def test_publication_resolves_format_size_through_publication_format(tenant_session):
    _build_fixture(tenant_session)
    pub = tenant_session.get(TblPublication, 1)

    assert pub.publication_format_size.PrintWidth == 210
    assert pub.publication_format_size.PrintHeight == 297


def test_distribution_resolves_publication_through_edition(tenant_session):
    _build_fixture(tenant_session)
    distribution = tenant_session.get(TblDistribution, 1)

    assert distribution.publication.Name == "Herald Sun"


def test_subdistribution_order_resolves_order_and_dummy_flag(tenant_session):
    _build_fixture(tenant_session)
    sub_order = tenant_session.get(TblSubdistributionOrder, 1)

    assert sub_order.order.UserInvoiceNumber == "00123"
    assert sub_order.isDummy == 0


def test_get_outstanding_distributions_filters_on_ready_to_run(tenant_session):
    _build_fixture(tenant_session)

    outstanding = get_outstanding_distributions(tenant_session)
    assert len(outstanding) == 1
    assert outstanding[0].DistributionID == 1

    by_id = get_outstanding_distributions(tenant_session, manual_distribution=1)
    assert len(by_id) == 1


def test_get_outstanding_subdistributions_filters_on_ready_to_run(tenant_session):
    _build_fixture(tenant_session)

    outstanding = get_outstanding_subdistributions(tenant_session)
    assert len(outstanding) == 1
    assert outstanding[0].iSubDistributionID == 1


def test_get_system_flag_reads_string_true_as_boolean(tenant_session):
    _build_fixture(tenant_session)

    assert get_system_flag(tenant_session, "FileAdsByRegion") is True
    assert get_system_flag(tenant_session, "DoesNotExist") is False
