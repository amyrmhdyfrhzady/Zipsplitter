import os
import tempfile
import unittest

from filesplitter.process import DEFAULT_PART_SIZE
from filesplitter.splitter import split_file


class SplitterTests(unittest.TestCase):
    def test_split_uses_exact_part_size_and_reconstructs_source(self):
        part_size = 1024
        payload = bytes((index % 251 for index in range(part_size * 2 + 17)))
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = os.path.join(temp_dir, "archive.zip")
            output_dir = os.path.join(temp_dir, "parts")
            with open(archive_path, "wb") as file:
                file.write(payload)
            parts = split_file(archive_path, output_dir, part_size)
            self.assertEqual([os.path.getsize(item) for item in parts], [1024, 1024, 17])
            rebuilt_chunks = []
            for item in parts:
                with open(item, "rb") as file:
                    rebuilt_chunks.append(file.read())
            self.assertEqual(b"".join(rebuilt_chunks), payload)

    def test_project_default_is_exactly_19_mib(self):
        payload = b"x" * (DEFAULT_PART_SIZE + 23)
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = os.path.join(temp_dir, "archive.zip")
            output_dir = os.path.join(temp_dir, "parts")
            with open(archive_path, "wb") as file:
                file.write(payload)
            parts = split_file(archive_path, output_dir, DEFAULT_PART_SIZE)
            self.assertEqual([os.path.getsize(item) for item in parts], [19 * 1024 * 1024, 23])

    def test_empty_input_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = os.path.join(temp_dir, "empty.zip")
            open(archive_path, "wb").close()
            with self.assertRaises(RuntimeError):
                split_file(archive_path, os.path.join(temp_dir, "parts"), 1024)


if __name__ == "__main__":
    unittest.main()
