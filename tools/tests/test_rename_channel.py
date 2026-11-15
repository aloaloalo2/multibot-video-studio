import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rename_channel


class IdNamedTest(unittest.TestCase):
    """A channel rename moves every piece of its data named by the old id (15 November 2026: «був голос»)."""

    def test_every_folder_and_file_named_by_the_id_is_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in ('channels/abc123/settings.json', 'language-defaults/abc123/current.json',
                        'agent-channel-memory/abc123.json', 'agent-channel-memory/abc123.lock',
                        'agent-channel-memory/other.json', 'projects/abc123/project.json', 'rename-backups/abc123/x'):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text('{}')
            with patch.object(rename_channel.store, 'DATA_ROOT', root):
                found = {str(p.relative_to(root)) for p in rename_channel.id_named('abc123')}
        self.assertEqual(found, {'channels/abc123', 'language-defaults/abc123',
                                 'agent-channel-memory/abc123.json', 'agent-channel-memory/abc123.lock'})


if __name__ == '__main__':
    unittest.main()
