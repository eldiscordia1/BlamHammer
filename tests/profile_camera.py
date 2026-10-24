"""Opt-in camera profiling against installed production BSPs."""
import cProfile
import io
import json
from pathlib import Path
import pstats
import sys
import time
from PySide6.QtCore import Qt,QPoint,QTimer
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from blamhammer.app import Editor,ROOT
from blamhammer.bsp import import_bsp
from blamhammer.toolchain import detect_hek
from blamhammer.viewports import OrthoView,PerspectiveView

samples={}
def measure(cls,name):
    original=getattr(cls,name)
    def wrapped(self,*args):
        start=time.perf_counter()
        try:return original(self,*args)
        finally:samples.setdefault(cls.__name__+'.'+name,[]).append(time.perf_counter()-start)
    setattr(cls,name,wrapped)

for cls,name in ((OrthoView,'paintEvent'),(PerspectiveView,'paintGL'),(PerspectiveView,'prepare_batches'),
                 (PerspectiveView,'build_geometry'),(PerspectiveView,'prepare_selection'),
                 (PerspectiveView,'invalidate_cache'),(PerspectiveView,'pick'),(Editor,'load_visible_previews'),
                 (Editor,'refresh'),(Editor,'refresh_properties')):
    measure(cls,name)
fmt=QSurfaceFormat();fmt.setVersion(2,1);fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
fmt.setDepthBufferSize(24);QSurfaceFormat.setDefaultFormat(fmt)
app=QApplication([]);name=sys.argv[1] if len(sys.argv)>1 else 'bloodgulch'
hek=detect_hek();source=Path(hek)/f'tags/levels/test/{name}/{name}.scenario_structure_bsp'
project=import_bsp(source,hek)
print('IMPORTED',name,sum(len(b.faces) for b in project.brushes),'faces',flush=True)
w=Editor(project);w.show();QTest.qWait(1200);w.frame_all();QTest.qWait(500)
v=w.perspective;v.setFocus();QTest.qWait(200);samples.clear()
cached_geometry=v._geometry;cached_batches=v.batches
original_project=w.project.to_dict();original_history=len(w.history.undo_stack)
heartbeats=[];watch=QTimer();watch.setInterval(10);watch.timeout.connect(lambda:heartbeats.append(time.perf_counter()));watch.start()
profiler=cProfile.Profile();profiler.enable()
pos=QPoint(v.width()//2,v.height()//2)
QTest.mouseClick(v,Qt.MouseButton.LeftButton,pos=pos);QTest.qWait(50)
QTest.keyPress(v,Qt.Key.Key_W);QTest.qWait(1200);QTest.keyRelease(v,Qt.Key.Key_W)
QTest.mousePress(v,Qt.MouseButton.RightButton,pos=pos)
for i in range(18):
    QTest.mouseMove(v,pos+QPoint(i*2,i%3));QTest.qWait(20)
QTest.mouseRelease(v,Qt.MouseButton.RightButton,pos=pos+QPoint(34,2))
profiler.disable();watch.stop()
assert v._geometry is cached_geometry and v.batches is cached_batches,'Camera/selection rebuilt map geometry'
assert not samples.get('PerspectiveView.prepare_batches') and not samples.get('PerspectiveView.build_geometry')
assert not v.move_keys and not v.move_timer.isActive()
assert w.project.to_dict()==original_project and len(w.history.undo_stack)==original_history
assert not v.render_error,v.render_error
summary={k:{'calls':len(v),'total_ms':round(sum(v)*1000,2),'max_ms':round(max(v)*1000,2)} for k,v in samples.items()}
summary['max_event_gap_ms']=round(max((b-a for a,b in zip(heartbeats,heartbeats[1:])),default=0)*1000,2)
summary['render_error']=v.render_error
ROOT.joinpath('artifacts').mkdir(exist_ok=True)
output=io.StringIO();pstats.Stats(profiler,stream=output).sort_stats('cumulative').print_stats(25)
ROOT.joinpath('artifacts',f'camera_profile_{name}.txt').write_text(output.getvalue(),encoding='utf-8')
ROOT.joinpath('artifacts',f'camera_profile_{name}.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2),flush=True);print(output.getvalue(),flush=True)
w.saved_state=w.project.to_dict();w.close()
