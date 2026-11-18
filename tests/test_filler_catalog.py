from unittest.mock import MagicMock
from insert_builder.database.tenant import TblAdvertisementSize, TblAdvertisementSizeDimension
from insert_builder.builder.filler_catalog import get_filler_catalog


def _add_size(session, size_id, dim_id, size_name, width, height):
    session.add(TblAdvertisementSizeDimension(
        IDAdvertisemntSizeDimension=dim_id, Height=str(height), Width=str(width), Units="mm",
        StartingPageXPos="0", StartingPageYPos="0", InsertSpacingX="0", InsertSpacingY="0",
    ))
    session.add(TblAdvertisementSize(
        AdvertisementSizeID=size_id, SizeName=size_name, Units="mm", AdvertisementSizeDimensionID=dim_id,
    ))
    session.commit()


def test_size_with_matching_filler_image_is_included(tenant_session):
    _add_size(tenant_session, 1, 1, "Quarter Page", width=50, height=100)
    local_fs = MagicMock()
    local_fs.find_file_path.return_value = "/remote/Safety Inserts/Quarter Page Filler.jpg"

    catalog = get_filler_catalog(tenant_session, local_fs)

    assert len(catalog) == 1
    assert catalog[0]["size_name"] == "Quarter Page"
    assert catalog[0]["document_path"] == "/remote/Safety Inserts/Quarter Page Filler.jpg"
    assert catalog[0]["is_dummy"] == 2
    assert catalog[0]["order_id"] is None
    assert catalog[0]["invoice_number"] is None


def test_size_with_no_matching_filler_image_is_excluded(tenant_session):
    _add_size(tenant_session, 1, 1, "Quarter Page", width=50, height=100)
    local_fs = MagicMock()
    local_fs.find_file_path.return_value = None

    catalog = get_filler_catalog(tenant_session, local_fs)

    assert catalog == []


def test_catalog_sorted_largest_first(tenant_session):
    _add_size(tenant_session, 1, 1, "Small", width=10, height=10)   # area 100
    _add_size(tenant_session, 2, 2, "Large", width=50, height=50)   # area 2500
    _add_size(tenant_session, 3, 3, "Medium", width=20, height=20)  # area 400
    local_fs = MagicMock()
    local_fs.find_file_path.return_value = "found.jpg"

    catalog = get_filler_catalog(tenant_session, local_fs)

    assert [c["size_name"] for c in catalog] == ["Large", "Medium", "Small"]


def test_size_name_with_slash_is_sanitised_for_filename_search(tenant_session):
    _add_size(tenant_session, 1, 1, "Half/Page", width=50, height=100)
    local_fs = MagicMock()
    local_fs.find_file_path.return_value = "found.jpg"

    get_filler_catalog(tenant_session, local_fs)

    local_fs.find_file_path.assert_called_once_with(
        "CarmaProduction/Print Ready/Safety Inserts", "*Half-Page*"
    )


def test_size_with_no_dimension_is_skipped_without_crashing(tenant_session):
    # AdvertisementSizeDimensionID pointing nowhere — ad_size.dimension
    # resolves to None, must be skipped rather than crashing on None.Width.
    tenant_session.add(TblAdvertisementSize(
        AdvertisementSizeID=1, SizeName="Orphan Size", Units="mm", AdvertisementSizeDimensionID=None,
    ))
    tenant_session.commit()
    local_fs = MagicMock()

    catalog = get_filler_catalog(tenant_session, local_fs)

    assert catalog == []
    local_fs.find_file_path.assert_not_called()
