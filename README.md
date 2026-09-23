# Shelfmate · Raspberry Pi AI shelf monitor

A local web dashboard and inventory event recorder for four shelf regions viewed by one camera. The application serves its website and MJPEG camera feed on the local network, stores stock state and event history in SQLite, and saves event screenshots on the device. Core runtime processing does not use cloud services.

## Quick start for beginners (demo mode)

The demo needs Python 3.10 or newer. VS Code is optional. The demo does not need a camera or AI model.

### Windows PowerShell

Open PowerShell, move into this project folder, and run:

```bash
python -m venv .venv
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m pip install fastapi "uvicorn[standard]" opencv-python-headless numpy pydantic-settings
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Keep the PowerShell window open while using the dashboard. Open `http://localhost:8000` in a browser. Do not double-click `index.html`; the dashboard must be opened through this address. Stop the server with `Ctrl+C`.

If PowerShell says that `Activate.ps1` is blocked, use the direct `.venv\Scripts\python.exe` commands above; activation is not required. Demo mode draws a synthetic camera view and periodically simulates stock events, which exercises the dashboard and event/evidence workflow without a camera. The first simulated event appears after the configured demo interval.

### Raspberry Pi OS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` on the Pi, or `http://<pi-address>:8000` from another device on the same LAN.

The first run creates `data/shelf_monitor.db` and `data/evidence/`. The database stores shelf state and events; evidence images are linked from Event history.

## Connect a camera and product model

Set `SHELF_MODE=camera` in `.env`, set `SHELF_CAMERA_INDEX=0` (or the camera's device index), and configure dimensions and frame rate for the device. Attach one USB camera or CSI camera exposed through a compatible Video4Linux/OpenCV device. On Raspberry Pi OS, the camera should be available to OpenCV via V4L2; CSI camera support depends on the OS camera stack and may require a V4L2 bridge or `libcamera` configuration.

For product names and counts, provide an Ultralytics-compatible object detection model trained on the products being monitored, then set `SHELF_MODEL_PATH=/absolute/path/to/model.pt`. Model labels must match the product names configured in `SHELF_PRODUCTS` (case-insensitive). Stock quantity is an approximate count of detected product instances in each region, capped at the configured shelf capacity (currently 12). A generic pretrained COCO model does not identify the example brands accurately; use a product-specific model for meaningful inventory results.

Set `SHELF_REGIONS` to four `[x,y,width,height]` rectangles in normalized image coordinates (0–1) and `SHELF_PRODUCTS` to the corresponding four expected class names, in shelf order. Example values are in `.env.example`. Put the camera at a fixed position so the regions remain aligned. `SHELF_CONFIRM_FRAMES` sets the number of consecutive matching observations required before accepting a stock count or wrong-shelf alert.

## Start at boot (Raspberry Pi OS)

Copy the project to `/opt/shelf-monitor`, install dependencies in its `.venv`, and create `/opt/shelf-monitor/.env`. Edit `deploy/shelf-monitor.service` if your install path or service user differs, then:

```bash
sudo cp deploy/shelf-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now shelf-monitor
sudo systemctl status shelf-monitor
```

The service binds to `0.0.0.0:8000`; allow TCP port 8000 on the local network firewall if enabled. SQLite and evidence images are kept under `data/` relative to the service working directory.

## What is implemented

- Four configurable shelf ROIs and shelf-to-product assignments.
- Approximate `Full`, `Medium`, `Low`, and `Empty` levels with quantities.
- Consecutive-frame confirmation for stock change and wrong-product detection.
- `Stock Removed`, `Stock Replenished`, and `WRONG SHELF` event records with old/new quantities, UTC timestamps, event detail, and evidence image.
- Live MJPEG feed, annotated ROIs and detector boxes, current dashboard, recent alerts, and event history with evidence links.
- SQLite persistence and restart-on-boot service example.

## Notes for installation and tuning

The sample regions and example product names are starting configuration, not camera calibration. The model's count of visible instances is only a quantity estimate: occlusion, stacked products, packaging changes, and lighting can affect it. Camera feed and local dashboard work in demo mode before a detector is supplied. Product recognition in camera mode requires an appropriate trained model; without one, the camera is displayed but inventory detections are not generated. The web service is intended for a trusted local network; it does not include user authentication or TLS.
