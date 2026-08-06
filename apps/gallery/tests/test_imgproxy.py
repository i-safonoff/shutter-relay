from django.conf import settings

from apps.gallery import imgproxy


def test_signing_is_deterministic():
    url = imgproxy.signed_url("s3://bucket/key", "thumb")
    assert url == imgproxy.signed_url("s3://bucket/key", "thumb")


def test_different_presets_sign_differently():
    thumb = imgproxy.signed_url("s3://bucket/key", "thumb")
    preview = imgproxy.signed_url("s3://bucket/key", "preview")
    assert thumb != preview


def test_different_sources_sign_differently():
    a = imgproxy.signed_url("s3://bucket/a", "thumb")
    b = imgproxy.signed_url("s3://bucket/b", "thumb")
    assert a != b


def test_variants_returns_every_preset_rooted_at_the_configured_base_url():
    result = imgproxy.variants("album/photo-key")
    assert set(result) == set(imgproxy.PRESETS)
    for url in result.values():
        assert url.startswith(settings.IMGPROXY_BASE_URL)
