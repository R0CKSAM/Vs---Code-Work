"""Render a self-contained interactive report plus shareable PNG/SVG charts."""
from pathlib import Path
import argparse, json, html
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def render(folder):
    folder = Path(folder)
    data = json.loads((folder / 'analysis.json').read_text())
    days = data['days']
    colors = ['#008b66', '#4065da', '#bd591c']
    fig, axes = plt.subplots(3, 1, figsize=(15, 12), constrained_layout=True)
    fig.suptitle(f"Client IP request activity | {days[0]} to {days[-1]} IST\n{data['ip']}", fontsize=17, fontweight='bold')
    for day, color in zip(days, colors):
        rows = {r['hour']: r['requests'] for r in data['hourly'] if r['day'] == day}
        axes[0].plot(range(24), [rows.get(h, 0) for h in range(24)], label=day, color=color, marker='.', linewidth=2)
    axes[0].set(title='Daily overlay: all feed requests by hour', ylabel='Requests / hour', xlabel='Hour of day (IST)', xticks=range(0, 24, 2))
    axes[0].legend(ncol=3)
    totals = {}
    for r in data['feed_daily']:
        key = (r['source'], r['reqHost'], r['candidate'])
        totals[key] = totals.get(key, 0) + r['requests']
    top = sorted(totals, key=totals.get, reverse=True)[:6]
    for key in top:
        rows = [r for r in data['feed_hourly'] if (r['source'], r['reqHost'], r['candidate']) == key]
        indexed = {(r['day'], r['hour']): r['requests'] for r in rows}
        axes[1].plot(range(72), [indexed.get((day, h), 0) for day in days for h in range(24)], label=rows[0]['feed'], linewidth=1.6)
    axes[1].set(title='Content/feed activity: top six by total requests', ylabel='Requests / hour', xticks=[0, 12, 24, 36, 48, 60, 71], xticklabels=[days[0]+' 00h', '12h', days[1]+' 00h', '12h', days[2]+' 00h', '12h', '23h'])
    axes[1].legend(fontsize=8, ncol=3, loc='upper center', bbox_to_anchor=(.5, -.16))
    rows = data['overlap_minutes']
    axes[2].plot(range(len(rows)), [r['active_feeds'] for r in rows], label='Any request', linewidth=.8, color='#4065da')
    axes[2].plot(range(len(rows)), [r['successful_ts_feeds'] for r in rows], label='Successful non-empty TS requests', linewidth=.8, color='#008b66')
    axes[2].set(title='Feeds requested within the same minute (not concurrent human viewers)', ylabel='Distinct host + feed candidates', xlabel='Consecutive active minutes, IST')
    axes[2].legend()
    for ax in axes:
        ax.grid(alpha=.18)
        ax.set_ylim(bottom=0)
        ax.spines[['top', 'right']].set_visible(False)
    fig.savefig(folder / 'request_trends.png', dpi=150, facecolor='white')
    fig.savefig(folder / 'request_trends.svg', facecolor='white')
    plt.close(fig)
    template = Path(__file__).with_name('client_ip_trend_template.html').read_text(encoding='utf-8')
    # JSON is inert script data; prevent a raw UA/host from terminating the element.
    embedded = json.dumps(data).replace('<', '\\u003c')
    (folder / 'report.html').write_text(template.replace('__REPORT_DATA__', embedded), encoding='utf-8')
    print(folder / 'report.html')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('folder')
    render(p.parse_args().folder)
