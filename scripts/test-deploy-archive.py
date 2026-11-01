import os
from pathlib import Path
import tempfile
import unittest
from deploy_archive import build_archive
import importlib.util

spec = importlib.util.spec_from_file_location('receiver', Path(__file__).with_name('server-deploy.py'))
receiver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(receiver)


class ReleaseArchiveTest(unittest.TestCase):
    def test_equivalent_checkouts_have_identical_archives(self):
        commit = 'a' * 40
        scratch = Path(__file__).resolve().parent.parent / '.test-tmp'
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch, prefix='archive-test-') as temporary:
            base = Path(temporary)
            roots = [base / 'windows-checkout', base / 'linux-checkout']
            contents = {'index.html': b'<html>ok</html>', '.htaccess': b'Options -Indexes',
                        f'deployment-{commit}.json': ('{"commit":"' + commit + '"}').encode(),
                        'assets/app.js': b'console.log("release")', 'fonts/mesa-1.woff2': b'wOF2fixture'}
            for index, root in enumerate(roots):
                for name, data in contents.items():
                    target = root / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                    os.utime(target, (100000 + index * 10000, 100000 + index * 10000))
                    target.chmod(0o755 if index else 0o644)
            first = build_archive(roots[0])
            self.assertEqual(first, build_archive(roots[1]))
            self.assertEqual(first, build_archive(roots[0]))
            destination = base / 'accepted'
            destination.mkdir()
            receiver.unpack(first, destination, commit)
            for name, data in contents.items():
                if name != '.htaccess':
                    self.assertEqual((destination / name).read_bytes(), data)


if __name__ == '__main__':
    unittest.main()
