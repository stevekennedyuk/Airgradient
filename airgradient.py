#!/usr/bin/env python3
"""Standalone AirGradient ONE/Open Air local-API client (Python 3.15).

Uses only the standard library. Edit DEFAULT_HOST below to save your monitor.

Examples:
  python3.15 airgradient.py --host 192.168.1.50 read
  python3.15 airgradient.py config --host airgradient_abcdef123456.local
  python3.15 airgradient.py set temperatureUnit=c ledBarBrightness=40
  python3.15 airgradient.py set postDataToAirGradient=false
  python3.15 airgradient.py set corrections.pm02.correctionAlgorithm=epa_2021
  python3.15 airgradient.py set --json '{"mqttBrokerUrl":"mqtt://192.168.1.2:1883"}'

After setting DEFAULT_HOST, omitting --host uses that value. With no command,
the program reads measurements. --raw prints JSON for scripting. Configuration
changes use PUT /config; cloud configuration may subsequently override them.
Use configurationControl=local only if you intend to manage settings locally.
"""

import argparse
import json
import math
import sys
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener


# Save your default IP address or hostname here; --host overrides it.
DEFAULT_HOST = ""

# Label, unit for known readings. Unknown fields are also displayed.
READINGS = {
    "rco2": ("CO₂", "ppm"),
    "pm01": ("PM1.0", "µg/m³"),
    "pm02": ("PM2.5", "µg/m³"),
    "pm10": ("PM10", "µg/m³"),
    "pm02Compensated": ("PM2.5 (corrected)", "µg/m³"),
    "atmp": ("Temperature", "°C"),
    "atmpCompensated": ("Temperature (corrected)", "°C"),
    "rhum": ("Humidity", "%"),
    "rhumCompensated": ("Humidity (corrected)", "%"),
    "tvocIndex": ("VOC index", ""),
    "noxIndex": ("NOx index", ""),
    "wifi": ("Wi-Fi signal", "dBm"),
    "serialno": ("Serial number", ""),
    "model": ("Model", ""),
    "firmware": ("Firmware", ""),
}


def reject_constant(value):
    raise ValueError(f"Non-finite JSON number: {value}")


def decode_json(value):
    return json.loads(value, parse_constant=reject_constant)


def base_url(host):
    host = host.strip()
    if not host:
        raise ValueError("Specify --host IP_OR_HOSTNAME, or edit DEFAULT_HOST in this script.")
    if "://" not in host:
        host = "http://" + host
    parts = urlsplit(host)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("Host must be an IP address, hostname, or HTTP(S) URL.")
    if parts.username or parts.password or parts.query or parts.fragment or parts.path not in ("", "/"):
        raise ValueError("Host must not contain credentials, a path, query, or fragment.")
    # Accessing port validates its syntax and range.
    _ = parts.port
    return f"{parts.scheme}://{parts.netloc}"


def request(url, timeout, payload=None):
    data = None if payload is None else json.dumps(payload, allow_nan=False).encode("utf-8")
    req = Request(url, data=data, method="GET" if payload is None else "PUT",
                  headers={"Accept": "application/json", "Content-Type": "application/json"})
    # Connect directly to the monitor, bypassing environment HTTP proxies.
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", errors="replace").strip()
        raise ValueError(f"HTTP {exc.code} from {url}" + (f": {detail}" if detail else "")) from exc
    except (URLError, OSError) as exc:
        raise ValueError(f"Cannot reach {url}: {getattr(exc, 'reason', exc)}") from exc
    if not body.strip():
        if payload is not None:
            return None
        raise ValueError(f"Empty response from {url}")
    try:
        return decode_json(body)
    except ValueError as exc:
        if payload is not None:
            # Some firmware versions return plain-text acknowledgement for PUT.
            return body.strip()
        raise ValueError(f"Expected JSON from {url}; received {body[:200]!r}") from exc


def flatten(obj, prefix=""):
    for key, value in obj.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict) and value:
            yield from flatten(value, name)
        else:
            yield name, value


