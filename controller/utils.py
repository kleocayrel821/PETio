import requests


def check_device_connection(device_ip: str, timeout: int = 3) -> bool:
    """
    Ping the ESP8266 device to verify connectivity.

    Returns True if the device responds with HTTP 200 at /ping, otherwise False.
    """
    if not device_ip:
        return False
    try:
        resp = requests.get(f"http://{device_ip}/ping", timeout=timeout)
        return resp.status_code == 200
    except requests.RequestException:
        return False