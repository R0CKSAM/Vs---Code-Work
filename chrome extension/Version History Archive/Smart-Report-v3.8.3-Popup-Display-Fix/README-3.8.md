# Smart Report 3.8.0 — Dual Mail Beta

Based on supplied Smart Report v3.7.5 manifest package. The v3.7.5 Microsoft OAuth, Grafana capture, preview approval and Outlook scheduler have been retained. New optional Google OAuth and one-time Gmail send test are isolated from the scheduled Outlook path.

**Setup**: see GOOGLE-SETUP.md. Google OAuth client ID is not supplied; test login will fail clearly until configured. Never put secrets in the extension. Company `allowedRecipientDomains` invalid address-like values removed; `vetostreaming.com` and `indiatvnews.com` retained. Mail to Gmail addresses outside those domains is therefore blocked unless company policy is explicitly updated.

**Known boundaries**: no server-side allowlist, no Gmail scheduled sending yet, no central backend, no validated live Google consent. Microsoft login must be used to approve the screenshot in this beta. Keep v3.7.5 package available as rollback.

Optional CC/BCC editor is available for Outlook and Gmail tests; recipients are validated against existing company allowed domains. Gmail testing is blocked while Outlook schedule is running.