def pretty_value(value):
    if isinstance(value, float):
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"
    if isinstance(value, str):
        # Escape control characters so device values cannot affect the terminal.
        return json.dumps(value, ensure_ascii=False)[1:-1] if value else '""'
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def display(obj, title, source, raw=False, readings=False):
    if raw:
        print(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False))
        return
    if not isinstance(obj, dict):
        raise ValueError("Expected a JSON object from the monitor.")
    items = list(flatten(obj))
    if readings:
        order = {key: i for i, key in enumerate(READINGS)}
        items.sort(key=lambda item: (order.get(item[0], len(order)), item[0]))
    rows = []
    for key, value in items:
        label, unit = READINGS.get(key, (key, "")) if readings else (key, "")
        rows.append((label, pretty_value(value) + (f" {unit}" if unit and value is not None else "")))
    width = max([len(label) for label, _ in rows] + [7])
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    heading = f"AirGradient · {title}"
    if sys.stdout.isatty():
        heading = f"\033[1;36m{heading}\033[0m"
    print(f"{heading}\n{source} · {stamp}\n{'─' * (width + 24)}")
    for label, value in rows:
        print(f"  {label:<{width}}  {value}")
    if not rows:
        print("  (no values)")


def assignment_value(text):
    try:
        return decode_json(text)
    except json.JSONDecodeError:
        # Bare strings such as c, local, or mqtt://… are convenient in the shell.
        return text


def make_payload(assignments, json_text):
    result = {}
    if json_text is not None:
        result = decode_json(json_text)
        if not isinstance(result, dict):
            raise ValueError("--json must contain a JSON object.")
    for assignment in assignments:
        key, separator, text = assignment.partition("=")
        if not separator or not key or any(not part for part in key.split(".")):
            raise ValueError(f"Invalid assignment {assignment!r}; use key=value.")
        node = result
        parts = key.split(".")
        for part in parts[:-1]:
            if part not in node:
                node[part] = {}
            if not isinstance(node[part], dict):
                raise ValueError(f"Conflicting assignments at {part!r}.")
            node = node[part]
        if parts[-1] in node:
            raise ValueError(f"Duplicate or conflicting assignment: {key}")
        node[parts[-1]] = assignment_value(text)
    if not result:
        raise ValueError("Supply at least one key=value assignment or a nonempty --json object.")
    # Also rejects overflow such as 1e999 before sending anything.
    json.dumps(result, allow_nan=False)
    return result


def add_options(parser, suppressed=False):
    default = argparse.SUPPRESS if suppressed else None
    parser.add_argument("--host", "-H", default=default,
                        help="monitor IP/hostname (overrides DEFAULT_HOST; optional port)")
    parser.add_argument("--timeout", type=float, default=argparse.SUPPRESS if suppressed else 10.0,
                        help="HTTP timeout in seconds (default: 10)")
    parser.add_argument("--raw", action="store_true", default=argparse.SUPPRESS if suppressed else False,
                        help="print JSON instead of a formatted table")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_options(parser)
    commands = parser.add_subparsers(dest="command")
    for command, help_text in (("read", "read current measurements (default)"),
                               ("config", "read current configuration"),
                               ("set", "update configuration using key=value assignments")):
        sub = commands.add_parser(command, help=help_text)
        add_options(sub, suppressed=True)
        if command == "set":
            sub.add_argument("assignments", nargs="*", metavar="KEY=VALUE")
            sub.add_argument("--json", dest="json_text", help="JSON object of configuration updates")
    args = parser.parse_args(argv)
    try:
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("--timeout must be a positive, finite number.")
        url = base_url(args.host if args.host is not None else DEFAULT_HOST)
        command = args.command or "read"
        if command == "set":
            payload = make_payload(args.assignments, args.json_text)
            result = request(url + "/config", args.timeout, payload)
            if args.raw:
                print(json.dumps({"submitted": payload, "response": result}, indent=2,
                                 ensure_ascii=False, allow_nan=False))
            else:
                display(payload, "Configuration update accepted", url)
                if result is not None:
                    display(result if isinstance(result, dict) else {"response": result},
                            "Server response", url)
                print("\nRun 'config' to check current settings. Cloud-managed settings may override local updates.")
        else:
            path = "/config" if command == "config" else "/measures/current"
            display(request(url + path, args.timeout),
                    "Configuration" if command == "config" else "Current readings",
                    url, args.raw, readings=command == "read")
        return 0
    except (ValueError, UnicodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
