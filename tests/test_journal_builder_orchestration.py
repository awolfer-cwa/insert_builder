import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from insert_builder.database.tenant import (
    TblPublicationFormat, TblPublicationFormatSize, TblPublication, TblEdition,
    TblDistribution,
)
from insert_builder.builder import journal_builder


def _fixture(session):
    session.add_all([
        TblPublicationFormat(iID=1, StoreByAdSize=False),
        TblPublicationFormatSize(PublicationFormatSizeID=1, PublicationFormatID=1, PrintWidth=210, PrintHeight=297),
        TblPublication(PublicationID=1, Name="Herald Sun", PublicationFormatID=1),
        TblEdition(EditionID=1, PublicationID=1, Name="Tuesday Edition"),
        TblDistribution(DistributionID=1, EditionID=1, Name="Dist 1", ReadyToRun=True),
    ])
    session.commit()
    return session.get(TblDistribution, 1)


def _settings(tmp_path):
    return SimpleNamespace(storage_path=str(tmp_path / "storage"), remote_path=str(tmp_path / "remote"))


def _local_fs_stub(tmp_path):
    local_fs = MagicMock()
    local_fs.find_file.return_value = None  # no template found by default, overridden per-test
    insert_dir = tmp_path / "remote" / "inserts"
    local_fs.create_remote_insert_directory.return_value = insert_dir
    return local_fs, insert_dir


def test_build_journal_returns_false_when_no_template_found(tenant_session, tmp_path, monkeypatch):
    distribution = _fixture(tenant_session)
    local_fs, _ = _local_fs_stub(tmp_path)
    local_fs.find_file.return_value = None

    success, error = journal_builder.build_journal(
        tenant_session, _settings(tmp_path), local_fs, distribution,
        file_ads_by_region=False, file_ads_by_format=False,
    )

    assert success is False
    assert "template" in error.lower()


def test_build_journal_succeeds_with_no_orders_without_calling_bridge(tenant_session, tmp_path, monkeypatch):
    distribution = _fixture(tenant_session)
    local_fs, _ = _local_fs_stub(tmp_path)
    local_fs.find_file.return_value = "Ad_Insert.indt"  # template found
    monkeypatch.setattr(journal_builder, "prepare_journal_orders", lambda *a, **k: [])

    run_script_mock = MagicMock()
    monkeypatch.setattr(journal_builder.bridge, "run_script", run_script_mock)

    success, error = journal_builder.build_journal(
        tenant_session, _settings(tmp_path), local_fs, distribution,
        file_ads_by_region=False, file_ads_by_format=False,
    )

    assert success is True
    assert error is None
    run_script_mock.assert_not_called()


def test_build_journal_success_path_applies_page_numbers(tenant_session, tmp_path, monkeypatch):
    distribution = _fixture(tenant_session)
    local_fs, insert_dir = _local_fs_stub(tmp_path)
    local_fs.find_file.return_value = "Ad_Insert.indt"

    fake_orders = [{"order_id": 1, "invoice_number": "00123", "document_path": "x", "is_dummy": 0,
                    "width": 1.0, "height": 1.0, "starting_page_x_pos": 0.0, "starting_page_y_pos": 0.0,
                    "insert_spacing_x": 0.0, "insert_spacing_y": 0.0}]
    monkeypatch.setattr(journal_builder, "prepare_journal_orders", lambda *a, **k: fake_orders)

    def fake_run_script(script_path, result_path, timeout=180):
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps({
            "ok": True,
            "placed_orders": [{"index": 0, "page_name": "3"}],
            "final_page_count": 4,
        }))
        return {"ok": "1"}

    monkeypatch.setattr(journal_builder.bridge, "run_script", fake_run_script)

    applied = {}
    def fake_apply(session, orders, result):
        applied["result"] = result

    monkeypatch.setattr(journal_builder, "apply_page_numbers", fake_apply)

    success, error = journal_builder.build_journal(
        tenant_session, _settings(tmp_path), local_fs, distribution,
        file_ads_by_region=False, file_ads_by_format=False,
    )

    assert success is True
    assert error is None
    assert applied["result"]["placed_orders"][0]["page_name"] == "3"
    assert distribution.InDesignCreateDate is not None


def test_build_journal_failure_path_returns_error_without_applying_page_numbers(tenant_session, tmp_path, monkeypatch):
    distribution = _fixture(tenant_session)
    local_fs, _ = _local_fs_stub(tmp_path)
    local_fs.find_file.return_value = "Ad_Insert.indt"

    fake_orders = [{"order_id": 1, "invoice_number": "00123", "document_path": "x", "is_dummy": 0,
                    "width": 1.0, "height": 1.0, "starting_page_x_pos": 0.0, "starting_page_y_pos": 0.0,
                    "insert_spacing_x": 0.0, "insert_spacing_y": 0.0}]
    monkeypatch.setattr(journal_builder, "prepare_journal_orders", lambda *a, **k: fake_orders)

    def fake_run_script(script_path, result_path, timeout=180):
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps({"ok": False, "error": "No pages available"}))
        return {"ok": "1"}

    monkeypatch.setattr(journal_builder.bridge, "run_script", fake_run_script)

    apply_called = MagicMock()
    monkeypatch.setattr(journal_builder, "apply_page_numbers", apply_called)

    success, error = journal_builder.build_journal(
        tenant_session, _settings(tmp_path), local_fs, distribution,
        file_ads_by_region=False, file_ads_by_format=False,
    )

    assert success is False
    assert error == "No pages available"
    apply_called.assert_not_called()
    assert distribution.InDesignCreateDate is None


def test_build_journal_always_cleans_up_scratch_dir(tenant_session, tmp_path, monkeypatch):
    distribution = _fixture(tenant_session)
    local_fs, _ = _local_fs_stub(tmp_path)
    local_fs.find_file.return_value = "Ad_Insert.indt"
    monkeypatch.setattr(journal_builder, "prepare_journal_orders", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))

    try:
        journal_builder.build_journal(
            tenant_session, _settings(tmp_path), local_fs, distribution,
            file_ads_by_region=False, file_ads_by_format=False,
        )
    except RuntimeError:
        pass

    local_fs.delete_local_directory.assert_called_once()
