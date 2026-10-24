"""Real Qt mouse/keyboard checks for face selection and the 3D camera."""
import math
import numpy as np
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from blamhammer.app import Editor,ROOT
from blamhammer.model import Project
from blamhammer.geometry import primitive,validate_brush

fmt=QSurfaceFormat();fmt.setVersion(2,1);fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
fmt.setDepthBufferSize(24);QSurfaceFormat.setDefaultFormat(fmt)
app=QApplication([])
p=Project(brushes=[primitive(center=(0,0,100),size=(400,400,200)),
                   primitive(center=(600,0,100),size=(400,400,200))])
for bi,b in enumerate(p.brushes):
    for fi,f in enumerate(b.faces):f.material=f'material_{bi}_{fi}.shader_environment'
initial=p.to_dict();first,second=[b.id for b in p.brushes]
w=Editor(p);errors=[];w.error=errors.append;w.show();QTest.qWait(500)
v=w.perspective;v.target=np.array([250.,0.,100.]);v.distance=1500;v.update()
w.set_tool('face');QTest.qWait(100)


def face_point(bid,fi):
    b=next(b for b in w.project.brushes if b.id==bid)
    center=np.asarray(b.vertices)[b.faces[fi].indices].mean(axis=0)
    eye,forward,right,up=v.camera();delta=center-eye;depth=delta@forward
    factor=math.tan(math.radians(55)/2)
    point=QPoint(round(v.width()/2*(1+(delta@right)/(depth*factor*v.width()/v.height()))),
                 round(v.height()/2*(1-(delta@up)/(depth*factor))))
    assert v.pick(point)==(bid,fi),(point,v.pick(point),(bid,fi))
    return point


def click_face(bid,fi,ctrl=False):
    QTest.mouseClick(v,Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier,
                     face_point(bid,fi))


click_face(first,1);click_face(first,2,True);click_face(second,1,True)
chosen={(first,1),(first,2),(second,1)}
assert set(w.face_selection)==chosen and len(w.selection)==2
assert len(list(w.selected_faces()))==3 and w.selected_brush().id==second
QTest.qWait(100)
ROOT.joinpath('artifacts').mkdir(exist_ok=True)
assert w.grab().save(str(ROOT/'artifacts/multiple_faces.png'))
assert not v.render_error,v.render_error
w.active_material='changed.shader_environment';w.apply_material()
for b in w.project.brushes:
    for fi,f in enumerate(b.faces):assert (f.material=='changed.shader_environment')==((b.id,fi) in chosen)
painted=w.project.to_dict();w.undo();assert w.project.to_dict()==initial
w.redo();assert w.project.to_dict()==painted
w.uv_scale[0].setValue(125);w.uv_offset[1].setValue(.5);w.uv_rotation.setValue(30);w.apply_uv()
for b in w.project.brushes:
    for fi,f in enumerate(b.faces):
        assert (f.scale[0]==125)==((b.id,fi) in chosen)
        assert (f.rotation==30)==((b.id,fi) in chosen)
w.undo();assert w.project.to_dict()==painted
click_face(first,1,True);assert set(w.face_selection)==chosen-{(first,1)}
click_face(second,2);assert w.face_selection==[(second,2)]
click_face(second,2,True);assert not w.face_selection and not w.selection
assert list(w.selected_faces())==[]
w.apply_material();assert w.project.to_dict()==painted
click_face(first,1)
blank=QPoint(3,30);assert v.pick(blank)==(None,-1)
QTest.mouseClick(v,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ControlModifier,blank)
assert w.face_selection==[(first,1)]
QTest.mouseClick(v,Qt.MouseButton.LeftButton,pos=blank);assert not w.face_selection and not w.selection

w.replace_project(Project.from_dict(initial));w.set_tool('face')
w.select_face(first,1);w.select_face(first,2,True);w.select_face(second,1,True)
w.subdivisions.setValue(2);w.subdivide_selection()
assert not errors,errors
for bi,b in enumerate(w.project.brushes):
    validate_brush(b)
    for fi in ([1,2] if bi==0 else [1]):
        assert sum(f.material==f'material_{bi}_{fi}.shader_environment' for f in b.faces)==8
