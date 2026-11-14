from services.camlora import camlora_endpoint, normalize_camlora_base_url


def test_accepts_private_usb_tether_ip():
    assert normalize_camlora_base_url('http://10.132.148.169:5959') == 'http://10.132.148.169:5959'


def test_normalizes_missing_port():
    assert normalize_camlora_base_url('http://192.168.1.42') == 'http://192.168.1.42:80'


def test_rejects_public_host():
    assert normalize_camlora_base_url('http://example.com:5959') is None


def test_rejects_credentials_and_paths():
    assert normalize_camlora_base_url('http://user:pass@10.0.0.2:5959') is None
    assert normalize_camlora_base_url('http://10.0.0.2:5959/video') is None


def test_endpoint_allowlist():
    base = 'http://10.132.148.169:5959'
    assert camlora_endpoint(base, 'video') == base + '/video'
    assert camlora_endpoint(base, 'shot.jpg') == base + '/shot.jpg'
    assert camlora_endpoint(base, 'anything') is None
