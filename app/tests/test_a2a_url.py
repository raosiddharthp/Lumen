import pytest

from app.common.a2a_url import card_origin


def test_unset_means_localhost_on_the_dev_port():
    assert card_origin(8011, {}) == {"host": "localhost", "port": 8011, "protocol": "http"}


def test_a_cloud_run_url_means_https_on_443():
    got = card_origin(8011, {"PUBLIC_URL": "https://lumen-research-1.us-east1.run.app"})
    assert got == {"host": "lumen-research-1.us-east1.run.app", "port": 443, "protocol": "https"}


def test_an_explicit_port_is_kept():
    assert card_origin(1, {"PUBLIC_URL": "http://example.test:9000"})["port"] == 9000


def test_a_trailing_slash_is_harmless():
    assert card_origin(1, {"PUBLIC_URL": "https://a.example/"})["host"] == "a.example"


@pytest.mark.parametrize("bad", ["lumen.run.app", "ftp://x.test", "https://"])
def test_a_malformed_url_fails_loudly(bad):
    with pytest.raises(ValueError):
        card_origin(8011, {"PUBLIC_URL": bad})
