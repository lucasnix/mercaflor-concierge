"""Canonical release archive shared by validation and SSH publication."""
import gzip
import io
from pathlib import Path
import sys
import tarfile


def build_archive(root):
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError('Expected a built release directory')

    def metadata(info):
        if not (info.isfile() or info.isdir()):
            raise ValueError('Links and special release files are forbidden')
        info.uid = info.gid = 0
        info.uname = info.gname = ''
        info.mtime = 0
        info.mode = 0o755 if info.isdir() else 0o644
        info.pax_headers = {}
        return info

    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode='wb', filename='', mtime=0, compresslevel=9) as compressed:
        with tarfile.open(fileobj=compressed, mode='w|', format=tarfile.PAX_FORMAT) as archive:
            archive.add(root, arcname='.', filter=metadata)
    return output.getvalue()


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Usage: deploy_archive.py BUILD_DIRECTORY ARCHIVE_PATH')
    Path(sys.argv[2]).write_bytes(build_archive(sys.argv[1]))
