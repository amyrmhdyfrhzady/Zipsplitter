import os
import tempfile
import unittest
import zipfile

from filesplitter.archive import make_zip
from filesplitter.splitter import split_file


class ArchivePipelineTests(unittest.TestCase):
    def test_zip_then_split_and_reassemble_produces_valid_archive(self):
        payload = b"FileSplitter integration test\n" * 5000
        with tempfile.TemporaryDirectory() as temp_dir:
            source = os.path.join(temp_dir, "sample.txt")
            archive = os.path.join(temp_dir, "sample.zip")
            parts_dir = os.path.join(temp_dir, "parts")
            with open(source, "wb") as file:
                file.write(payload)

            make_zip(source, "sample.txt", archive)
            parts = split_file(archive, parts_dir, 4096)
            rebuilt = os.path.join(temp_dir, "rebuilt.zip")
            with open(rebuilt, "wb") as output:
                for part in parts:
                    with open(part, "rb") as input_file:
                        output.write(input_file.read())

            with zipfile.ZipFile(rebuilt, "r") as result:
                self.assertIsNone(result.testzip())
                self.assertEqual(result.read("sample.txt"), payload)


if __name__ == "__main__":
    unittest.main()
