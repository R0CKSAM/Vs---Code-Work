# Smart Export v2.5 Parameter Studio

New Grafana-inspired selection workspace and original exporter retained.

Limitations: Only metrics in the certified REPORTS catalog can be selected. Changing a metric does not trigger requests; Get data calls the existing category-level report request (which currently retrieves full columns for the selected categories), and the saved workbook limits columns to selected metrics. Last 7 days means seven completed days. Today is shown as invalid for complete-day exports. Breakdown choices are only a view hint, not new backend aggregation. For non-day categories the data remains on separate sheets according to each report grain.

Keep same unpacked extension path to preserve local data. Test live Grafana with two complete days.
