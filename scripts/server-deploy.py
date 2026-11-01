#!/usr/bin/python3
"""Restricted deploy receiver for mercaflor.clicpic.co only. Installed root-owned."""
import ctypes
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

BASE = Path('/home/mercaflor.clicpic.co')
PUBLIC = BASE / 'public_html'
RELEASES = BASE / '.deploy-releases'
BACKUPS = BASE / '.deploy-backups'
STATE = BASE / '.deploy-state.json'
MAX_ARCHIVE = 64 * 1024 * 1024
MAX_CONTENT = 128 * 1024 * 1024
STATIC_HTACCESS = r'''# Static React/Vite entry for Mercaflor Concierge.
RewriteEngine On
RewriteCond %{REQUEST_FILENAME} !-f
RewriteCond %{REQUEST_FILENAME} !-d
RewriteRule ^ index.html [L]
DirectoryIndex index.html
Options -Indexes
<IfModule mod_headers.c>
  Header always set X-Content-Type-Options "nosniff"
  Header always set Referrer-Policy "strict-origin-when-cross-origin"
  <FilesMatch "\.(png|jpe?g|webp|avif|svg|ico)$">
    Header set Cache-Control "public, max-age=604800"
  </FilesMatch>
  <FilesMatch "-[A-Za-z0-9_-]{8,}\.(js|css|woff2?|mp4)$">
    Header set Cache-Control "public, max-age=31536000, immutable"
  </FilesMatch>
  <FilesMatch "^(index\.html|sitemap\.xml|robots\.txt|deployment-.*\.json)$">
    Header set Cache-Control "no-cache"
  </FilesMatch>
</IfModule>
'''


def unpack(data, destination, commit):
    """Never extract links, traversal paths, executable server code or tar metadata."""
    if len(data) > MAX_ARCHIVE:
        raise ValueError('Archive too large')
    total = 0
    seen = set()
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        for index, member in enumerate(archive):
            if index > 2000:
                raise ValueError('Too many archive entries')
            name = member.name.removeprefix('./').rstrip('/')
            if name in ('', '.') and member.isdir():
                continue
            path = PurePosixPath(name)
            if path.is_absolute() or '\\' in name or '..' in path.parts or name != path.as_posix():
                raise ValueError('Unsafe archive path')
            if name in seen or any(part.startswith('.') for part in path.parts if part != '.htaccess'):
                raise ValueError('Duplicate or hidden archive path')
            seen.add(name)
            if not (member.isdir() or member.isfile()):
                raise ValueError('Links and special files are forbidden')
            if len(path.parts) > 1 and path.parts[0] not in ('assets', 'media', 'fonts'):
                raise ValueError('Unexpected directory')
            if member.isdir():
                if path.parts[0] not in ('assets', 'media', 'fonts'):
                    raise ValueError('Unexpected directory')
                (destination / name).mkdir(parents=True, exist_ok=True)
                continue
            if len(path.parts) == 1 and name not in ('index.html', 'favicon.svg', 'icons.svg', 'robots.txt', 'sitemap.xml', '.htaccess', f'deployment-{commit}.json'):
                raise ValueError('Unexpected root file')
            if name != '.htaccess' and path.suffix.lower() not in ('.html', '.js', '.css', '.json', '.xml', '.svg', '.png', '.jpg', '.jpeg', '.webp', '.gif', '.ico', '.mp4', '.woff', '.woff2', '.ttf', '.txt', '.avif', '.pdf'):
                raise ValueError('Unexpected file type')
            total += member.size
            if member.size > 32 * 1024 * 1024 or total > MAX_CONTENT:
                raise ValueError('Content too large')
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, target.open('xb') as output:
                shutil.copyfileobj(source, output)
    for name in ('index.html', '.htaccess', f'deployment-{commit}.json'):
        if not (destination / name).is_file():
            raise ValueError('Required file missing: ' + name)
    if json.loads((destination / f'deployment-{commit}.json').read_text()).get('commit') != commit:
        raise ValueError('Deployment marker mismatch')
    # SSH credentials cannot inject PHP handlers or other server configuration.
    (destination / '.htaccess').write_text(STATIC_HTACCESS)


def safe_release(value):
    value = Path(value)
    if value.parent != RELEASES or not re.fullmatch(r'(?:[0-9a-f]{40}|legacy-[0-9]+)', value.name) or not value.is_dir() or value.is_symlink():
        raise ValueError('Invalid release path')
    return value


def permissions(folder):
    import grp
    import pwd
    owner = Path('/etc/mercaflor-concierge-owner').read_text().strip()
    uid = pwd.getpwnam(owner).pw_uid
    if uid == 0:
        raise ValueError('Deploy site owner cannot be root')
    gid = grp.getgrnam('nogroup').gr_gid
    for root, dirs, files in os.walk(folder):
        os.chown(root, uid, gid)
        os.chmod(root, 0o755)
        for name in dirs + files:
            target = Path(root) / name
            if target.is_symlink():
                raise ValueError('Release cannot contain symlinks')
            os.chown(target, uid, gid)
            os.chmod(target, 0o755 if target.is_dir() else 0o644)


