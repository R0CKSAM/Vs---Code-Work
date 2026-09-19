import os
from pathlib import Path
import subprocess
import sys

env = {k: v for k, v in os.environ.items() if not k.startswith(('GST_', 'GI_', 'PYGI_'))}
env['PYTHONPATH'] = r'D:\Veto OTT\python_packages'
code = '''
import sys, os
sys.path.insert(0, r'D:\\Veto OTT')
print('import core', flush=True)
import scoreboard_app as core
print('core ready', flush=True)
print('pango', bool(core._load_pango_modules()), flush=True)
import gi
gi.require_version('Gst','1.0')
print('gi ready', flush=True)
if len(sys.argv)>1:
    os.environ['GST_PLUGIN_PATH_1_0']=''
    os.environ['GST_PLUGIN_SYSTEM_PATH_1_0']=''
    os.environ['GST_REGISTRY_1_0']=r'D:\\Veto Live\\.dropdown-fix\\isolated-registry.bin'
    os.environ['GST_REGISTRY_FORK']='no'
from gi.repository import Gst
Gst.init(None)
print('gst ready', flush=True)
if len(sys.argv)>1:
    Gst.Plugin.load_file(r'D:\\Veto OTT\\python_packages\\gstreamer_plugins\\lib\\gstreamer-1.0\\gstdecklink.dll')
    print('decklink loaded', flush=True)
m=Gst.DeviceMonitor.new()
m.add_filter('Video/Sink',None)
print('starting monitor', flush=True)
print('monitor',m.start(), flush=True)
for d in m.get_devices():
    print('DEVICE',d.get_display_name(),d.get_properties().to_string(),d.get_caps().to_string(),flush=True)
m.stop()
'''
proc = subprocess.Popen([sys.executable, '-u', '-c', code, *sys.argv[1:]], env=env,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NO_WINDOW)
try:
    out, _ = proc.communicate(timeout=20)
    print(out.decode(errors='replace'))
    print('exit', proc.returncode)
except subprocess.TimeoutExpired:
    subprocess.run(['taskkill.exe', '/PID', str(proc.pid), '/T', '/F'], capture_output=True)
    out, _ = proc.communicate(timeout=5)
    print(out.decode(errors='replace'))
    print('timed out')
