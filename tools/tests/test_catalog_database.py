"""Regression tests for Resolve 20's empty generator-bin exports (Python 3.12+)."""
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from backports.zstd import compress
from autocatchsubs_catalog import generator_fields, inspect_project_database, filter_templates


class DatabaseCatalogTests(unittest.TestCase):
    def test_compressed_source_fields_survive_user_renaming(self):
        raw = b'\x12\x0fAdjustment Clip\x32\x0fAdjustment Clip'
        blob = b'\0\0\0\2' + len(raw).to_bytes(4, 'big') + b'\x81' + compress(raw)
        self.assertEqual(generator_fields(blob)[6], b'Adjustment Clip')

    def test_read_only_exact_ids_and_project_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'Project.db'
            connection = sqlite3.connect(path)
            connection.executescript('CREATE TABLE SM_Project (SM_Project_id TEXT);'
                'CREATE TABLE Sm2MpMedia (Sm2MpMedia_id TEXT,UniqueMediaPoolItemId TEXT,DbType TEXT,FieldsBlob BLOB);')
            connection.execute('INSERT INTO SM_Project VALUES (?)', ('project-id',))
            title = b'\x12\x0cFusion Title\x32\x05Text+'
            adjustment = b'\x12\x0fAdjustment Clip'
            compressed = b'\0\0\0\2' + len(adjustment).to_bytes(4, 'big') + b'\x81' + compress(adjustment)
            connection.executemany('INSERT INTO Sm2MpMedia VALUES (?,?,?,?)', [
                ('text-id', 'text-unique', 'Sm2MpGenerator', title),
                ('adjust-id', 'adjust-unique', 'Sm2MpGenerator', compressed)])
            connection.commit(); connection.close()
            before = hashlib.sha256(path.read_bytes()).digest()
            items = [{'label':'Mismo nombre', 'value':'Mismo nombre', 'mediaId':uid}
                     for uid in ('text-id', 'adjust-id')]
            result = inspect_project_database(path, 'project-id', items)
            self.assertEqual(result['generators'], 2)
            self.assertEqual(result['rejected'], 1)
            self.assertEqual(len(filter_templates(items, result)), 1)
            self.assertIsNone(inspect_project_database(path, 'otro-proyecto', items))
            self.assertEqual(before, hashlib.sha256(path.read_bytes()).digest())

    def test_compressed_metadata_limit(self):
        blob = b'\0\0\0\2' + (100_000_000).to_bytes(4, 'big') + b'\x81' + compress(b'\x32\x05Text+')
        self.assertEqual(generator_fields(blob), {})


if __name__ == '__main__':
    unittest.main(verbosity=2)
