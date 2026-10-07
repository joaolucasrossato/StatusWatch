#!/usr/bin/env python3
"""Test the built production Nginx image against the dev API, without prod data."""
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]


def main():
    dev = json.loads(subprocess.check_output(['docker', 'compose', 'config', '--format', 'json'], cwd=ROOT))
    prod = json.loads(subprocess.check_output(['docker', 'compose', '-f', 'compose.prod.yaml',
                                             '--env-file', '.env.production', 'config', '--format', 'json'], cwd=ROOT))
    image = prod['services']['web'].get('image', prod['name'] + '-web')
    name = 'statuswatch-proxy-test-' + uuid.uuid4().hex[:8]
    try:
        subprocess.run(['docker', 'run', '--rm', '-d', '--name', name,
                        '--network', dev['networks']['statuswatch']['name'],
                        '-p', '127.0.0.1::80', image], check=True, stdout=subprocess.DEVNULL)
        port = json.loads(subprocess.check_output(['docker', 'inspect', name]))[0]['NetworkSettings']['Ports']['80/tcp'][0]['HostPort']
        base = 'http://127.0.0.1:' + port
        for _ in range(30):
            try:
                with urllib.request.urlopen(base + '/api/health', timeout=2) as response:
                    assert response.status == 200
                break
            except urllib.error.URLError:
                time.sleep(1)
        else:
            raise AssertionError('Production Nginx did not become ready')
        for path in ['/metrics', '/metrics/', '/api/metrics', '/api/metrics?query=test',
                     '/api//metrics', '/api/%6detrics', '/api/metrics/']:
            try:
                urllib.request.urlopen(base + path, timeout=5)
            except urllib.error.HTTPError as error:
                assert error.code == 404, (path, error.code)
            else:
                raise AssertionError('Metrics exposed through proxy: ' + path)
        with urllib.request.urlopen('http://127.0.0.1:8000/metrics', timeout=5) as response:
            assert response.status == 200
        print('PASS: seven proxy metrics paths blocked; /api/health and direct API /metrics remain available')
    finally:
        subprocess.run(['docker', 'stop', name], check=False, stdout=subprocess.DEVNULL)


if __name__ == '__main__':
    main()
