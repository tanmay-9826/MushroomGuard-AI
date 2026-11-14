"""Small, dependency-free helpers for a Camlora Android IP camera."""
from ipaddress import ip_address
from urllib.parse import urlsplit


def normalize_camlora_base_url(value):
    """Accept only plain-HTTP URLs on private/local IP addresses.

    Camlora's local video endpoints are unencrypted. Restricting the configured
    endpoint to a private/loopback IP avoids accidentally proxying public hosts.
    Credentials, paths, query strings and fragments are not accepted.
    """
    raw = (value or '').strip()
    if not raw:
        return None
    parsed = urlsplit(raw)
    if parsed.scheme.lower() != 'http' or not parsed.hostname:
        return None
    if parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
        return None
    try:
        address = ip_address(parsed.hostname)
        if not (address.is_private or address.is_loopback or address.is_link_local):
            return None
        port = parsed.port or 80
        if not 1 <= port <= 65535:
            return None
    except ValueError:
        return None
    host = f'[{parsed.hostname}]' if ':' in parsed.hostname else parsed.hostname
    return f'http://{host}:{port}'


def camlora_endpoint(base_url, endpoint):
    base = normalize_camlora_base_url(base_url)
    if not base or endpoint not in ('video', 'shot.jpg'):
        return None
    return f'{base}/{endpoint}'