assert not w.face_selection
subdivided=w.project.to_dict();w.undo();assert w.project.to_dict()==initial
w.redo();assert w.project.to_dict()==subdivided
w.select_face(second,0);w.select_face(first,0,True);w.set_tool('vertex');w.frame_all()
other_vertices=np.asarray(w.project.brushes[1].vertices).copy()
point=[0,0,200];pos=w.top.project(point).toPoint()
QTest.mouseClick(w.top,Qt.MouseButton.LeftButton,pos=pos)
pos=w.front.project(point).toPoint();end=pos+QPoint(0,-13)
QTest.mousePress(w.front,Qt.MouseButton.LeftButton,pos=pos)
QTest.mouseMove(w.front,end,60);QTest.mouseRelease(w.front,Qt.MouseButton.LeftButton,pos=end)
assert not errors,errors
assert w.project.to_dict()!=subdivided
np.testing.assert_array_equal(w.project.brushes[1].vertices,other_vertices)
w.replace_project(Project.from_dict(initial));w.select_face(first,1);w.select_face(second,2,True)
w.triangulate();assert not errors,errors
for b in w.project.brushes:
    assert len(b.faces)==7 and sum(len(f.indices)==4 for f in b.faces)==5
    validate_brush(b)
w.undo();assert w.project.to_dict()==initial
w.select(first);w.faces.setCurrentIndex(2);assert w.face_selection==[(first,1)]
w.faces.setCurrentIndex(0);assert not w.face_selection and len(list(w.selected_faces()))==6

# Camera input changes the view only, and key-up/focus loss stops movement.
w.set_tool('select');v.setFocus();QTest.qWait(50)
project=w.project.to_dict();history=len(w.history.undo_stack)
for key,basis,sign in ((Qt.Key.Key_W,1,1),(Qt.Key.Key_S,1,-1),(Qt.Key.Key_A,2,-1),(Qt.Key.Key_D,2,1)):
    before=v.camera()[0].copy();direction=v.camera()[basis]*sign
    QTest.keyPress(v,key);QTest.qWait(150);QTest.keyRelease(v,key)
    delta=v.camera()[0]-before
    assert np.linalg.norm(delta)>10 and delta@direction>10,('Wrong camera direction',key,delta)
    assert np.linalg.norm(np.cross(delta,direction))<1e-6
    stopped=v.camera()[0].copy();QTest.qWait(60);np.testing.assert_allclose(v.camera()[0],stopped)
before,forward,*_=v.camera();pos=QPoint(v.width()//2,v.height()//2)
QTest.mousePress(v,Qt.MouseButton.RightButton,pos=pos)
QTest.mouseMove(v,pos+QPoint(35,15),100)
QTest.mouseRelease(v,Qt.MouseButton.RightButton,pos=pos+QPoint(35,15))
np.testing.assert_allclose(v.camera()[0],before,atol=1e-8)
assert not np.allclose(v.camera()[1],forward),'Right drag did not look around'
look=v.camera()[1].copy();QTest.mouseMove(v,pos+QPoint(50,30),50)
np.testing.assert_allclose(v.camera()[1],look)
before=v.camera()[0].copy();QTest.mousePress(v,Qt.MouseButton.RightButton,pos=pos)
QTest.keyPress(v,Qt.Key.Key_W);QTest.qWait(100);QTest.keyRelease(v,Qt.Key.Key_W)
QTest.mouseRelease(v,Qt.MouseButton.RightButton,pos=pos)
assert np.linalg.norm(v.camera()[0]-before)>10,'WASD failed with right mouse held'
QTest.keyPress(v,Qt.Key.Key_W);QTest.qWait(40);w.search.setFocus();QTest.qWait(20)
assert not v.move_keys and not v.move_timer.isActive(),'Movement continued after focus loss'
stopped=v.camera()[0].copy();QTest.qWait(80);np.testing.assert_allclose(v.camera()[0],stopped)
QTest.keyRelease(w.search,Qt.Key.Key_W);QTest.keyClicks(w.search,'wasd');QTest.qWait(40)
assert w.search.text()=='wasd';np.testing.assert_allclose(v.camera()[0],stopped)
v.setFocus();QTest.keyClick(v,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier)
assert len(w.selection)==2 and not w.face_selection
np.testing.assert_allclose(v.camera()[0],stopped)
assert w.project.to_dict()==project and len(w.history.undo_stack)==history
assert not errors and not v.render_error,(errors,v.render_error)
w.saved_state=w.project.to_dict();w.close()
print('UI NAVIGATION PASS: Ctrl face toggles across brushes, scoped materials/UV/subdivision/triangulation, undo/redo, WASD, in-place right-drag look, key release, focus loss, text entry and Ctrl+A.')
