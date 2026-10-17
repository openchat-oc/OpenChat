import tempfile
import unittest
from pathlib import Path

from app.safe_files import is_safe_filename, write_text_safely


class SafeFilesTests(unittest.TestCase):
    def test_accepts_plain_filename(self):
        self.assertTrue(is_safe_filename("app.py"))
        self.assertTrue(is_safe_filename("notas.txt"))

    def test_rejects_paths_and_special_names(self):
        for name in ("", ".", "..", "../escape.txt", "folder/file.txt",
                     r"folder\file.txt", "/tmp/file.txt", "C:secret.txt"):
            with self.subTest(name=name):
                self.assertFalse(is_safe_filename(name))

    def test_writes_and_verifies_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_text_safely(directory, "hola.txt", "línea 1\nlínea 2")
            self.assertEqual(path.read_text(encoding="utf-8"), "línea 1\nlínea 2")

    def test_does_not_overwrite_without_permission(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hola.txt"
            path.write_text("original", encoding="utf-8")
            result = write_text_safely(directory, "hola.txt", "nuevo")
            self.assertIsNone(result)
            self.assertEqual(path.read_text(encoding="utf-8"), "original")

    def test_overwrite_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hola.txt"
            path.write_text("original", encoding="utf-8")
            result = write_text_safely(directory, "hola.txt", "nuevo", overwrite=True)
            self.assertEqual(result, path)
            self.assertEqual(path.read_text(encoding="utf-8"), "nuevo")


if __name__ == "__main__":
    unittest.main()
