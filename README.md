# Airgradient

A standalone command-line client for the AirGradient ONE and Open Air local HTTP API. Reads current measurements, displays configuration, and updates configuration with formatted terminal output or JSON.

## Requirements

- Python 3.15; no third-party dependencies.
- A compatible monitor running standard firmware with the local API enabled (ONE/Open Air firmware 3.0.10 or later).
- Network access to the monitor from your computer. Available measurements and settings depend on model and firmware.

## Usage

```sh
python3.15 airgradient.py --host 192.168.1.50 read
python3.15 airgradient.py --host airgradient_abcdef123456.local config
python3.15 airgradient.py --host 192.168.1.50 set temperatureUnit=c ledBarBrightness=40
```

You can also run `./airgradient.py` if your `python3` executable is Python 3.15. Omitting the command defaults to `read`.

### Save a default host

Edit the variable near the top of `airgradient.py`:

```python
DEFAULT_HOST = "airgradient_abcdef123456.local"
```

It defaults to `""`. If it is empty and `--host` is omitted, the program prints an error and exits with status 1. `--host` overrides the saved default and can appear before or after the command. An optional port or HTTP(S) base URL is accepted.

With a default configured:

```sh
python3.15 airgradient.py read
python3.15 airgradient.py config
python3.15 airgradient.py set temperatureUnit=c ledBarBrightness=40
```

### Update configuration

Assignments accept JSON numbers, booleans, arrays, objects, and null. Bare text is treated as a string. Use dotted keys for nested configuration, or `--json` for a JSON object:

```sh
python3.15 airgradient.py set postDataToAirGradient=false
python3.15 airgradient.py set corrections.pm02.correctionAlgorithm=epa_2021
python3.15 airgradient.py set --json '{"mqttBrokerUrl":"mqtt://192.168.1.2:1883"}'
```

Updates use `PUT /config`. Run `config` afterwards to inspect current settings. Cloud-managed configuration may override local updates. Set `configurationControl=local` only when you intend to manage settings locally; supported transitions depend on firmware. The client forwards settings to the monitor, which determines supported keys and valid ranges.

### JSON and timeouts

```sh
python3.15 airgradient.py read --raw
python3.15 airgradient.py config --raw
python3.15 airgradient.py --timeout 5 read
python3.15 airgradient.py --help
```

The default request timeout is 10 seconds. Requests bypass environment HTTP proxies to connect directly to the monitor. Exit status is 0 on success, 1 for operational errors, 2 for argument parsing errors, and 130 when interrupted.

## API documentation

- [AirGradient local API access guide](https://www.airgradient.com/documentation/kb/where-do-i-access-the-api-documentation-api-token-and-local-api/)
- [Official local server API documentation](https://github.com/Open-Air-Foundation/firmware-one-openair/blob/master/docs/local-server.md)

## Validation

Exercised on Python 3.15 with mocked HTTP transport: measurements, configuration reads, typed and nested updates, JSON payloads, saved-host fallback, command-line overrides, validation, and network/HTTP errors. Hardware validation has not yet been performed.
