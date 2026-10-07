#!/usr/bin/env python3
"""Read-only live validation of the development stack. Run from the repo root."""
import base64
import json
from pathlib import Path
import subprocess
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent.parent


def get(url, auth=None):
    headers = {'Authorization': 'Basic ' + auth} if auth else {}
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as response:
        return json.load(response)


def query(expression):
    result = get('http://127.0.0.1:9090/api/v1/query?' + urllib.parse.urlencode({'query': expression}))
    assert result['status'] == 'success', result
    return result['data']['result']


def main():
    config = json.loads(subprocess.check_output(['docker', 'compose', 'config', '--format', 'json'], cwd=ROOT))
    # Read credentials in memory, never place them on the command line or print them.
    env = config['services']['grafana']['environment']
    auth = base64.b64encode((env['GF_SECURITY_ADMIN_USER'] + ':' + env['GF_SECURITY_ADMIN_PASSWORD']).encode()).decode()
    assert get('http://127.0.0.1:8000/health')['status'] == 'healthy'
    targets = get('http://127.0.0.1:9090/api/v1/targets')['data']['activeTargets']
    expected = {'api', 'worker', 'node-exporter', 'cadvisor', 'prometheus', 'alertmanager'}
    assert {t['labels']['job'] for t in targets} == expected
    for target in targets:
        assert target['health'] == 'up', (target['labels']['job'], target['lastError'])
        print('target', target['labels']['job'], 'UP')
    for metric in ['statuswatch_api_http_requests_total', 'statuswatch_scheduler_cycles_total',
                   'node_cpu_seconds_total', 'node_network_receive_bytes_total',
                   'node_filesystem_avail_bytes',
                   'container_network_receive_bytes_total{container_label_com_docker_compose_service!=""}',
                   'container_fs_reads_bytes_total{container_label_com_docker_compose_service!=""}',
                   'container_cpu_usage_seconds_total{container_label_com_docker_compose_service!=""}',
                   'container_memory_working_set_bytes{container_label_com_docker_compose_service!=""}']:
        results = query(metric)
        assert results, 'Missing real samples: ' + metric
        print('samples', metric, len(results))
    groups = get('http://127.0.0.1:9090/api/v1/rules')['data']['groups']
    rules = [rule for group in groups for rule in group['rules']]
    assert len(rules) == 19
    assert all(rule['health'] == 'ok' for rule in rules)
    print('rules: 10 recording + 9 alerting, healthy')
    managers = get('http://127.0.0.1:9090/api/v1/alertmanagers')['data']['activeAlertmanagers']
    assert any('alertmanager:9093' in m['url'] for m in managers)
    print('Prometheus -> Alertmanager discovery OK')
    grafana = 'http://127.0.0.1:3000'
    assert get(grafana + '/api/health')['database'] == 'ok'
    datasource = get(grafana + '/api/datasources/uid/statuswatch-prometheus', auth)
    assert datasource['url'] == 'http://prometheus:9090'
    assert get(grafana + '/api/datasources/uid/statuswatch-prometheus/health', auth)['status'] == 'OK'
    queries = 0
    for path in sorted((ROOT / 'observability/grafana/dashboards').glob('*.json')):
        source = json.loads(path.read_text())
        provisioned = get(grafana + '/api/dashboards/uid/' + source['uid'], auth)
        assert provisioned['meta']['provisioned']
        assert len(provisioned['dashboard']['panels']) == len(source['panels'])
        for panel in source['panels']:
            for target in panel['targets']:
                query(target['expr'])  # Sparse no-event series may legitimately be empty.
                queries += 1
        print('dashboard', source['title'], len(source['panels']), 'panels provisioned')
    print('Grafana datasource healthy;', queries, 'panel queries accepted by Prometheus')


if __name__ == '__main__':
    main()
