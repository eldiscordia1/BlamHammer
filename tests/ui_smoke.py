"""Exercise real Qt widgets and OpenGL; save screenshots for visual review."""
from pathlib import Path
import sys
import tempfile
import numpy as np
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from blamhammer.app import Editor,ROOT
from blamhammer.model import Project,load,save
from blamhammer.geometry import bounds,primitive,validate_brush,to_manifold

fmt=QSurfaceFormat();fmt.setVersion(2,1);fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
fmt.setDepthBufferSize(24);QSurfaceFormat.setDefaultFormat(fmt)
app=QApplication([]);app.setStyle('Fusion')
w=Editor(load(ROOT/'examples/test_room.hceproj'));w.show()
errors=[];w.error=lambda message:errors.append(message)
QTest.qWait(1000);w.frame_all();QTest.qWait(700)
assert w.perspective.isValid(),'OpenGL context failed'
assert not w.perspective.render_error,w.perspective.render_error
initial=w.project.to_dict()
w.active_material=w.project.brushes[1].faces[0].material
w.set_tool('draw');w.shape.setCurrentText('Box')
before=len(w.project.brushes)
start=w.top.project([400,650,0]).toPoint();end=w.top.project([600,850,0]).toPoint()
QTest.mousePress(w.top,Qt.MouseButton.LeftButton,pos=start)
QTest.mouseMove(w.top,end,100)
QTest.mouseRelease(w.top,Qt.MouseButton.LeftButton,pos=end)
assert len(w.project.brushes)==before+1,'2D draw failed'
created=w.selected_brush();assert created is not None
w.set_tool('select')
old=np.asarray(created.vertices).copy()
lo,hi=bounds(created);pos=w.top.project((lo+hi)/2).toPoint()
QTest.mousePress(w.top,Qt.MouseButton.LeftButton,pos=pos)
QTest.mouseMove(w.top,pos+QPoint(40,20),100)
QTest.mouseRelease(w.top,Qt.MouseButton.LeftButton,pos=pos+QPoint(40,20))
assert not np.array_equal(old,w.selected_brush().vertices),'2D move failed'
w.duplicate();assert len(w.project.brushes)==before+2
w.undo();assert len(w.project.brushes)==before+1
w.redo();assert len(w.project.brushes)==before+2
w.delete_selection();assert len(w.project.brushes)==before+1
with tempfile.TemporaryDirectory() as folder:
    p=Path(folder)/'ui.hceproj';save(w.project,p)
    assert load(p).to_dict()==w.project.to_dict()
w.replace_project(load(ROOT/'examples/test_room.hceproj'))
w.select_face(w.project.brushes[1].id,0)
other=w.project.brushes[0].faces[0].material
w.active_material=other;w.apply_material()
assert w.project.brushes[1].faces[0].material==other
w.uv_scale[0].setValue(125);w.apply_uv();assert w.project.brushes[1].faces[0].scale[0]==125
w.undo();w.undo()
assert not errors,errors

# Drive the actual subdivision button, cross-view vertex drag, and clip-mode combo.
material=w.project.brushes[1].faces[0].material
fixture=Project(brushes=[primitive('room',(0,0,400),(1600,1600,800),material),
                         primitive('box',(0,0,100),(400,400,200),material)],hek=w.project.hek)
