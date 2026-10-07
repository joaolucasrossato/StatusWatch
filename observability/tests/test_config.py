"""Static deployment boundary checks against resolved root Compose configs."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]


class DeploymentBoundaries(unittest.TestCase):
    def config(self, filename):
        env = dict(os.environ, DATABASE_URL='postgresql+psycopg://test:test@db/test',
                   REDIS_URL='redis://redis:6379/0', JWT_SECRET='validation-only-not-a-real-secret',
                   POSTGRES_PASSWORD='validation-only', GRAFANA_ADMIN_PASSWORD='validation-only',
                   NODE_EXPORTER_LISTEN_ADDRESS='172.17.0.1')
        return json.loads(subprocess.check_output(
            ['docker', 'compose', '-f', filename, 'config', '--format', 'json'], cwd=ROOT, env=env))

    def test_production_only_publishes_web(self):
        services = self.config('compose.prod.yaml')['services']
        self.assertEqual({name for name, service in services.items() if service.get('ports')}, {'web'})
        self.assertEqual(services['web']['ports'][0]['host_ip'], '127.0.0.1')

    def test_development_ports_are_loopback_only(self):
        services = self.config('compose.yaml')['services']
        self.assertEqual({name for name, service in services.items() if service.get('ports')},
                         {'web', 'api', 'grafana', 'prometheus', 'alertmanager'})
        for service in services.values():
            for port in service.get('ports', []):
                self.assertEqual(port['host_ip'], '127.0.0.1')

    def test_exporter_privileges_and_storage(self):
        for filename in ['compose.yaml', 'compose.prod.yaml']:
            config = self.config(filename)
            services = config['services']
            self.assertTrue(config['networks']['observability']['internal'])
            for name in ['prometheus', 'grafana', 'alertmanager', 'node-exporter', 'cadvisor']:
                service = services[name]
                self.assertFalse(service.get('privileged', False), name)
                self.assertNotIn(':latest', service['image'])
                self.assertIn('no-new-privileges:true', service['security_opt'])
                for mount in service.get('volumes', []):
                    if mount['type'] == 'bind':
                        self.assertTrue(mount['read_only'], (name, mount['target']))
            self.assertEqual(services['node-exporter']['network_mode'], 'host')
            self.assertIn('--web.listen-address=172.17.0.1:9100', services['node-exporter']['command'])
            self.assertEqual({cap.removeprefix('CAP_') for cap in services['cadvisor']['cap_add']}, {'DAC_READ_SEARCH'})
            for volume in ['prometheus_data', 'grafana_data', 'alertmanager_data']:
                self.assertIn(volume, config['volumes'])


if __name__ == '__main__':
    unittest.main()
