# Outlook and Microsoft Entra setup

Smart Report uses a single Microsoft Entra app registration and the delegated `Mail.Send` and `User.Read` scopes, with authorization-code + PKCE. Each employee sends from their own signed-in mailbox.

- Configure the registration to accept Microsoft Entra organizational accounts according to company policy. For approved cross-company logins use the multitenant application audience and the `organizations` authority already configured in `company-config.js`.
- Keep the Microsoft application ID, registration tenant ID, and permitted tenant IDs in `company-config.js`. They are identifiers, not secrets.
- Keep the **same Chrome extension ID** and its registered Chromiumapp redirect URI across builds.
- Microsoft tenants may require administrator approval for `Mail.Send` even though it is delegated. **Do not attempt to bypass another company's consent policy.** A Gmail account or an approved central delivery service are alternate authorized workflows, not bypasses.
- The `allowedTenantIds` list in `company-config.js` restricts Outlook sign-in to specified organizations. To onboard additional companies, add their validated tenant IDs, review consent/policies and test their users.

No `client_secret`, password or administrator application credential belongs in the extension. If a shared corporate mailbox is needed, a company-managed backend with scoped Graph permissions and separate access control is required.
