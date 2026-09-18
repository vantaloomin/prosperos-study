from pathlib import Path

from server.archives.collect import collect
from server.archives.format import canonical, digest, summary
from server.archives.library_imports import restore_imports
from server.archives.library_sources import collect_drafts, restore_sources
from server.archives.lore_sources import collect_entry_drafts, restore_entry_sources
from server.archives.restore import restore
from server.archives.validate import parse_archive
from server.database import decode, encode, identifier, many, now, one
from server.errors import require
from server.operations import previous, remember


def file_view(row):
    return {**row, "summary": decode(row["summary"]), "download_url": f"/api/archives/{row['id']}/download"}


class Archives:
    def __init__(self, database):
        self.database = database
        self.directory = database.path.parent / f"{database.path.stem}-archives"

    def list(self):
        with self.database.connect() as connection:
            return [file_view(row) for row in many(connection, "SELECT * FROM archive_files ORDER BY created_at DESC")]

    def create(self, body):
        with self.database.connect() as connection:
            document = collect(connection, body)
            document['library_drafts'] = collect_drafts(self.database, document['data'])
            document['lore_drafts'] = collect_entry_drafts(self.database, document['data'])
        content = canonical(document)
        verification = {}
        parse_archive(content, verification=verification)
        return self.save(document, content, "backup", verification)

    def stage(self, content):
        verification = {}
        document = parse_archive(content, verification=verification)
        return self.save(document, canonical(document), "import", verification)

    def save(self, document, content, kind, verification=None):
        file_id = identifier()
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / f"{file_id}.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(target)
        row = {"id": file_id, "kind": kind, "filename": f"roleplay-{document['scope']}-{file_id[:8]}.json",
               "sha256": digest(content), "summary": encode({**summary(document), "writer_verification": verification}),
               "byte_count": len(content.encode("utf-8")), "created_at": now()}
        with self.database.connect(write=True) as connection:
            connection.execute("INSERT INTO archive_files VALUES (?,?,?,?,?,?,?)", tuple(row.values()))
        return file_view(row)

    def file(self, file_id) -> tuple[dict, Path]:
        with self.database.connect() as connection:
            row = one(connection, "SELECT * FROM archive_files WHERE id=?", (file_id,))
        # A successful lookup is still not a filesystem path supplied by the caller.
        require(len(row["id"]) == 32 and all(char in "0123456789abcdef" for char in row["id"]), "Invalid archive identifier.")
        path = self.directory / f"{row['id']}.json"
        require(path.is_file(), "This archive file is missing. Import another saved copy.", 404)
        return row, path

    def review(self, file_id):
        row, path = self.file(file_id)
        content = path.read_text(encoding='utf-8')
        require(digest(content) == row['sha256'], 'The saved archive changed. Import and review that file again.', 409)
        verification = {}
        parse_archive(content, verification=verification)
        value = file_view(row)
        return {**value, 'summary': {**value['summary'], 'writer_verification': verification}}

    def apply(self, file_id, body):
        row, path = self.file(file_id)
        content = path.read_text(encoding="utf-8")
        require(digest(content) == row["sha256"] == body.sha256, "The archive changed. Import and preview it again.", 409)
        document = parse_archive(content)
        payload = {"archive_id": file_id, "sha256": body.sha256}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, "archive-restore", payload)
            if cached is not None:
                return cached
            result = restore(connection, document)
            mapping = result.pop("identity_map")
            restore_sources(self.database, connection, document, mapping)
            restore_entry_sources(self.database, document, mapping)
            restore_imports(self.database, document, mapping)
            restored_at = now()
            connection.execute("INSERT INTO archive_restores VALUES (?,?,?,?)",
                               (result["receipt_id"], file_id, encode(mapping), restored_at))
            for kind in ("stories", "assets", "profiles"):
                connection.executemany("INSERT INTO archive_origins VALUES (?,?,?,?)",
                                       ((mapping[item["id"]], kind, result["receipt_id"], restored_at)
                                        for item in document["data"][kind]))
            return remember(connection, body.operation_id, "archive-restore", payload, result)
