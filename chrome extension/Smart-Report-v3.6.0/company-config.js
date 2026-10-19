// Company Edition public identifiers. NOT secrets.
// Replace these two values with the IDs from your existing Entra application.
const COMPANY_MICROSOFT = Object.freeze({
  clientId: "00ad226c-9ab3-42d0-add9-1d5d8964f41b",
  tenantId: "c6ac1249-3f6f-4a68-989a-f100bd6bda03"
});

// Company policy for outgoing reports.
//  allowedRecipientDomains: e.g. ["yourcompany.com"]. Recipients (To, CC and BCC) outside these domains
//                           are rejected. An EMPTY list limits recipients to the signed-in Outlook account domain.
//  To permit other company domains, add them explicitly above.
//  maxRecipients:           cap on To + CC + BCC.
//  requirePanels:           refuse to send a screenshot when no Grafana panels are detected on the page.
//                           Set to false only if your Grafana version uses different panel markup
//                           and every capture is being rejected with "No Grafana panels found".
const COMPANY_POLICY = Object.freeze({
  allowedRecipientDomains: ["vetostreaming.com", "indiatvnews.com"],
  maxRecipients: 50,
  requirePanels: true
});


// Grafana capture defaults for company dashboards.
// defaultFrom/defaultTo: applied when the saved dashboard URL has no time range.
// defaultRefresh: applied when the saved dashboard URL has no refresh parameter.
// forceReloadBeforeCapture: false keeps the current open dashboard state instead of reloading every run.
// captureFullPage: true captures the full dashboard vertically instead of only the visible viewport.
const COMPANY_GRAFANA_DEFAULTS = Object.freeze({
  defaultFrom: "now/d",
  defaultTo: "now",
  defaultRefresh: "1m",
  forceReloadBeforeCapture: false,
  captureFullPage: true
});
