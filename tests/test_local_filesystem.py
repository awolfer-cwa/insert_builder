from types import SimpleNamespace
from insert_builder.filesystem.local import LocalFileHandler


def _handler(tmp_path):
    remote = tmp_path / "remote"
    storage = tmp_path / "storage"
    remote.mkdir()
    storage.mkdir()
    settings = SimpleNamespace(remote_path=str(remote), storage_path=str(storage))
    return LocalFileHandler(settings), remote, storage


def test_find_file_matches_glob_pattern(tmp_path):
    handler, remote, _ = _handler(tmp_path)
    (remote / "orders").mkdir()
    (remote / "orders" / "12345.final.indd").write_text("x")

    found = handler.find_file("orders", "12345.*.indd")
    assert found == "12345.final.indd"


def test_find_file_returns_none_when_no_match(tmp_path):
    handler, remote, _ = _handler(tmp_path)
    (remote / "orders").mkdir()

    assert handler.find_file("orders", "99999.*.indd") is None


def test_find_file_exact_is_case_insensitive_but_matches_basename(tmp_path):
    handler, remote, _ = _handler(tmp_path)
    (remote / "templates").mkdir()
    (remote / "templates" / "Ad_Insert.indt").write_text("x")

    assert handler.find_file_exact("templates", "ad_insert.indt") == str(remote / "templates" / "Ad_Insert.indt")


def test_download_file_copies_into_local_path(tmp_path):
    handler, remote, storage = _handler(tmp_path)
    (remote / "orders").mkdir()
    (remote / "orders" / "12345.indd").write_text("ad content")

    local_dest = storage / "scratch" / "12345.indd"
    handler.download_file("orders/12345.indd", local_dest)

    assert local_dest.read_text() == "ad content"


def test_upload_file_creates_destination_dirs(tmp_path):
    handler, remote, storage = _handler(tmp_path)
    local_file = storage / "finished.indd"
    local_file.write_text("finished insert")

    handler.upload_file(local_file, "CarmaProduction/Print Ready/Pub/Edition/inserts/files/finished.indd")

    uploaded = remote / "CarmaProduction/Print Ready/Pub/Edition/inserts/files/finished.indd"
    assert uploaded.read_text() == "finished insert"


def test_create_remote_insert_directory_makes_all_three_subfolders(tmp_path):
    handler, remote, _ = _handler(tmp_path)

    insert_dir = handler.create_remote_insert_directory("MyPub", "MyEdition")

    assert insert_dir == remote / "CarmaProduction/Print Ready/MyPub/MyEdition/inserts"
    assert (insert_dir / "files").is_dir()
    assert (insert_dir / "Hi-Res PDFs").is_dir()
    assert (insert_dir / "Lo-Res PDFs").is_dir()


def test_delete_local_directory_removes_tree(tmp_path):
    handler, _, storage = _handler(tmp_path)
    scratch = storage / "scratch"
    scratch.mkdir()
    (scratch / "leftover.indd").write_text("x")

    handler.delete_local_directory(scratch)

    assert not scratch.exists()
