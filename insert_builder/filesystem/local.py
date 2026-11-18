import fnmatch
import shutil
from pathlib import Path


class LocalFileHandler:
    """Mirrors local_engine.rb — 'remote' here means a path under the Dropbox
    desktop-sync folder (settings.remote_path), not a network call. Methods
    the Ruby FileHandler declares but LocalEngine never implements
    (list_folder, create_folder, move_file, close) aren't ported — nothing in
    the builder/task code ever calls them."""

    def __init__(self, settings):
        self.remote_root = Path(settings.remote_path)
        self.storage_root = Path(settings.storage_path)

    def ensure_storage_root(self) -> None:
        self.storage_root.mkdir(parents=True, exist_ok=True)

    def find_file_exact(self, directory: str, filename: str) -> str | None:
        matches = self.find_files(directory, filename)
        for match in matches:
            if Path(match).name.lower() == filename.lower():
                return match
        return None

    def find_files(self, directory: str, pattern: str) -> list[str]:
        # Case-insensitive by design, not by relying on the OS: Ruby's
        # Dir.glob on Windows matches case-insensitively because NTFS/Dropbox
        # sync folders are case-insensitive there. pathlib.Path.glob's
        # case-sensitivity instead follows the OS it runs on — matching here
        # on Linux (dev) but not on Windows (prod), or vice versa, would be
        # exactly the kind of cross-platform bug this whole migration is
        # trying to avoid. fnmatch.fnmatch already case-folds on every
        # platform, so this doesn't depend on which OS it happens to run on.
        local_directory = self.remote_root / directory
        if not local_directory.exists():
            return []
        pattern_lower = pattern.lower()
        return [
            str(p) for p in local_directory.glob("**/*")
            if p.is_file() and fnmatch.fnmatch(p.name.lower(), pattern_lower)
        ]

    def find_file(self, directory: str, pattern: str) -> str | None:
        matches = self.find_files(directory, pattern)
        return Path(matches[0]).name if matches else None

    def find_file_path(self, directory: str, pattern: str) -> str | None:
        matches = self.find_files(directory, pattern)
        # Ruby's LocalEngine lowercases this path (filePath = result[0].downcase).
        # Preserved for fidelity — harmless on Windows's case-insensitive
        # filesystem, but looks accidental rather than deliberate.
        return matches[0].lower() if matches else None

    def download_file(self, remote_file: str, local_file: Path) -> None:
        local_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(self.remote_root / remote_file, local_file)

    def upload_file(self, local_file: Path, remote_file: str) -> None:
        destination = self.remote_root / remote_file
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(local_file, destination)

    def create_remote_insert_directory(self, publication_name: str, edition_name: str) -> Path:
        """Shared by both builders — distribution and subdistribution output
        both land under .../<publication>/<edition>/inserts/, matching the
        folder shape handbook_builder.rb already used (local.py applies the
        same shape to journal builds too, fixing the bug where journal_builder.rb
        never had an equivalent of this)."""
        insert_directory = self.remote_root / "CarmaProduction" / "Print Ready" / publication_name / edition_name / "inserts"
        for subfolder in ("files", "Hi-Res PDFs", "Lo-Res PDFs"):
            (insert_directory / subfolder).mkdir(parents=True, exist_ok=True)
        return insert_directory

    def delete_local_directory(self, directory: Path) -> None:
        shutil.rmtree(directory, ignore_errors=True)
