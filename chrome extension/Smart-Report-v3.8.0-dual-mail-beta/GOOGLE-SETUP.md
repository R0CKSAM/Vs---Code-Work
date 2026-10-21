# Google/Gmail opt-in setup — beta

**Outlook scheduling remains unchanged.** Google can authorize a user and send **one** approved screenshot test; recurring Gmail mode and central mailbox backend are future features.

1. Open Google Cloud Console, create/select a project and configure the OAuth consent screen and your approved test users. Choose External where appropriate. For wider distribution Google may require verification of `gmail.send`.
2. Enable the **Gmail API**.
3. Create an **OAuth Client ID**, application type **Chrome Extension**, using the extension ID shown at `chrome://extensions/` (not a Web application redirect). The manifest's existing `key` is preserved from v3.7.5 to stabilize unpacked extension identity; verify the actual ID in Chrome.
4. Replace `REPLACE_WITH_GOOGLE_CHROME_CLIENT_ID.apps.googleusercontent.com` in `manifest.json` > `oauth2.client_id` with the actual Chrome Extension OAuth client ID.
5. Save/reload unpacked extension, open the popup and click **Connect Google / Gmail (Beta)**. Grant `gmail.send` and `userinfo.email` if permitted.
6. Sign in to Outlook as normal for dashboard preview. Link Grafana, capture and approve screenshot. After this, click **Send approved screenshot via Gmail**.
7. Verify Gmail Sent and recipient inbox. OAuth approval may still be required by Google Workspace admins. All recipient domain restrictions still apply.

**Security**: do not add Google client secrets, passwords, tokens, or service-account keys to the extension. Google's identity API manages Google token caching. `clearAllCachedAuthTokens` also clears other Google tokens cached by this extension. This is a development/test build and should not be distributed to all employees before consent, privacy, and error handling are reviewed.

**Not yet implemented**: automatic Gmail scheduling, switching Outlook/Gmail in the active schedule, secure central sending backend, multi-provider trusted-server allowlists, the central mailbox backend. Those require separate test and approval. A local extension-side recipient allowlist cannot enforce access against someone who edits extension files.
