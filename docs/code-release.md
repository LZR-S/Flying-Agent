# Photography harness source

This repository includes the RGB-driven drone photography harness, its Webots R2025a scenarios, and a DJI Tello backend. The harness code is licensed under Apache-2.0; see [LICENSE](../LICENSE). Scene assets retain their own terms, documented in [asset licenses](asset-licenses.md).

## Install

Python 3.12, Git LFS, and Webots R2025a are required for simulation. The launch path has been verified on macOS. Clone with Git so LFS assets are available:

```sh
git lfs install
git clone https://github.com/LZR-S/Flying-Agent.git
cd Flying-Agent
git lfs pull
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
```

Set your own API credentials in `.env`. OpenLux uses `BASE_URL` and `API_KEY`; the dashboard can also select the AliCloud endpoint using `AliCloud_url` and `AliCloud_key`. The example file contains no credentials. Model and image-generation calls may incur provider charges.

## Dashboard

```sh
python -m drone_agent dashboard --port 8766 --env-file .env --open
```

The dashboard opens at <http://127.0.0.1:8766>. English is the initial language; use the top-bar button to switch to Chinese. The choice persists in the browser. Select a scenario, provider, model, and task before starting. The dashboard supports Webots runs and historical replay; it does not control the real aircraft.

## Command line

```sh
python -m drone_agent run --scenario hidden --model gemini-3.6-flash \
  --brief 'Find a person and take a full-body photo' --env-file .env
```

Available scenarios are `facing`, `open`, `hidden`, and `terrace`. By default, the CLI uses Webots at `/Applications/Webots.app/Contents/MacOS/webots`; use `--webots` for a different path. Run artifacts are saved under `runs/`. The Tello backend is available with `--backend tello`, but it has passed offline fault tests only and has not undergone real-aircraft flight acceptance. Do not infer that the public real-world demo was produced or validated by this release.

## Offline tests

```sh
python -m pytest
```

For the optional DJI Tello SDK receiver tests, install `python -m pip install -e '.[dev,tello]'`. Offline tests do not start Webots or call model APIs. The historical v0 snapshot under `baseline/v0/` is not distributed, so its integration tests are skipped.

Further technical details: [tool protocol](native-tools.md), [dashboard](workbench.md), and [Tello action contract](tello-profile.md).
