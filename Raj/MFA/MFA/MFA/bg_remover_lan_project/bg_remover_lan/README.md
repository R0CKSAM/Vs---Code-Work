# Office AI Background Remover (LAN)

A browser-based LAN version of the background remover. The server uses `rembg` with the `u2net` model and returns transparent PNG files at the original input image resolution.

## Features

- Browser UI; no software install needed on client computers
- Drag and drop
- JPG / JPEG / PNG / WEBP
- Single image before/after preview
- Transparent PNG download
- Batch processing (default: up to 20 images)
- Batch ZIP download
- Preserves original image dimensions
- One shared U2Net session for faster repeat processing
- Health endpoint at `/health`
- LAN binding on `0.0.0.0:6805`
- Configured for access at `http://192.168.50.134:6805`
- Responsive desktop/mobile interface

## Quick Start

### 1. Start the Server

From the project directory (`d:\MFA\bg_remover_lan_project\bg_remover_lan`):

Using Python:
```bash
python app.py
```
or:
```bash
python run.py
```

Using PowerShell:
```powershell
.\start_server.ps1
```

Once running, the server is accessible at:
- **LAN URL:** [http://192.168.50.134:6805](http://192.168.50.134:6805)
- **Localhost:** [http://127.0.0.1:6805](http://127.0.0.1:6805)

### 2. Open Firewall Port 6805 (if other computers cannot reach it)

If client computers on your LAN cannot access `http://192.168.50.134:6805`, open an Administrator PowerShell prompt and run:

```powershell
New-NetFirewallRule -DisplayName "Office AI Background Remover (Port 6805)" -Direction Inbound -LocalPort 6805 -Protocol TCP -Action Allow
```
Or run the included script:
```powershell
.\open_firewall.ps1
```

## Configuration

Environment variables supported by `app.py`:

- `HOST` — default `0.0.0.0` (binds to all network interfaces)
- `PORT` — default `6805`
- `MAX_FILE_MB` — default `35`
- `MAX_BATCH` — default `20`
- `REMBG_MODEL` — default `u2net`

Example:
```powershell
$env:PORT = "6805"
$env:HOST = "0.0.0.0"
python app.py
```

## Folder layout

```text
bg_remover_lan/
├─ app.py                 # FastAPI backend server (default port 6805)
├─ run.py                 # Runner helper script
├─ start_server.ps1       # PowerShell launcher
├─ open_firewall.ps1      # Script to open port 6805 in Windows Firewall
├─ requirements.txt
├─ README.md
├─ templates/
│  └─ index.html
├─ static/
│  ├─ style.css
│  └─ app.js
├─ outputs/
└─ temp/
```

## Security Note

This version is intended for a trusted internal LAN. It has no login/authentication layer. Do not expose port 6805 directly to the public internet without an authentication layer and HTTPS reverse proxy or VPN.
