"""Reusable insight configurations served by the application."""

INSIGHT_PRESETS = [
    {'id': 'insight-views', 'name': 'Daily views vs total revenue', 'config': {'type': 'mixed', 'group': 'day', 'first': 'views', 'second': 'total'}},
    {'id': 'insight-leader', 'name': 'Highest-revenue channel each day', 'config': {'type': 'bar', 'group': 'leader', 'first': 'total', 'second': 'none'}},
    {'id': 'insight-mix', 'name': 'Daily ad revenue vs sponsorship', 'config': {'type': 'grouped', 'group': 'day', 'first': 'ad', 'second': 'other'}},
    {'id': 'insight-share', 'name': 'Channel revenue share', 'config': {'type': 'pie', 'group': 'channel', 'first': 'total', 'second': 'none'}},
]
