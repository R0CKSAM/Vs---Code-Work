# Secure TOTP MFA Authentication Demo

A minimal, production-grade Multi-Factor Authentication (TOTP 2FA) demo application built with **React**, **Vite**, **Tailwind CSS**, **Cloudflare Workers**, **Hono**, **Cloudflare D1**, **Drizzle ORM**, and **Better Auth**.

---

## Key Security Features

- **Strict In-Browser QR Code Generation**: Uses `qrcode.react` to render QR codes directly to `<svg>` without contacting external APIs or third-party image generation services.
- **Dual-Layer Middleware Protection**:
  - `requireAuth()`: Enforces a valid, active session.
  - `requireMFA()`: Enforces that the session has an active, verified two-factor authentication profile (`twoFactorEnabled = true`). Unverified or password-only sessions cannot access protected API endpoints.
- **Single-Use Recovery Codes**: Recovery backup codes are generated upon MFA setup, stored encrypted by Better Auth, and verified via `twoFactor.verifyBackupCode`. Each code can only be used once.
- **Safe Development Admin Seeding**: Dedicated dev-only endpoint (`/api/dev/seed-admin`) and CLI script (`npm run seed:admin`) that safely seeds or resets a test account with `role = 'admin'` without hardcoding passwords in frontend source code. Dev endpoints are automatically disabled in production.
- **Zero Sensitive Data in Client Storage**: Passwords, Better Auth secrets, TOTP secrets, recovery codes, and tokens are **never** stored in browser `localStorage`.

---

## Project Structure

```
d:/MFA/
├── db/
│   ├── schema.ts            # Drizzle ORM SQLite / D1 schema (user, session, account, verification, twoFactor)
│   └── migrations/
│       └── 0000_init.sql    # D1 SQL migration script
├── worker/
│   ├── index.ts             # Cloudflare Worker entry point with Hono routes & dev seeder
│   ├── auth.ts              # Better Auth server configuration (Drizzle adapter + twoFactor + admin)
│   ├── middleware.ts        # requireAuth() and requireMFA() server middleware
│   └── db.ts                # Drizzle D1 database initializer
├── src/
│   ├── components/
│   │   ├── Navbar.tsx       # Minimal navigation header with session status
│   │   ├── OtpInput.tsx     # Clean 6-digit TOTP input with auto-advance and clipboard paste
│   │   └── Alert.tsx        # Notification and error alert banner
│   ├── pages/
│   │   ├── Login.tsx        # Email + password authentication with MFA redirect detection
│   │   ├── MfaSetup.tsx     # Offline QR code scanner, initial verification, & recovery codes display
│   │   ├── MfaVerify.tsx    # TOTP authenticator verification & single-use recovery code fallback
│   │   ├── Dashboard.tsx    # Protected dashboard proving backend requireMFA() verification
│   │   └── Security.tsx     # Account security: regenerate recovery codes, disable MFA, logout all
│   ├── lib/
│   │   ├── auth-client.ts   # Better Auth client with twoFactorClient & adminClient plugins
│   │   └── api.ts           # Fetch client for protected endpoints with credentials
│   ├── App.tsx              # React router setup
│   ├── main.tsx             # React application mount
│   └── index.css            # Tailwind CSS configuration
├── scripts/
│   └── seed-admin.ts        # CLI tool to create/reset local development admin account
├── wrangler.jsonc           # Cloudflare Workers configuration with D1 database binding
├── vite.config.ts           # Vite development server with /api proxy to local worker
├── drizzle.config.ts        # Drizzle kit configuration
├── package.json             # NPM dependencies & scripts
├── .dev.vars                # Cloudflare Workers local environment secrets
└── README.md                # Documentation & test guide
```

---

## ⚡ Instant Test Without Node.js (Zero-Install Edition)

If you do not have Node.js or administrator privileges installed on your machine, you can immediately test the entire TOTP MFA flow in your browser:

```powershell
Start-Process "D:\MFA\standalone-demo.html"
```
*(Or double-click `standalone-demo.html` in File Explorer).*

This self-contained edition uses the browser's native **Web Crypto API (HMAC-SHA1)** to compute valid RFC 6238 TOTP codes in real time, generates QR codes offline on an HTML canvas, and allows you to scan with Google Authenticator or Bitwarden with **zero external software installed**.

---

## 1. Prerequisites (For Full Server Stack)

- **Node.js**: v18+ or v20+ (or **Docker**)
- **npm** (or **pnpm** / **yarn**)
- Authenticator app on your phone or desktop:
  - **Google Authenticator**
  - **Microsoft Authenticator**
  - **1Password**
  - **Bitwarden**
  - Or any TOTP-compatible application

---

## 2. Quickstart Commands

### Step 1: Install Dependencies
```bash
npm install
```

### Step 2: Initialize & Migrate Local D1 Database
Create the local D1 database schema and tables using the provided migration file:
```bash
npx wrangler d1 execute mfa-demo-db --local --file=./db/migrations/0000_init.sql
```

### Step 3: Start the Backend Cloudflare Worker
In your first terminal window:
```bash
npm run dev:worker
```
*(Runs on `http://127.0.0.1:8787`)*

### Step 4: Seed the Development Admin Account
In a second terminal window, run the safe admin seeder:
```bash
npm run seed:admin
```
*(Alternatively, you can click the **"Create / Reset Local Admin"** button directly on the `/login` page)*

**Default Development Admin Credentials:**
- **Email**: `admin@example.com`
- **Password**: `AdminDemo12345!Secure`
- **Role**: `admin`

### Step 5: Start the Frontend Vite Dev Server
In the second terminal window:
```bash
npm run dev
```
*(Open your browser at `http://localhost:5173`)*

