"""Exercise installer failure handling without contacting R2 or systemd."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(os.name == 'nt' or not shutil.which('bash'), reason='requires a POSIX shell')
def test_install_stops_if_download_fails(tmp_path):
    script = Path(__file__).resolve().parents[1] / 'deploy' / 'nhsc-release'
    config = tmp_path / 'release.env'
    root = tmp_path / 'releases-root'
    root.mkdir()
    config.write_text(f'NHSC_R2_BUCKET=test\nNHSC_R2_ACCOUNT_ID=test\nNHSC_RELEASE_ROOT={root}\nNHSC_SERVICE=test\nNHSC_HEALTH_URL=http://localhost/health\n', encoding='utf-8')
    copy = tmp_path / 'installer'
    copy.write_text(script.read_text(encoding='utf-8'), encoding='utf-8')
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    aws = bin_dir / 'aws'
    aws.write_text('#!/bin/sh\nexit 42\n', encoding='utf-8')
    aws.chmod(0o755)
    env = {**os.environ, 'NHSC_RELEASE_CONFIG': str(config), 'PATH': f'{bin_dir}{os.pathsep}{os.environ["PATH"]}'}
    result = subprocess.run(['bash', str(copy), 'install'], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert not (root / 'current').exists() and not (root / 'current').is_symlink()


@pytest.mark.skipif(os.name == 'nt' or not shutil.which('bash'), reason='requires a POSIX shell')
def test_install_and_rollback_use_verified_releases(tmp_path):
    import hashlib
    import json
    import tarfile

    root = tmp_path / 'service'
    root.mkdir()
    bucket = tmp_path / 'bucket'
    prefix = bucket / 'releases' / 'nh-supreme-court'
    prefix.mkdir(parents=True)
    config = tmp_path / 'release.env'
    config.write_text(f'NHSC_R2_BUCKET=test\nNHSC_R2_ACCOUNT_ID=test\nNHSC_RELEASE_ROOT={root}\nNHSC_SERVICE=test\nNHSC_HEALTH_URL=http://localhost/health\n', encoding='utf-8')
    source = Path(__file__).resolve().parents[1] / 'deploy' / 'nhsc-release'
    script = tmp_path / 'installer'
    script.write_text(source.read_text(encoding='utf-8'), encoding='utf-8')
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for name, body in {'aws':'cp "$MOCK_BUCKET/${3#s3://test/}" "$4"', 'systemctl':'exit 0', 'curl':'exit 0'}.items():
        command = bin_dir / name
        command.write_text(f'#!/bin/sh\n{body}\n', encoding='utf-8')
        command.chmod(0o755)
    env = {**os.environ, 'MOCK_BUCKET':str(bucket), 'NHSC_RELEASE_CONFIG': str(config), 'PATH':f'{bin_dir}{os.pathsep}{os.environ["PATH"]}'}

    def publish(release_id, payload):
        contents = tmp_path / 'bundle' / release_id
        contents.mkdir(parents=True)
        (contents / 'data').mkdir()
        (contents / 'data' / 'record.txt').write_bytes(payload)
        rel = 'data/record.txt'
        manifest = {'application':'nh-supreme-court', 'manifest_schema_version':1, 'release_id':release_id,
                    'required_files':[rel], 'files':[{'path':rel,'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}]}
        (contents / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        dest = prefix / release_id
        dest.mkdir()
        shutil.copy2(contents / 'manifest.json', dest / 'manifest.json')
        archive = dest / 'runtime.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            tar.add(contents, arcname=release_id)
        pointer = {'application':'nh-supreme-court','release_id':release_id,
                   'archive':f'releases/nh-supreme-court/{release_id}/runtime.tar.gz',
                   'manifest':f'releases/nh-supreme-court/{release_id}/manifest.json',
                   'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
        (prefix / 'current.json').write_text(json.dumps(pointer), encoding='utf-8')

    def run(action):
        return subprocess.run(['bash',str(script),action],env=env,capture_output=True,text=True,check=True)

    publish('r1', b'first')
    run('install')
    assert (root / 'current' / 'data' / 'record.txt').read_bytes() == b'first'
    publish('r2', b'second')
    run('install')
    assert (root / 'current' / 'data' / 'record.txt').read_bytes() == b'second'
    assert (root / 'previous' / 'data' / 'record.txt').read_bytes() == b'first'
    run('rollback')
    assert (root / 'current' / 'data' / 'record.txt').read_bytes() == b'first'
    assert (root / 'previous' / 'data' / 'record.txt').read_bytes() == b'second'

    # A failed health check must restore the active release and retain the
    # previous rollback target. Simulate the readiness wait without delays.
    publish('r3', b'third')
    (bin_dir / 'curl').write_text('#!/bin/sh\nexit 1\n', encoding='utf-8')
    (bin_dir / 'sleep').write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
    (bin_dir / 'sleep').chmod(0o755)
    failed = subprocess.run(['bash', str(script), 'install'], env=env, capture_output=True, text=True)
    assert failed.returncode != 0
    assert (root / 'current' / 'data' / 'record.txt').read_bytes() == b'first'
    assert (root / 'previous' / 'data' / 'record.txt').read_bytes() == b'second'
