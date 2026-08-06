from app import load_report, write_frequency_report_json, write_standalone_dashboard
from landing_channel_tracker import process_landing_tracker_files

if __name__ == "__main__":
    print("Rebuilding landing tracker history CSV...")
    res = process_landing_tracker_files(force_reprocess=True)
    print(f"Imported {res.get('total_records', 0):,} records.")

    print("Rebuilding dashboard bundle and HTML...")
    report = load_report(force=True)
    write_frequency_report_json(report)
    write_standalone_dashboard(report)
    print("Dashboard rebuilt successfully!")
