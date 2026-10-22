# Smart Report v3.8.3 — Chrome popup display fix

This is a targeted fix for v3.8.2 opening as a thin vertical scrollbar with no visible controls.

## Root cause and change

Chrome action popups are intrinsically sized. v3.8.2 used `body { width:555px; max-width:100% }` with no definite width on `html`, and later `html,body {overflow-x:hidden}`. The popup can start at a tiny width, at which point the `100%` cap feeds the tiny viewport back into the body size. The only visible piece is a scrollbar. Earlier browser UI tests forced 555px viewports and did not test popup intrinsic sizing.

v3.8.3 sets explicit, fixed 540px intrinsic widths for both html and body, including at small initial viewport sizes. It bounds long text and keeps previous UI/application functions unchanged.

## Installation

1. Go to `chrome://extensions/`, disable the previous Smart Report extension.
2. Extract this ZIP and load `Smart-Report-v3.8.3-Popup-Display-Fix` using **Load unpacked**.
3. If you wish to update in place, replace the files in the folder you already loaded, then press **Reload** on that extension's card.
4. Reopen Smart Report. You should see the full header and login/dashboard, not just a thin scrollbar.
5. Try both Google-only and Outlook-only, and one test email each before scheduling.

Use **only one enabled copy** of the extension for testing to avoid duplicate scheduler triggers. The Microsoft extension key/public identity, OAuth configuration, sending/capture scripts, and policies are preserved.

## Testing

Static JS checks, ZIP integrity, popup sizing with a synthetic 1px-initial-width environment, and existing offline regression/UI tests were run. Real action-popup behavior must still be confirmed in your Chrome installation.
