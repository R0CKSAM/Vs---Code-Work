# Smart Report v3.1 — Company Edition (wider popup)

## One-time company configuration

Open `company-config.js` and replace the two placeholder GUIDs with the existing Application (client) ID and Directory (tenant) ID from Microsoft Entra. These identifiers are not secrets. **Never embed client secrets or authentication tokens.**

The same Entra app may be reused by authorized company employees, each signing in with their own Outlook account. A new installed extension ID may require the matching redirect URI registered in Entra. The original manifest public key is retained.

## Employees

Install the unpacked extension, connect Outlook, choose Grafana, add To / CC / BCC, and start monitoring (15 minutes by default). No need to enter IDs in the popup.

## Limits

The extension requires Chrome running and Grafana authentication. Company session/consent policies can require occasional Microsoft sign-in. Background screenshot uses the Chrome debugger permission and must be verified under your IT policies. Screenshots may contain internal analytics—review external recipients carefully.

## Layout changes

Popup width increased from 392px to 590px. Dashboard and email settings occupy two columns, with narrow-width fallback. The existing automation/capture logic is retained except for reading IDs from company-config.js.
