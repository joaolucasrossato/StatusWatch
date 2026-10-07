#!/usr/bin/env python3
"""Controlled dev-only end-to-end test of the real TargetDown rule; no app outage."""
import json
import re
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
import urllib.request
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent.parent
AM = 'http://127.0.0.1:9093'


def api(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(AM + path, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=10) as response:
        body = response.read()
        return json.loads(body) if body else None


def main():
    config = json.loads(subprocess.check_output(['docker', 'compose', 'config', '--format', 'json'], cwd=ROOT))
    # Refuse to test if Alertmanager has been changed to send external messages.
    active = api('/api/v2/status')['config']['original']
    assert 'local-only' in active and not re.search(r'\b\w+_configs:', active), (
        'Use the shipped local-only receiver for this test'
    )
    network = config['networks']['observability']['name']
    name = 'statuswatch-alert-test-' + uuid.uuid4().hex[:8]
    labels = {'alertname': 'TargetDown', 'severity': 'critical', 'job': 'api',
              'instance': '127.0.0.1:1', 'validation': name}
    with tempfile.TemporaryDirectory(prefix='statuswatch-alert-') as directory:
        path = Path(directory)
        path.chmod(0o755)
        (path / 'prometheus.json').write_text(json.dumps({
            'global': {'scrape_interval': '5s', 'evaluation_interval': '5s'},
            'rule_files': ['/validation/alerts.yml'],
            'alerting': {'alertmanagers': [{'static_configs': [{'targets': ['alertmanager:9093']}]}]},
            'scrape_configs': [{'job_name': 'api', 'scrape_timeout': '1s', 'static_configs': [
                {'targets': ['127.0.0.1:1'], 'labels': {'validation': name}}]}],
        }))
        try:
            subprocess.run(['docker', 'run', '--rm', '-d', '--name', name, '--network', network,
                            '-v', str(path) + ':/validation-config:ro',
                            '-v', str(ROOT / 'observability/prometheus/alerts.yml') + ':/validation/alerts.yml:ro',
                            config['services']['prometheus']['image'],
                            '--config.file=/validation-config/prometheus.json'], check=True, stdout=subprocess.DEVNULL)
            deadline = time.monotonic() + 210
            while time.monotonic() < deadline:
                found = [a for a in api('/api/v2/alerts') if a['labels'].get('validation') == name]
                if found:
                    assert found[0]['labels'] == labels
                    print('PASS: real TargetDown rule fired and arrived in Alertmanager', flush=True)
                    break
                time.sleep(5)
            else:
                raise AssertionError('TargetDown did not reach Alertmanager within 210 seconds')
        finally:
            subprocess.run(['docker', 'stop', name], check=False, stdout=subprocess.DEVNULL)
            now = datetime.now(timezone.utc)
            # Remove the synthetic incident after stopping its temporary source.
            api('/api/v2/alerts', [{'labels': labels, 'startsAt': (now-timedelta(minutes=5)).isoformat(),
                                  'endsAt': now.isoformat(), 'annotations': {'summary': 'Controlled validation completed'}}])
            print('Temporary Prometheus removed; controlled alert resolved.', flush=True)


if __name__ == '__main__':
    main()