---

## 3. Step-by-Step MFA Testing Guide

Follow this 13-point test plan to verify the entire flow end-to-end:

### Test 1: Wrong Password Fails
1. Navigate to `http://localhost:5173/login`.
2. Enter `admin@example.com` and an incorrect password like `WrongPassword!`.
3. Click **LOGIN**.
4. **Expected**: Login fails and an error message is displayed.

### Test 2: Correct Password + MFA Not Yet Configured
1. Enter `admin@example.com` and `AdminDemo12345!Secure`.
2. Click **LOGIN**.
3. **Expected**: The application detects that MFA is not yet enabled for this account and automatically redirects to `/mfa/setup`.

### Test 3 & 4: Scan QR Code & Enable MFA
1. On `/mfa/setup`, observe the QR code generated completely offline via `qrcode.react`.
2. Open your authenticator app (e.g. Google Authenticator) and scan the QR code.
3. The app will add "Secure MFA Demo (admin@example.com)".
4. Enter the 6-digit code currently shown on your authenticator app into the `[ _ ][ _ ][ _ ][ _ ][ _ ][ _ ]` boxes.
5. Click **VERIFY & ENABLE MFA**.
6. **Expected**: MFA is enabled. The screen displays **"Save your Recovery Codes"** with your one-time backup codes (e.g. `ABCD-1234`, `EFGH-5678`, etc.).
7. Click **Copy All Codes** or record one of them for later testing, then click **I HAVE SAVED THEM**.
8. **Expected**: You are redirected to `/dashboard`.

### Test 5: Dashboard Access & Status Verification
1. On `/dashboard`, observe:
   - "Welcome, Admin"
   - Password: **Verified**
   - MFA: **Verified (TOTP)**
   - Role: **ADMIN**
2. The backend middleware `requireMFA()` has successfully validated the session.

### Test 6: Logout
1. Click the **Logout** button.
2. **Expected**: Session is invalidated, and you are redirected to `/login`.
3. Try directly opening `http://localhost:5173/dashboard`.
4. **Expected**: Instantly redirected back to `/login`.

### Test 7 & 8: Second Login Triggers MFA Verification
1. On `/login`, enter `admin@example.com` and `AdminDemo12345!Secure`.
2. Click **LOGIN**.
3. **Expected**: Better Auth detects that 2FA is active, triggers `twoFactorRedirect`, and the frontend routes directly to `/mfa/verify`.

### Test 9: Wrong MFA Code is Denied
1. On `/mfa/verify`, enter an invalid code: `000000`.
2. Click **VERIFY**.
3. **Expected**: Error message displayed: `Invalid authentication code.`. No access granted.

### Test 10: Correct MFA Code Grants Access
1. Enter the current 6-digit code from your authenticator app.
2. Click **VERIFY**.
3. **Expected**: Successfully redirected to `/dashboard`.

### Test 11: Single-Use Recovery Code Login
1. Click **Logout**.
2. Enter `admin@example.com` and `AdminDemo12345!Secure` on `/login` and submit.
3. On `/mfa/verify`, click **"Use Recovery Code"**.
4. Enter one of the recovery codes you saved in Step 4 (e.g., `ABCD-1234`).
5. Click **VERIFY WITH RECOVERY CODE**.
6. **Expected**: Successfully verified and redirected to `/dashboard`.

### Test 12: Recovery Code Reuse is Denied
1. Click **Logout**.
2. Log in again with password to arrive at `/mfa/verify`.
3. Click **"Use Recovery Code"** and enter the **exact same code** you used in Test 11.
4. Click **VERIFY WITH RECOVERY CODE**.
5. **Expected**: Verification fails (`Invalid authentication code.`) because recovery codes are strictly single-use.

### Test 13: Direct Backend API Protection Without Authentication
1. Open a new incognito window or run `curl` in terminal:
   ```bash
   curl -i http://127.0.0.1:8787/api/protected/dashboard-data
   ```
2. **Expected**: Returns `HTTP/1.1 401 Unauthorized` with:
   `{"error":"UNAUTHORIZED","message":"Authentication session required. Please log in."}`

---

## 4. Environment Variables and Secrets

### Cloudflare Workers (`.dev.vars` for local / Cloudflare Secrets for production):

| Variable | Description | Local Default |
| :--- | :--- | :--- |
| `BETTER_AUTH_SECRET` | 32+ character random secret used for cookie encryption and TOTP secret hashing | *(provided in `.dev.vars`)* |
| `BETTER_AUTH_URL` | Application base URL | `http://localhost:5173` |
| `ENVIRONMENT` | Environment toggle (`development` or `production`). In production, `/api/dev/*` is disabled. | `development` |
| `ADMIN_DEFAULT_EMAIL` | Default email for test Admin account | `admin@example.com` |
| `ADMIN_DEFAULT_PASSWORD` | Default password for test Admin account | `AdminDemo12345!Secure` |

---

## 5. Cloudflare Production Deployment (Optional)

When you are ready to deploy to Cloudflare:

1. **Create Remote D1 Database**:
   ```bash
   npx wrangler d1 create mfa-demo-db
   ```
   Copy the `database_id` returned by Cloudflare and paste it into `wrangler.jsonc` under `d1_databases[0].database_id`.

2. **Run Migrations on Remote D1**:
   ```bash
   npx wrangler d1 execute mfa-demo-db --remote --file=./db/migrations/0000_init.sql
   ```

3. **Set Cloudflare Secrets**:
   ```bash
   npx wrangler secret put BETTER_AUTH_SECRET
   ```

4. **Deploy Worker**:
   ```bash
   npx wrangler deploy
   ```
