#!/usr/bin/env python3
"""Build a local source candidate from an explicit source-only allowlist."""
import hashlib
from pathlib import Path
import tarfile
ROOT = Path(__file__).resolve().parent.parent
VERSION = '0.1.0-alpha.1'
NAMES = ['.gitignore', 'LICENSE', 'README.md', 'HOW-TO.md', 'CHANGELOG.md', 'app.py', 'bridge.py', 'model.py',
         'phonebridge.py', 'send_test.py', 'receive_test.py', 'request_access.py', 'connect_phone.py', 'alerts.py', 'history.py', 'tray.py', 'presentation.py', 'attachment_test.py']
DIRECTORIES = {'assets': {'.css', '.svg', '.wav'}, 'docs': {'.md'}, 'scripts': {'.py', '.sh'}, 'tests': {'.py'}}

def main():
    files = [ROOT/name for name in NAMES]
    for directory, extensions in DIRECTORIES.items():
        files.extend(p for p in sorted((ROOT/directory).iterdir()) if p.is_file() and p.suffix in extensions)
    dist = ROOT/'dist'; dist.mkdir(exist_ok=True)
    archive = dist/f'phonebridge-{VERSION}-source.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for path in files:
            if path.is_symlink():
                raise ValueError('Source symlinks are not allowed in release candidates.')
            tar.add(path, arcname=f'phonebridge-{VERSION}/'+str(path.relative_to(ROOT)), recursive=False)
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_name(archive.name+'.sha256').write_text(checksum+'  '+archive.name+'\n')
    print(archive)
    print(f'{len(files)} source files; no app data, vault notes or capability reports.')

if __name__ == '__main__':
    main()
