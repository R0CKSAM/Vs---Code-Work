# Smart Report v3.9.1 — Branded Premium UI

This extension builds directly on the user's working Smart Report v3.9.0 Production Candidate. It retains all Grafana capture, Outlook / Gmail OAuth, delivery and scheduler code while integrating the original chart-envelope Smart Report logo and the navy/mint visual theme.

## What's new
- Approved square icon in 16/32/48/128 px sizes and full wordmark on the welcome screen.
- 540px compact popup with aligned account menu, providers and accordions.
- Navy-to-teal gradient borders and soft lighting on the status card.
- Color semantics: teal Start, amber Pause, blue Resume / email tests, muted red Stop / destructive actions.
- Long email addresses, recipients, subjects, event logs and errors constrained and wrapped.
- Responsive screenshot review tab with the same brand.
- No changes to identity keys, OAuth application IDs, redirect configuration, capture engine or send logic.

## Upgrade in place
1. Keep a backup of your working Smart Report extension folder and pause reporting before changing files.
2. Extract this ZIP.
3. Copy the *contents* of `Smart-Report-v3.9.1-Branded-Premium/` over the files in your current unpacked extension folder. Leave its extension identity unchanged.
4. Open `chrome://extensions/` and click Reload.
5. Open the popup, check account connections and approved capture, then send one test email before resuming.

Do not remove the existing `manifest.key`; it ensures the extension maintains its Chrome identity so Microsoft and Google OAuth redirects stay valid.

## Validation
See `BRANDING-AND-UI-AUDIT.md`. Automated regression/UI checks are not substitutes for a live company rollout test.

Support: Please contact Smarth for support.
