"""Failure injection ONLY for the disposable statuswatch-v1-validation stack.

Run from repository root after following the isolated setup in validation-v1.0.md.
Never targets the default development or production Compose project.
"""
import json
import subprocess
import time
import urllib.error
import urllib.request

COMPOSE = ['docker', 'compose', '-p', 'statuswatch-v1-validation', '-f', 'compose.prod.yaml',
           '-f', '/tmp/statuswatch-v1-prod.yaml']
BASE = 'http://127.0.0.1:18080/api'


def health():
    try:
        response = urllib.request.urlopen(BASE + '/health', timeout=12)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        return response.status, json.load(response)


def healthy():
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            if health()[0] == 200:
                return
        except (OSError, ValueError):
            pass
        time.sleep(1)
    raise AssertionError('Health did not recover')


def main():
    healthy()
    for service, key in [('redis', 'redis'), ('db', 'database')]:
        try:
            subprocess.run(COMPOSE + ['stop', service], check=True)
            code, body = health()
            assert code == 503 and body['services'][key] == 'unhealthy'
        finally:
            subprocess.run(COMPOSE + ['start', service], check=True)
        healthy()
        print(f'PASS: {service} down 503 and recovery 200', flush=True)
    subprocess.run(COMPOSE + ['restart', 'worker'], check=True)
    subprocess.run(COMPOSE + ['up', '-d', '--wait'], check=True)
    healthy()
    print('PASS: worker restart and dependency recovery', flush=True)


if __name__ == '__main__':
    main()
