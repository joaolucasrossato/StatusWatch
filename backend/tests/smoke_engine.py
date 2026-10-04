"""Explicit integration smoke against a development API/worker, never part of pytest.

Creates a synthetic account and removes its monitors. With --public-url, makes
one monitored GET to that public URL; the default only tests a blocked destination.
"""
import argparse
import json
import secrets
import time
import urllib.error
import urllib.request
import uuid


def main(base: str, public_url: str | None) -> None:
    token = None
    def request(method, path, expected=200, payload=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(base + path, method=method, headers=headers,
            data=json.dumps(payload).encode() if payload is not None else None)
        try:
            response = urllib.request.urlopen(req, timeout=15)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            assert response.status == expected, (method, path, response.status, expected)
            body = response.read()
            return json.loads(body) if body else None

    credentials = {"email": f"engine-{uuid.uuid4().hex}@example.com", "password": secrets.token_urlsafe(24)}
    request('POST', '/auth/register', 201, {**credentials, 'full_name': 'Engine Smoke'})
    token = request('POST', '/auth/login', payload=credentials)['access_token']
    paths = []
    try:
        for url in ['http://127.0.0.1'] + ([public_url] if public_url else []):
            monitor = request('POST', '/monitors', 201, {
                'name': 'Engine Smoke', 'url': url, 'interval_seconds': 30, 'is_active': False,
            })
            path = '/monitors/' + monitor['id']; paths.append(path)
            assert request('GET', path + '/checks/latest') is None
            request('PATCH', path, payload={'is_active': True})
            deadline = time.monotonic() + 45
            result = None
            while time.monotonic() < deadline:
                result = request('GET', path + '/checks/latest')
                if result is not None:
                    break
                time.sleep(1)
            assert result is not None, 'Worker did not persist a check'
            assert result['response_time_ms'] >= 0
            assert result['checked_at'].endswith(('Z', '+00:00'))
            if url == 'http://127.0.0.1':
                assert result['status'] == 'DOWN' and result['error_type'] == 'ssrf_blocked'
            else:
                assert result['status'] == 'UP', (result['status'], result['error_type'])
                assert 200 <= result['http_status_code'] <= 399
            request('PATCH', path, payload={'is_active': False})
            paused_result = request('GET', path + '/checks/latest')
            print('PASS: pending → persisted ' + result['status'] + ', code=' + str(result['http_status_code']), flush=True)
        time.sleep(36)
        assert request('GET', paths[-1] + '/checks/latest') == paused_result
        print('PASS: paused monitor unchanged beyond its interval', flush=True)
    finally:
        for path in paths:
            request('DELETE', path, 204)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('base')
    parser.add_argument('--public-url')
    args = parser.parse_args()
    main(args.base.rstrip('/'), args.public_url)
