import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import export_names


class ExportNameTests(unittest.TestCase):
    def test_first_export_and_unicode_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'Ready'
            self.assertEqual(export_names.destination(folder, 'Назва проєкту').name,
                             'v1_Назва проєкту.mp4')

    def test_existing_and_queued_versions_survive_title_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'v2_Стара назва.mp4').touch()
            (folder / 'Video Studio old.mp4').touch()
            result = export_names.destination(folder, 'Нова назва',
                [folder / 'v3_Стара назва.mp4', folder / 'elsewhere' / 'v99_Other.mp4'])
            self.assertEqual(result.name, 'v4_Нова назва.mp4')
            self.assertEqual(len(list(folder.iterdir())), 2)

    def test_unsafe_and_long_names_stay_inside_output_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for title in ['../Папка/Відео: тест?', '😀' * 100, '...']:
                result = export_names.destination(folder, title)
                self.assertEqual(result.parent, folder)
                self.assertLessEqual(len(result.name.encode('utf-8')), 255)
                self.assertNotIn('/', result.name)
                self.assertNotIn(':', result.name)
