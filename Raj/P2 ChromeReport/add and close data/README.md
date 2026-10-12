# Weekly Add/Closed Network Files

Place one add/closed-network `.xlsx` workbook here for every reporting week.

Expected columns are `TRANSMISSION`, `STATE`, `MARKET`, `CITY`, `NETWORK`, `CRN NO`, and `REMARKS`. The week may be written in the filename (recommended) or near the top of the `Networks Details` sheet.

The dashboard matches rows by `CRN NO` first and by transmission/market/city/network second. Closure-style remarks such as `CLOSURE`, `CLOSED`, `DELETION`, `REMOVAL`, `OFF`, or `DISCONTINUED` mark the whole head-end as closed. If a tracked channel changes from a value to `NA` and the weekly file has no matching closure, the frequency report labels that channel as closed at an available head-end.
