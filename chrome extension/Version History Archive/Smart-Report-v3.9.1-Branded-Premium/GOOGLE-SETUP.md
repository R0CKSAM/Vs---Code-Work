# Gmail setup for Smart Report 3.9.0

The extension uses the `oauth2.client_id` in `manifest.json`, the Chrome extension ID derived from its existing public `key`, and Google's built-in `chrome.identity.getAuthToken`. **No Google client secret is needed or permitted inside a Chrome extension.**

To distribute beyond a limited test group:

1. In Google Cloud Console select the correct Smart Report project and enable the Gmail API.
2. Check OAuth **Audience**. For personal Gmail users or users from multiple Google Workspace organizations choose an **External** application. Publish to production when authorized.
3. Check **Data access**. The minimum scopes requested are `gmail.send` and `userinfo.email`. Follow Google's sensitive-scope verification requirements for broader production rollout.
4. Ensure the Chrome Extension OAuth client is associated with the **same extension ID** used by your deployed Smart Report build. The public manifest key must not change between private installations.
5. Test authorization on an employee's personal or Google Workspace account, send one Gmail screenshot test, and check recipient inbox + Gmail Sent Items.
6. Only after a successful test using the **same screenshot layout, recipient list, subject and sender** does Smart Report permit scheduled Gmail dispatch. A new recipient or sender requires another test.

**Restrictions**: Google Testing-mode grants can expire after seven days; do not assume they remain valid for unattended company-wide monitoring. Google OAuth app verification, browser policies or Workspace administrator controls can require approval. A central shared sender isn't included in this client-only release.

Never embed Gmail passwords, OAuth tokens, private keys, or client secrets in a ZIP or JS file.
