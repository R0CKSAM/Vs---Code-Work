/* Grafana source panel sequence, verified against source dashboard export. */
export const SECTIONS = [
  {
    "key": "session",
    "title": "Session and Users Stats",
    "style": "stats",
    "panels": [
      {
        "report": "kpis",
        "field": "unique_devices",
        "name": "Total Users ( Based on Device ID - APP DATA)",
        "note": "Distinct device IDs per day",
        "panel": 2,
        "icon": "users"
      },
      {
        "report": "kpis",
        "field": "session_ids",
        "name": "Total Sessions (Based on Session ID in query String - APP DATA)",
        "note": "Distinct session IDs per day",
        "panel": 1,
        "icon": "session"
      },
      {
        "report": "kpis",
        "field": "unique_ips",
        "name": "Total Users  (Based on Uniq IP)",
        "note": "Unique IP addresses per day",
        "panel": 8,
        "icon": "users"
      },
      {
        "report": "kpis",
        "field": "new_users",
        "name": "Total New Users ( Based on Device ID - APP DATA)",
        "note": "One distinct session ID per device in the day",
        "panel": 6,
        "icon": "users"
      },
      {
        "report": "kpis",
        "field": "returning_users",
        "name": "Total Returning Users ( Based on Device ID - APP DATA)",
        "note": "More than one distinct session ID per device in the day",
        "panel": 7,
        "icon": "users"
      },
      {
        "report": "kpis",
        "field": "ip_ua_sessions",
        "name": "Total Sessions  (Based on Uniq IP & UA)",
        "note": "Unique IP + User Agent pairs per day",
        "panel": 12,
        "icon": "session"
      },
      {
        "report": "kpis",
        "field": "manifest_views",
        "name": "Total Views (Total Master Manifest Requests)",
        "note": "Master manifest requests",
        "panel": 5,
        "icon": "eye"
      },
      {
        "report": "kpis",
        "field": "session_hours",
        "name": "Total Session Duration (Hours)",
        "note": "Estimated duration in hours",
        "panel": 41,
        "icon": "clock"
      },
      {
        "report": "kpis",
        "field": "avg_watch_minutes_per_user",
        "name": "Avg Watch Time per user (Based on Unique IP)",
        "note": "Estimated minutes per unique IP",
        "panel": 49,
        "icon": "clock"
      },
      {
        "report": "kpis",
        "fields": [
          "unique_ips",
          "ip_ua_sessions"
        ],
        "name": "Total Unique IPs & Session",
        "note": "Both Grafana table columns exported together",
        "panel": 11,
        "icon": "session",
        "composite": true,
        "compositeColumns": [
          [
            "unique_ips",
            "unique_cliIP"
          ],
          [
            "ip_ua_sessions",
            "unique_session"
          ]
        ]
      }
    ]
  },
  {
    "key": "device-series",
    "title": "Total Users ( Based on Device ID - APP DATA) - Time Series",
    "style": "series",
    "description": "Choose Per Minute or Per 5 Minute; each downloads separately.",
    "panels": [
      {
        "report": "ts_device_1m",
        "field": "value",
        "name": "Total Users ( Based on Device ID - APP DATA) - Per Minute",
        "note": "Device ID · one-minute source panel",
        "panel": 4,
        "icon": "trend"
      },
      {
        "report": "ts_device_5m",
        "field": "value",
        "name": "Total Users - Summation ( Based on Device ID - APP DATA) - Per 5 Minute",
        "note": "Device ID · original cumulative five-minute calculation",
        "panel": 67,
        "icon": "trend"
      }
    ]
  },
  {
    "key": "session-series",
    "title": "Total Sessions (Based on Session ID in query String - APP DATA) - Time Series",
    "style": "series",
    "description": "Choose Per Minute or Per 5 Minute; each downloads separately.",
    "panels": [
      {
        "report": "ts_session_1m",
        "field": "value",
        "name": "Total Sessions (Based on Session ID in query String - APP DATA) - Per Minute",
        "note": "Session ID · one-minute source panel",
        "panel": 39,
        "icon": "trend"
      },
      {
        "report": "ts_session_5m",
        "field": "value",
        "name": "Total Sessions (Based on Session ID in query String - APP DATA) - Per 5 Minute",
        "note": "Session ID · original cumulative five-minute calculation",
        "panel": 69,
        "icon": "trend"
      }
    ]
  },
  {
    "key": "views-series",
    "title": "Total Views (Total Master Manifest Requests) - Time Series",
    "style": "series",
    "description": "Choose Per Minute or Per 5 Minute; each downloads separately.",
    "panels": [
      {
        "report": "ts_views_1m",
        "field": "value",
        "name": "Total Views (Total Master Manifest Requests) - Per Minute",
        "note": "Views · one-minute source panel",
        "panel": 3,
        "icon": "trend"
      },
      {
        "report": "ts_views_5m",
        "field": "value",
        "name": "Total Views (Total Master Manifest Requests) - Per 5 Minute",
        "note": "Views · original cumulative five-minute calculation",
        "panel": 70,
        "icon": "trend"
      }
    ]
  },
  {
    "key": "ip-series",
    "title": "Total Users (Based on Uniq IP) - Time Series",
    "style": "series",
    "description": "Choose Per Minute or Per 5 Minute; each downloads separately.",
    "panels": [
      {
        "report": "ts_ip_1m",
        "field": "value",
        "name": "Total Users  (Based on Uniq IP) - Per Minute",
        "note": "Unique IP · one-minute source panel",
        "panel": 9,
        "icon": "trend"
      },
      {
        "report": "ts_ip_5m",
        "field": "value",
        "name": "Total Users  (Based on Uniq IP) - Per 5 Minute",
        "note": "Unique IP · original cumulative five-minute calculation",
        "panel": 71,
        "icon": "trend"
      }
    ]
  },
  {
    "key": "ipua-series",
    "title": "Total Sessions (Based on Uniq IP & UA) - Time Series",
    "style": "series",
    "description": "Choose Per Minute or Per 5 Minute; each downloads separately.",
    "panels": [
      {
        "report": "ts_ipua_1m",
        "field": "value",
        "name": "Total Sessions  (Based on Uniq IP & UA) - Per Minute",
        "note": "IP + User Agent · one-minute source panel",
        "panel": 38,
        "icon": "trend"
      },
      {
        "report": "ts_ipua_5m",
        "field": "value",
        "name": "Total Sessions  (Based on Uniq IP & UA) - Per 5 Minute",
        "note": "IP + User Agent · original cumulative five-minute calculation",
        "panel": 72,
        "icon": "trend"
      }
    ]
  },
  {
    "key": "viewership",
    "title": "Viewership Trend",
    "style": "viewership",
    "panels": [
      {
        "report": "viewership_stats",
        "field": "viewership_hours",
        "name": "Total Viewership (Hours)",
        "note": "Estimated segment-hours in each day",
        "panel": 13,
        "icon": "clock"
      },
      {
        "report": "viewership_stats",
        "field": "avg_watch_minutes",
        "name": "Avg Watch Time/User",
        "note": "Estimated minutes per unique IP",
        "panel": 22,
        "icon": "clock"
      },
      {
        "report": "viewership_stats",
        "field": "total_segments",
        "name": "Total Segments Played",
        "note": "Matching six-second TS segments",
        "panel": 14,
        "icon": "session"
      },
      {
        "report": "viewership_stats",
        "field": "bandwidth_bytes",
        "name": "Total Bandwidth (Video)",
        "note": "Successful video response bytes",
        "panel": 15,
        "icon": "stream"
      },
      {
        "report": "viewership_minute",
        "field": "value",
        "name": "Viewership minutes",
        "note": "Estimated playtime in minute buckets",
        "panel": 17,
        "icon": "trend",
        "layout": "wide-chart"
      },
      {
        "report": "channel",
        "field": "playtime_minutes",
        "name": "Playtime by Channel",
        "note": "Per-channel daily grouped export",
        "panel": 34,
        "icon": "channel",
        "layout": "wide-chart"
      },
      {
        "report": "channel",
        "field": "unique_ips",
        "name": "Total Users (Based on Uniq IP)",
        "note": "Per-channel daily unique-IP export",
        "panel": 68,
        "icon": "users",
        "layout": "wide-chart"
      },
      {
        "report": "content",
        "fields": [
          "unique_ips",
          "unique_devices",
          "session_ids",
          "manifest_views"
        ],
        "name": "Popular Content",
        "note": "Date, content title, IP/device users, session IDs and views",
        "panel": 27,
        "icon": "channel",
        "layout": "wide-table",
        "composite": true,
        "compositeColumns": [
          [
            "unique_ips",
            "Users (Based on Uniq IP)"
          ],
          [
            "unique_devices",
            "Users (Based on Device ID - APP DATA)"
          ],
          [
            "session_ids",
            "Total Sessions (Session ID)"
          ],
          [
            "manifest_views",
            "views"
          ]
        ]
      }
    ]
  },
  {
    "key": "playtime",
    "title": "Playtime",
    "style": "playtime",
    "panels": [
      {
        "report": "geo",
        "field": "playtime_minutes",
        "name": "Playtime by GEO",
        "note": "Country · State · City · Estimated minutes",
        "panel": 20,
        "icon": "map"
      },
      {
        "report": "platform_devices",
        "field": "unique_devices",
        "name": "Total Device ID by Platform",
        "note": "Grouped by device platform",
        "panel": 58,
        "icon": "device"
      },
      {
        "report": "os_devices",
        "field": "unique_devices",
        "name": "Total Device ID by OS",
        "note": "Grouped by operating system",
        "panel": 55,
        "icon": "device"
      }
    ]
  },
  {
    "key": "playtime-ip",
    "title": "Playtime - IP",
    "style": "playtime-ip",
    "panels": [
      {
        "report": "geo_ips",
        "field": "unique_ips",
        "name": "Unique Client IP by Geo",
        "note": "Country · State · City · Unique IPs",
        "panel": 53,
        "icon": "map"
      },
      {
        "report": "platform_ips",
        "field": "unique_ips",
        "name": "IP by Platform(sessions)",
        "note": "Source panel groups unique IPs by platform",
        "panel": 33,
        "icon": "device"
      },
      {
        "report": "os_ips",
        "field": "unique_ips",
        "name": "IP by OS(sessions)",
        "note": "Source panel groups unique IPs by OS",
        "panel": 37,
        "icon": "device"
      }
    ]
  }
];
