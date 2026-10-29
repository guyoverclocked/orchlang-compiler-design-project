import hashlib
from pathlib import Path
import tempfile
import unittest

from experiments.run_workflow import source_checkout_identity


class ExportProvenance(unittest.TestCase):
    def test_source_export_uses_manifest_and_has_no_invented_git_commit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "publication").mkdir()
            raw = b'{"files": {}}\n'
            (root / "publication/FILE_MANIFEST.json").write_bytes(raw)
            identity = source_checkout_identity(root)
            self.assertIsNone(identity["git_commit"])
            self.assertIsNone(identity["git_dirty"])
            self.assertTrue(identity["source_export"])
            self.assertEqual(identity["export_manifest_sha256"], hashlib.sha256(raw).hexdigest())

    def test_export_nested_in_checkout_does_not_inherit_parent_commit(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=root) as folder:
            identity = source_checkout_identity(folder)
            self.assertIsNone(identity["git_commit"])
            self.assertTrue(identity["source_export"])


if __name__ == "__main__":
    unittest.main()