w.replace_project(fixture);w.select(w.project.brushes[1].id);w.faces.setCurrentIndex(2)
w.subdivisions.setValue(4);base=w.project.to_dict()
QTest.mouseClick(w.subdivide_button,Qt.MouseButton.LeftButton);QTest.qWait(100)
assert not errors,errors
assert w.tool=='vertex'
terrain=w.selected_brush();assert len(terrain.faces)==37 and len(terrain.vertices)==29
assert len(w.perspective.selected_lines)==2*sum(len(f.indices) for f in terrain.faces),'Wireframe must show face boundaries'
subdivided=w.project.to_dict();w.undo();assert w.project.to_dict()==base
w.redo();assert w.project.to_dict()==subdivided
# Triangulating a stitched neighbor must also preserve the closed brush.
terrain=w.selected_brush();w.select_face(terrain.id,33);w.triangulate()
assert not errors,errors
assert len(w.selected_brush().faces)==41
validate_brush(w.selected_brush());w.undo();assert w.project.to_dict()==subdivided
terrain=w.selected_brush();w.select(terrain.id)
w.frame_all()
center=next(i for i,p in enumerate(terrain.vertices) if p==[0,0,200])
pos=w.top.project([0,0,200]).toPoint()
QTest.mouseClick(w.top,Qt.MouseButton.LeftButton,pos=pos)
assert w.component==[center],'Interior vertex selection failed'
pos=w.front.project([0,0,200]).toPoint()
QTest.mousePress(w.front,Qt.MouseButton.LeftButton,pos=pos)
QTest.mouseMove(w.front,pos+QPoint(0,-13),100)
QTest.mouseRelease(w.front,Qt.MouseButton.LeftButton,pos=pos+QPoint(0,-13))
assert not errors,errors
terrain=w.selected_brush();height=terrain.vertices[center][2]
assert height>200 and (height-200)%25==0,'Vertex drag did not snap'
validate_brush(terrain)
deformed=w.project.to_dict();w.undo();assert w.project.to_dict()==subdivided
w.redo();assert w.project.to_dict()==deformed
for mode in ('left','right','both'):
    w.replace_project(Project.from_dict(deformed));w.select(w.project.brushes[1].id)
    w.set_tool('clip');w.clip_mode.setCurrentIndex(w.clip_mode.findData(mode))
    before=w.project.to_dict()
    start=w.top.project([12,-300,0]).toPoint();end=w.top.project([12,300,0]).toPoint()
    QTest.mousePress(w.top,Qt.MouseButton.LeftButton,pos=start)
    QTest.mouseMove(w.top,end,100)
    QTest.mouseRelease(w.top,Qt.MouseButton.LeftButton,pos=end)
    assert not errors,errors
    parts=[b for b in w.project.brushes if b.kind=='solid']
    assert len(parts)==(2 if mode=='both' else 1)
    for b in parts:validate_brush(b)
    if mode=='left':assert max(p[0] for p in parts[0].vertices)==0
    if mode=='right':assert min(p[0] for p in parts[0].vertices)==0
    if mode=='both':assert len(w.selection)==2 and parts[0].id!=parts[1].id
    cut=w.project.to_dict();w.undo();assert w.project.to_dict()==before
    w.redo();assert w.project.to_dict()==cut
with tempfile.TemporaryDirectory() as folder:
    path=Path(folder)/'features.hceproj';save(w.project,path);assert load(path).to_dict()==cut
before=w.project.to_dict();w.select(w.project.brushes[1].id)
start=w.top.project([600,-300,0]).toPoint();end=w.top.project([600,300,0]).toPoint()
QTest.mousePress(w.top,Qt.MouseButton.LeftButton,pos=start)
QTest.mouseRelease(w.top,Qt.MouseButton.LeftButton,pos=end)
assert errors and 'cuts through' in errors.pop()
assert w.project.to_dict()==before,'Rejected cut changed the project'
assert not errors,errors
w.set_tool('vertex');w.frame_all();QTest.qWait(400)
ROOT.joinpath('artifacts').mkdir(exist_ok=True)
assert w.grab().save(str(ROOT/'artifacts/features_editor.png'))
w.replace_project(load(ROOT/'examples/test_room.hceproj'))
w.select(w.project.brushes[1].id);w.set_tool('select')
w.search.setText('example_tutorial');QTest.qWait(1200)
ROOT.joinpath('artifacts').mkdir(exist_ok=True)
assert w.grab().save(str(ROOT/'artifacts/editor.png'))
assert w.perspective.grabFramebuffer().save(str(ROOT/'artifacts/viewport.png'))
assert not w.perspective.render_error,w.perspective.render_error
w.saved_state=w.project.to_dict();w.close()
print('UI PASS: OpenGL, draw/move, duplicate/delete, materials/UVs, subdivision, cross-view vertex snapping, all clip modes, caps, undo/redo, rejected-cut rollback, save/reload. Screenshots saved.')
