# Smart Report 3.7.5 — Microsoft organization sign-in

The application client ID, redirect URI, extension key, PKCE and delegated scopes remain unchanged.
Sign-in/code exchange use the organizations endpoint. Refresh uses the verified tenant.
The application accepts signed v2 identities only from Veto Streaming and India TV, with signature, issuer, audience, expiry, not-before and login nonce validation before credentials are stored.
Existing sessions must sign in again. Upgrade pauses schedules and requires screenshot approval again.

## Administrator action (not performed by this patch)

In Microsoft Entra, open App registrations, select Smart Report (client ID 00ad226c-9ab3-42d0-add9-1d5d8964f41b), and set Supported account types to Accounts in any organizational directory (multitenant). Keep the registered Chrome redirect URI and public-client configuration.
India TV may need administrator consent under its organization policies for the existing delegated permissions, including Mail.Send.
Do not add a client secret to the extension. Guest invitations to Veto are not needed for home-organization mailbox sign-in.

## Activate

1. Reload the actual unpacked installation in chrome://extensions; confirm 3.7.5.
2. Sign in with the intended Veto or India TV Microsoft 365 mailbox.
3. Confirm the account, review/approve the screenshot, send one test, and check the received attachment.
4. Explicitly start scheduling after the test.

Recipient permissions are separate from permitted sign-in tenants. This patch preserves each copy's recipient configuration. Full email addresses inside allowedRecipientDomains do not work as exact-address exceptions; that requires a separate change.

61 local regression checks passed, including real WebCrypto signatures for both tenants and rejection of altered signatures, unapproved tenants, wrong issuer/audience/nonce and expired identities. Microsoft metadata responses and mailbox APIs were mocked. Live Entra consent, sign-in, refresh and mailbox delivery still need verification.
An allowlist in an editable unpacked extension is not a tamper-proof licensing or organizational access-control boundary.

References:
- https://learn.microsoft.com/en-us/entra/architecture/authenticate-applications-and-users
- https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference
