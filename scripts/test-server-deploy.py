import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import sys
import unittest
from unittest.mock import patch

# Keep Windows test scratch files inside this checkout's writable workspace.
if sys.platform == 'win32':
    scratch = Path(__file__).resolve().parent.parent / '.test-tmp'
    scratch.mkdir(exist_ok=True)
    tempfile.tempdir = str(scratch)

spec = importlib.util.spec_from_file_location('deploy', Path(__file__).with_name('server-deploy.py'))
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)
COMMIT = 'a' * 40


def archive(extra=None):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:gz') as tar:
        files = {name: b'example' for name in ('index.html', '.htaccess', 'fonts/mesa-1.ttf')}
        files[f'deployment-{COMMIT}.json'] = json.dumps({'commit': COMMIT}).encode()
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
        if extra:
            info, content = extra
            tar.addfile(info, io.BytesIO(content))
    return output.getvalue()


class ReceiverTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith('linux'), 'Atomic exchange requires Linux')
    def test_real_publication_retry_and_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            public, releases, backups = base / 'public_html', base / '.deploy-releases', base / '.deploy-backups'
            for folder in (public, releases, backups):
                folder.mkdir()
            (public / 'index.html').write_text('legacy page')
            (public / 'assets').mkdir()
            (public / 'assets/old-hash.js').write_text('old lazy chunk')
            with patch.multiple(deploy, BASE=base, PUBLIC=public, RELEASES=releases, BACKUPS=backups, STATE=base / '.deploy-state.json'), patch.object(deploy, 'permissions'), patch.object(deploy, 'health'):
                deploy.publish('deploy ' + COMMIT, io.BytesIO(archive()))
                self.assertTrue(public.is_symlink())
                self.assertEqual(public.resolve().name, COMMIT)
                self.assertTrue((public / 'assets/old-hash.js').is_file())
                self.assertTrue(list(backups.glob('original-public-html-*')))
                deploy.publish('deploy ' + COMMIT, io.BytesIO(archive()))
                deploy.publish('rollback', io.BytesIO())
                self.assertEqual((public / 'index.html').read_text(), 'legacy page')

    def test_complete_archive_and_fixed_server_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            deploy.unpack(archive(), destination, COMMIT)
            self.assertEqual((destination / '.htaccess').read_text(), deploy.STATIC_HTACCESS)
            self.assertTrue((destination / 'fonts/mesa-1.ttf').is_file())
            self.assertIn('RewriteRule ^ index.html [L]', (destination / '.htaccess').read_text())

    def test_unsafe_paths_and_server_scripts(self):
        for name in ('../escape', '/escape', 'assets/../../escape', 'assets/payload.php', '.env', 'assets/.htaccess', 'catalogs/items.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                info = tarfile.TarInfo(name)
                info.size = 1
                with self.assertRaises(ValueError):
                    deploy.unpack(archive((info, b'x')), Path(directory), COMMIT)

    def test_symbolic_and_hard_links_rejected(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                info = tarfile.TarInfo('assets/link.js')
                info.type = kind
                info.linkname = '/etc/passwd'
                with self.assertRaises(ValueError):
                    deploy.unpack(archive((info, b'')), Path(directory), COMMIT)

    def test_duplicates_missing_files_and_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            info = tarfile.TarInfo('index.html')
            info.size = 1
            with self.assertRaises(ValueError):
                deploy.unpack(archive((info, b'x')), Path(directory), COMMIT)
        with tempfile.TemporaryDirectory() as directory, patch.object(deploy, 'MAX_CONTENT', 1):
            with self.assertRaises(ValueError):
                deploy.unpack(archive(), Path(directory), COMMIT)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                deploy.unpack(archive(), Path(directory), 'b' * 40)

    def test_unapproved_commands_rejected(self):
        for command in ('bash', 'deploy ../access.clicpic.co', 'deploy ' + COMMIT + '; whoami', 'rollback anything'):
            with self.subTest(command=command), self.assertRaises(ValueError):
                deploy.publish(command, io.BytesIO())

    def test_failed_health_restores_previous_release(self):
        previous, current = Path('/mock/previous'), Path('/mock/current')
        with patch.object(deploy, 'STATE') as state, patch.object(deploy, 'PUBLIC') as public, patch.object(deploy, 'safe_release', side_effect=[previous, current]), patch.object(deploy, 'health', side_effect=[None, ValueError('bad response')]), patch.object(deploy, 'switch') as switch, patch.object(deploy, 'save_state') as save:
            state.read_text.return_value = json.dumps({'previous': str(previous)})
            public.resolve.return_value = current
            with self.assertRaises(RuntimeError):
                deploy.publish('rollback', io.BytesIO())
            self.assertEqual([call.args[0] for call in switch.call_args_list], [previous, current])
            save.assert_not_called()


if __name__ == '__main__':
    unittest.main()
