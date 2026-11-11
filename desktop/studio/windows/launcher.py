"""Portable Windows launcher. No Python installation or administrator access required."""
import argparse
import json
import logging
import os
from pathlib import Path
import sys
import threading
import time

ENGINE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ENGINE))
os.environ['PYTHONUTF8']='1';os.environ['PYTHONIOENCODING']='utf-8'
os.environ['PATH']=str(ENGINE/'import-tools')+os.pathsep+os.environ.get('PATH','')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--smoke',type=Path);parser.add_argument('--gui-smoke',type=Path);args=parser.parse_args()
    if args.smoke:
        from windows.smoke import smoke
        smoke(ENGINE,args.smoke);return
    import diagnostics
    diagnostics.install_hooks();diagnostics.event("startup",**diagnostics.summary())
    from windows.startup import unblock_bundled_libraries, load_clr
    if os.name == 'nt':
        preparation = unblock_bundled_libraries(ENGINE)
        diagnostics.event('startup.libraries', **preparation)
        print('Préparation des bibliothèques Windows : '+json.dumps(preparation), flush=True)
        load_clr()
        from importlib.metadata import version
        diagnostics.event('startup.clr', pythonnet=version('pythonnet'), clr_loader=version('clr-loader'))
    import webview
    from windows.host import Api
    logroot=diagnostics.directory();logroot.mkdir(parents=True,exist_ok=True)
    from logging.handlers import RotatingFileHandler
    logging.basicConfig(handlers=[RotatingFileHandler(logroot/'webview.log',maxBytes=1_000_000,backupCount=2,encoding='utf-8')],level=logging.INFO)
    api=Api(ENGINE,logroot/'UITestProjects' if args.gui_smoke else None)
    window=webview.create_window('BandStudio · Préparation pour REAPER',str(ENGINE/'web/index.html'),js_api=api,width=1360,height=900,min_size=(960,660),background_color='#0b1121')
    api._window=window
    if not args.gui_smoke:window.events.loaded+=api._loaded
    window.events.closing+=api._closing
    threading.Thread(target=api._pulse,daemon=True).start()
    if args.gui_smoke:
        def check():
            try:
                result=None
                for _ in range(100):
                    result=window.evaluate_js('({title:document.title,bridge:typeof window.pywebview?.api?.command,sections:document.querySelectorAll(".view").length})')
                    if result and result.get('bridge')=='function':break
                    time.sleep(.1)
                if result['title']!='BandStudio' or result['bridge']!='function' or result['sections']<5:raise RuntimeError(str(result))
                api._notice="Interface Windows connectée"
                window.evaluate_js("send('ready')")
                for _ in range(100):
                    result['ready']=window.evaluate_js("document.querySelector('#notice').textContent === 'Interface Windows connectée'")
                    if result['ready']:break
                    time.sleep(.1)
                assert result['ready']
                args.gui_smoke.write_text(json.dumps(result),encoding='utf-8')
            finally:window.destroy()
        window.events.loaded+=check
    webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER']=True
    webview.start(gui='edgechromium',debug=False,private_mode=True)


if __name__=='__main__':
    try:main()
    except Exception as error:
        import diagnostics
        diagnostics.event('startup.failed', kind=type(error).__name__, error=error)
        import traceback
        traceback.print_exc();sys.exit(1)
