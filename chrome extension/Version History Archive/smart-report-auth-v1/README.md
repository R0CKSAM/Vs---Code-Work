# Smart Report – Microsoft 365 Authentication Test v1

**Purpose:** Verify Microsoft Entra sign-in and Microsoft Graph `/me` with your work account. This build does not take screenshots or send email.

## Install
1. Extract the ZIP and load the inner `smart-report-auth-v1` folder with Chrome > `chrome://extensions` > Developer mode > Load unpacked.
2. Inspect extension ID on Chrome extension details; the build embeds a public key in its manifest to keep that ID stable while reloading this package.
3. In Entra > App registrations > Smart Report - Grafana Automation > Authentication > Add Redirect URI, add the **exact** URL shown in the popup. Use *Single-page application* where accepted for this browser OAuth PKCE flow. Save.
4. Copy **Application (client) ID** and **Directory (tenant) ID** from Entra app Overview into the extension popup.
5. Click Test Microsoft sign-in, follow the company login/consent screens, and check the popup result. If admin approval is required, contact your IT admin; do not grant tenant-wide consent without approval.

## Security
- Public OAuth client with authorization code + PKCE + random state; no client secret.
- Requests `openid profile offline_access User.Read Mail.Send` for future functionality. The test only calls Microsoft Graph `/me`, **not** `sendMail`.
- Access and refresh tokens are **not persisted**. The app stores only Client ID and Tenant ID in `chrome.storage.local`.
- The full screenshot/email scheduler is a separate development step.
- The redirect origin must match Chrome's `chrome.identity.getRedirectURL()` exactly.

## Troubleshooting
- `AADSTS50011`: Entra redirect URI mismatch — verify exact URL and platform.
- `AADSTS65001` or approval needed: user/admin consent is not granted.
- Authorization was cancelled: rerun sign-in, and check popup status.
- Chrome extension ID changes: use the ID shown by the installed extension and confirm it matches the copied redirect URL.

Support: Please contact Smarth for support.
