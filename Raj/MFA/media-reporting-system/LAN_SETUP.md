# Media Reporting System - Local Area Network (LAN) Setup Guide

This guide describes how to deploy and access the **Media Reporting System** across a company Local Area Network (LAN) on `0.0.0.0:8000`.

---

## 1. Architecture Overview

- **Host Machine**: Runs the FastAPI backend, crawler scheduler, and SQLite database.
- **Client Devices**: Any computer, tablet, or phone on the same local Wi-Fi or office Ethernet.
- **Port**: Default is `8000` (configurable via `PORT` environment variable).
- **Binding Address**: `0.0.0.0` (accepts connections from localhost and any LAN interface).
- **Single Administrator**: Exactly one administrator account (`rajxy71@gmail.com`) manages user access.
- **User Self-Registration**: Team members register on their own devices. All new accounts default to `PENDING` approval.

---

## 2. Step 1: Provision Administrator Account

Before starting the LAN server, ensure the single administrator account is initialized on the host machine:

```powershell
cd D:\MFA\media-reporting-system
python backend/create_admin.py
```

- When prompted, set a strong administrator password (minimum 10 characters).
- The script hashes the password with PBKDF2-HMAC-SHA256 and provisions the single administrator `rajxy71@gmail.com`.
- Normal users can **never** register as administrators.

---

## 3. Step 2: Find Your Host Machine's IP Address

On the host machine (where the server runs):

1. Open **PowerShell** or **Command Prompt**.
2. Run:
   ```powershell
   ipconfig
   ```
3. Locate your active network adapter (e.g. `Wireless LAN adapter Wi-Fi` or `Ethernet adapter Ethernet`).
4. Find the **IPv4 Address** (for example: `192.168.1.45` or `10.0.0.12`).

---

## 4. Step 3: Configure Windows Defender Firewall

By default, Windows Firewall blocks incoming connections from other LAN devices to port 8000.

### Option A: Via PowerShell (Run as Administrator)

Open **PowerShell as Administrator** and execute:

```powershell
New-NetFirewallRule -DisplayName "Media Reporting System (Port 8000)" `
  -Direction Inbound `
  -LocalPort 8000 `
  -Protocol TCP `
  -Action Allow `
  -Profile Private
```

> **Note**: For security, this rule applies exclusively to **Private** network profiles (office/home Wi-Fi), preventing exposure on untrusted public networks.

### Option B: Via Windows Defender GUI

1. Open **Windows Defender Firewall** (`wf.msc`).
2. Click **Inbound Rules** > **New Rule...**.
3. Select **Port** > click **Next**.
4. Select **TCP** and enter **Specific local ports**: `8000`.
5. Select **Allow the connection** > click **Next**.
6. Check **Private** (uncheck Public) > click **Next**.
7. Name: `Media Reporting System (Port 8000)` > click **Finish**.

---

## 5. Step 4: Start the Server

On the host machine:

### Password reset email configuration

Before starting the server, configure an SMTP account. For Gmail, enable two-step
verification and use a Google App Password (not the normal Gmail password):

```powershell
$env:SMTP_HOST = "smtp.gmail.com"
$env:SMTP_PORT = "587"
$env:SMTP_USERNAME = "your-account@gmail.com"
$env:SMTP_PASSWORD = "your-16-character-app-password"
$env:SMTP_FROM_EMAIL = "your-account@gmail.com"
$env:PUBLIC_BASE_URL = "http://192.168.50.134:8000"
```

Set `PUBLIC_BASE_URL` to the address users use to open the dashboard. These
variables must be set in the same PowerShell window before running the server.

```powershell
cd D:\MFA\media-reporting-system
python run_server.py
```

The server will display:
```
======================================================================
  MEDIA REPORTING - FASTAPI SERVER (LOCAL + LAN)
======================================================================
  Local Access : http://127.0.0.1:8000/
  LAN Access   : http://192.168.50.134:8000/
  API Docs     : http://127.0.0.1:8000/docs
======================================================================
```

---

## 6. Step 5: Connecting from Team Member Devices

### From the Host Machine
- Open browser and navigate to: `http://127.0.0.1:8000/` or `http://192.168.50.134:8000/`

### From Other LAN Devices (Laptops, Desktops, Tablets, Phones)
- Open browser and navigate to: **`http://192.168.50.134:8000/`**

---

## 7. User Registration & Administrator Approval Flow

1. **User Registration**:
   - A team member opens `http://<HOST-IP>:8000/` on their device.
   - Clicks the **Register** tab.
   - Enters their **Full Name**, **Company Email**, and a secure **Password** (min 10 characters).
   - Upon submitting, the screen displays **Approval Pending** awaiting admin action.

2. **Administrator Approval**:
   - The system owner logs in at `http://127.0.0.1:8000/` using `rajxy71@gmail.com`.
   - Clicks **User Management** in the left sidebar under the Administration group.
   - Sees pending accounts in the table.
   - Clicks **Approve Access**.
   - (Optional) Clicks **Edit** under Permissions to customize the user's granular feature access.

3. **User Access Granted**:
   - The user clicks **Check Status** or logs in from their device.
   - They now have access to the shared Media Reporting dashboard.

---

## 8. Granular Permission Matrix

The single administrator (`rajxy71@gmail.com`) always holds all system permissions. Approved users receive granular access based on their assigned role:

| Permission Key | Description | Default for Users |
| :--- | :--- | :---: |
| `dashboard.view` | View high-level metrics & intelligence summaries | **Enabled** |
| `monitoring.view` | Access the monitored publications catalog | **Enabled** |
| `monitoring.news` | Browse and filter real-time scraped articles | **Enabled** |
| `monitoring.advertisements` | Inspect detected brand ads and creatives | **Enabled** |
| `monitoring.changes` | Review historical article and ad changes | **Enabled** |
| `reports.view` | Read daily, weekly, and custom reports | **Enabled** |
| `reports.export` | Download on-demand PDF, Excel, and CSV files | **Enabled** |
| `settings.view` | View crawler schedules and system parameters | **Enabled** |
| `admin.users` | Approve, suspend, and configure user permissions | **Admin Only** |

---

## 9. Troubleshooting & FAQ

### 1. "Can't reach this page" or connection timed out on client devices
- **Check Wi-Fi**: Verify both the host computer and client devices are on the **same Wi-Fi or router**.
- **Check Windows Firewall**: Ensure inbound TCP port 8000 is allowed as described in Step 3.
- **Check Host IP**: If your router uses DHCP, your host IP might change after rebooting. Re-run `ipconfig` to verify.

### 2. Can another user become an administrator?
- **No.** The system enforces a strict single-administrator constraint. Any attempt to register or elevate another account to `ADMIN` is rejected at the API and database levels.

### 3. What happens if a user is suspended?
- If the administrator suspends a user, all active sessions and tokens for that user are immediately deleted from SQLite. The user is logged out instantly on their next action.
