"""Start the local H1A runtime, capture only its window, then close our process."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import subprocess
import sys
import time
from PIL import ImageGrab
from blamhammer.toolchain import detect_hek
from blamhammer.model import tag_path

root=Path(detect_hek())
output=Path(__file__).resolve().parent.parent/'artifacts'
output.mkdir(exist_ok=True)
script=output/'standalone_init.txt'
scenario=tag_path(sys.argv[1] if len(sys.argv)>1 else 'levels\\blamhammer\\blamhammer_demo\\blamhammer_demo')
script.write_text('game_variant slayer\nmap_name '+scenario+'\n')
process=subprocess.Popen([str(root/'halo_tag_test.exe'),'-window','-vidmode','1024,640','-nosound','-nojoystick','-exec',str(script)],cwd=root)
try:
    time.sleep(10)
    assert process.poll() is None,'Standalone exited unexpectedly.'
    user32=ctypes.windll.user32
    handles=[]
    callback=ctypes.WINFUNCTYPE(ctypes.c_bool,wintypes.HWND,wintypes.LPARAM)
    @callback
    def visit(hwnd,param):
        pid=wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        if pid.value==process.pid and user32.IsWindowVisible(hwnd):handles.append(hwnd)
        return True
    user32.EnumWindows(visit,0)
    assert handles,'No standalone window.'
    image=ImageGrab.grab(window=handles[0])
    screenshot=output/(scenario.split('\\')[-1]+'_in_game.png')
    image.save(screenshot)
    print(f'Captured local Halo runtime: {screenshot}. Window capture alone does not prove gameplay.')
finally:
    process.terminate()
    process.wait(timeout=10)