def switch(target):
    target = safe_release(target)
    temporary = BASE / ('.deploy-link-' + str(os.getpid()))
    temporary.symlink_to(target)
    try:
        if PUBLIC.is_symlink():
            safe_release(PUBLIC.resolve())
            os.replace(temporary, PUBLIC)
        elif PUBLIC.is_dir():
            # Linux renameat2 exchanges the original directory and link atomically.
            libc = ctypes.CDLL(None, use_errno=True)
            rename = libc.renameat2
            rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
            rename.restype = ctypes.c_int
            if rename(-100, os.fsencode(temporary), -100, os.fsencode(PUBLIC), 2) != 0:
                raise OSError(ctypes.get_errno(), 'Atomic first publication failed')
            try:
                os.replace(temporary, BACKUPS / ('original-public-html-' + str(time.time_ns())))
            except Exception:
                rename(-100, os.fsencode(temporary), -100, os.fsencode(PUBLIC), 2)
                raise
        else:
            raise ValueError('Unexpected document root')
    finally:
        if temporary.is_symlink():
            temporary.unlink()


def health(target):
    marker = f'/deployment-{target.name}.json' if re.fullmatch('[0-9a-f]{40}', target.name) else '/'
    result = subprocess.run(['curl', '--fail', '--silent', '--show-error', '--max-time', '15', '--resolve', 'mercaflor.clicpic.co:443:127.0.0.1', 'https://mercaflor.clicpic.co' + marker], capture_output=True, text=True, check=True)
    if marker != '/' and json.loads(result.stdout).get('commit') != target.name:
        raise ValueError('Origin did not serve the expected release')
    if marker == '/' and not result.stdout.strip():
        raise ValueError('Empty origin response')


def save_state(current, previous):
    temp = STATE.with_suffix('.tmp')
    temp.write_text(json.dumps({'current': str(current), 'previous': str(previous)}))
    temp.chmod(0o600)
    os.replace(temp, STATE)


def publish(command, stream):
    if command == 'probe':
        target = PUBLIC.resolve() if PUBLIC.is_symlink() else PUBLIC
        health(target)
        print('READY: restricted deploy receiver and HTTPS origin verified')
        return
    if command == 'rollback':
        state = json.loads(STATE.read_text())
        target, previous = safe_release(state['previous']), safe_release(PUBLIC.resolve())
    else:
        match = re.fullmatch(r'deploy ([0-9a-f]{40})', command)
        if not match:
            raise ValueError('Only probe, deploy <commit> and rollback are allowed')
        commit = match.group(1)
        data = stream.read(MAX_ARCHIVE + 1)
        with tempfile.TemporaryDirectory(prefix='.staging-', dir=RELEASES) as staging:
            staged = Path(staging)
            unpack(data, staged, commit)
            target = RELEASES / commit
            if not target.exists():
                # Keep old hashed assets readable for already-open browser tabs.
                old_assets = PUBLIC / 'assets'
                if old_assets.is_dir():
                    for source in old_assets.iterdir():
                        if source.is_file() and not source.is_symlink() and re.fullmatch(r'[A-Za-z0-9_.-]+', source.name) and source.suffix.lower() in ('.js', '.css', '.mp4', '.woff', '.woff2', '.png', '.svg', '.jpg', '.webp'):
                            destination = staged / 'assets' / source.name
                            if not destination.exists():
                                destination.parent.mkdir(exist_ok=True)
                                shutil.copy2(source, destination)
                permissions(staged)
                os.replace(staged, target)
            target = safe_release(target)
        if PUBLIC.is_symlink():
            previous = safe_release(PUBLIC.resolve())
        else:
            # Keep a clean legacy version; full original files are also preserved.
            previous = RELEASES / ('legacy-' + str(time.time_ns()))
            previous.mkdir()
            for name in ('index.html', 'favicon.svg', 'icons.svg', '.htaccess', 'assets', 'media', 'es', 'pt', 'robots.txt', 'sitemap.xml'):
                source = PUBLIC / name
                if source.is_dir():
                    shutil.copytree(source, previous / name, symlinks=True)
                elif source.is_file():
                    shutil.copy2(source, previous / name)
            permissions(previous)
    if target == previous:
        health(target)
        print('DEPLOYED: ' + target.name)
        return
    health(previous)  # Fail before switching if the origin is already unhealthy.
    switch(target)
    try:
        health(target)
        save_state(target, previous)
    except Exception:
        switch(previous)
        raise RuntimeError('Publication verification failed; previous release restored')
    print('DEPLOYED: ' + target.name)


def main():
    import fcntl
    if os.geteuid() != 0 or len(sys.argv) != 2:
        raise ValueError('Run through the restricted SSH command')
    if BASE.is_symlink() or BASE.resolve() != BASE or not BASE.is_dir():
        raise ValueError('Unexpected website base path')
    for directory, mode in ((RELEASES, 0o755), (BACKUPS, 0o700)):
        if directory.is_symlink():
            raise ValueError('Unexpected storage symlink')
        directory.mkdir(exist_ok=True)
        directory.chmod(mode)
    with (BASE / '.deploy.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        publish(sys.argv[1], sys.stdin.buffer)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('DEPLOY ERROR: ' + str(error), file=sys.stderr)
        sys.exit(1)
