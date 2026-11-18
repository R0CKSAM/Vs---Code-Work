"""Open/reuse the local explorer without a console window."""
from pathlib import Path
import ctypes,json,subprocess,time,urllib.request,webbrowser
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];URL='http://127.0.0.1:8768'
def ready():
    try:
        with urllib.request.urlopen(URL+'/health',timeout=2) as r:return json.load(r).get('application')=='veto-identity-explorer'
    except Exception:return False
try:
    if not ready():
        folder=ROOT/'Reports/Sports_Identity_Explorer_20261118';folder.mkdir(parents=True,exist_ok=True)
        with (folder/'server.log').open('a',encoding='utf-8') as log:
            subprocess.Popen([str(ROOT/'venv/Scripts/python.exe'),'-u',str(HERE/'server.py')],cwd=str(ROOT),stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(75):
            if ready():break
            time.sleep(1)
        else:raise RuntimeError('The snapshot is still building or the server could not start. Check Reports/Sports_Identity_Explorer_20261118/server.log and open the shortcut again.')
    webbrowser.open(URL)
except Exception as e:ctypes.windll.user32.MessageBoxW(0,str(e),'Veto Identity Explorer',0x10)
