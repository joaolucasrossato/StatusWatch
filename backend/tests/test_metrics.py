def test_metrics_endpoint_exposes_prometheus_metrics(client):
    response = client.get("/")

    assert response.status_code == 200

    metrics = client.get("/metrics")

    assert metrics.status_code == 200
    assert metrics.headers["cache-control"] == "no-store"
    assert "text/plain" in metrics.headers["content-type"]

    body = metrics.text

    assert "statuswatch_api_http_requests_total" in body
    assert "statuswatch_api_http_request_duration_seconds" in body
    assert "statuswatch_api_http_requests_in_progress" in body
    assert 'route="/"' in body


def test_metrics_scrapes_do_not_instrument_themselves(client):
    from app.observability.metrics import (
        API_HTTP_REQUEST_DURATION, API_HTTP_REQUESTS, API_HTTP_REQUESTS_IN_PROGRESS,
    )

    def samples():
        return [sample for collector in (
            API_HTTP_REQUESTS, API_HTTP_REQUEST_DURATION, API_HTTP_REQUESTS_IN_PROGRESS,
        ) for metric in collector.collect() for sample in metric.samples]

    before = samples()
    assert client.get('/metrics').status_code == 200
    assert client.get('/metrics').status_code == 200
    assert samples() == before


def test_routes_and_methods_have_bounded_labels(client, metric_value):
    labels = {'method': 'GET', 'route': '/monitors/{monitor_id}', 'status_code': '401'}
    before = metric_value('api_http_requests_total', **labels)
    for identifier in ('private-identifier-one', 'private-identifier-two'):
        assert client.get('/monitors/' + identifier).status_code == 401
    assert metric_value('api_http_requests_total', **labels) - before == 2

    labels = {'method': 'OTHER', 'route': 'unmatched', 'status_code': '404'}
    before = metric_value('api_http_requests_total', **labels)
    for method in ('PRIVATE-METHOD-ONE', 'PRIVATE-METHOD-TWO'):
        assert client.request(method, '/private-unmatched-path').status_code == 404
    assert metric_value('api_http_requests_total', **labels) - before == 2
    body = client.get('/metrics').text
    for sensitive in ('private-identifier', 'private-unmatched-path', 'PRIVATE-METHOD'):
        assert sensitive not in body


def test_request_metrics_during_request_and_after_exception(client, dependencies, metric_value):
    import pytest

    labels = {'method': 'GET', 'route': '/health'}
    gauge_before = metric_value('api_http_requests_in_progress', method='GET')
    count_before = metric_value('api_http_requests_total', **labels, status_code='500')
    duration_before = metric_value('api_http_request_duration_seconds_count', **labels)

    def fail():
        assert metric_value('api_http_requests_in_progress', method='GET') - gauge_before == 1
        raise RuntimeError('private-error-details')

    dependencies.check.side_effect = fail
    with pytest.raises(RuntimeError, match='private-error-details'):
        client.get('/health')
    assert metric_value('api_http_requests_in_progress', method='GET') == gauge_before
    assert metric_value('api_http_requests_total', **labels, status_code='500') - count_before == 1
    assert metric_value('api_http_request_duration_seconds_count', **labels) - duration_before == 1
    assert 'private-error-details' not in client.get('/metrics').text


def test_successful_request_counts_and_releases_gauge(client, metric_value):
    labels = {'method': 'GET', 'route': '/'}
    before = metric_value('api_http_requests_total', **labels, status_code='200')
    duration_before = metric_value('api_http_request_duration_seconds_count', **labels)
    gauge_before = metric_value('api_http_requests_in_progress', method='GET')
    assert client.get('/').status_code == 200
    assert metric_value('api_http_requests_total', **labels, status_code='200') - before == 1
    assert metric_value('api_http_request_duration_seconds_count', **labels) - duration_before == 1
    assert metric_value('api_http_requests_in_progress', method='GET') == gauge_before
