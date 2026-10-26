# Smart Report v3.8.1 — Google-only dashboard fix

Google login now opens the main screenshot and recipient setup without Microsoft Outlook authentication. Gmail users can capture, approve and test-send a screenshot. Outlook-only scheduled automation and Outlook test remain available only when an Outlook account is connected.

Note: The Google login address is restored from extension local storage; if a stored authorization is revoked, reconnect Google before Gmail sending. A successful OAuth sign-in does not validate Gmail delivery. Company recipient domain policy still applies.

Install by replacing the previous unpacked extension folder and reloading in chrome://extensions. Preserve the original extension key and Google OAuth client.
