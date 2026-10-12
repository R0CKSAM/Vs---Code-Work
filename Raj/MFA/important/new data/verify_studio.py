"""
Standalone Senior Developer Verification and Quality Audit Runner.
Executes the comprehensive test suite for davis_cup_generator.py.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import davis_cup_generator
    success = davis_cup_generator.run_senior_developer_audit()
    sys.exit(0 if success else 1)
except Exception as e:
    print(f"\n[ERROR] Audit encountered an exception: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
