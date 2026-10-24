"""Exercise the BSP menu, real rendering, editing and project persistence."""
from pathlib import Path
import tempfile
from unittest.mock import patch
import numpy as np
from PySide6.QtCore import Qt,QSettings,QPoint
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication,QFileDialog,QMessageBox
from PySide6.QtTest import QTest
from blamhammer.app import Editor,ROOT
from blamhammer.model import Project,load
from blamhammer.toolchain import detect_hek
from tests.test_bsp import fixture

fmt=QSurfaceFormat();fmt.setVersion(2,1);fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
fmt.setDepthBufferSize(24);QSurfaceFormat.setDefaultFormat(fmt)
app=QApplication([])
with tempfile.TemporaryDirectory() as folder:
    w=Editor(Project(hek=detect_hek()));w.preferences=QSettings(str(Path(folder)/'settings.ini'),QSettings.Format.IniFormat)
    errors=[];w.error=errors.append;w.show();QTest.qWait(300)
    source=Path(w.project.hek)/'tags/levels/test/bloodgulch/bloodgulch.scenario_structure_bsp'
    original=source.read_bytes()
    menu=next(a.menu() for a in w.menuBar().actions() if a.text()=='File')
    action=next(a for a in menu.actions() if a.text()=='Open BSP…')
    with patch.object(QFileDialog,'getOpenFileName',return_value=(str(source),'')):action.trigger()
    QTest.qWait(600)
    assert not errors,errors
    assert w.filepath is None and w.project.to_dict()!=w.saved_state
    assert w.project.brushes[1].kind=='mesh' and len(w.project.brushes[1].faces)>5000
    assert w.project.sky and all(f.material=='+sky' for f in w.project.brushes[0].faces)
    assert w.perspective.isValid() and not w.perspective.render_error
    lo=np.min(w.project.brushes[0].vertices,axis=0);hi=np.max(w.project.brushes[0].vertices,axis=0)
    np.testing.assert_allclose(w.perspective.target,(lo+hi)/2)
    ROOT.joinpath('artifacts').mkdir(exist_ok=True)
    assert w.grab().save(str(ROOT/'artifacts/bsp_import_editor.png'))
    before=w.project.to_dict();bid=w.project.brushes[1].id
    w.set_tool('face')
    QTest.mouseClick(w.perspective,Qt.MouseButton.LeftButton,pos=QPoint(w.perspective.width()//2,w.perspective.height()//2))
    assert w.face_selection and w.face_selection[-1][0]==bid,'Imported terrain must be pickable through the sky enclosure'
    w.select_face(bid,0);w.uv_offset[0].setValue(.125);w.apply_uv()
    assert w.project.brushes[1].faces[0].offset[0]==.125
    w.undo();assert w.project.to_dict()==before;w.redo()
    path=Path(folder)/'bloodgulch.hceproj'
    with patch.object(QFileDialog,'getSaveFileName',return_value=(str(path),'')):assert w.save_project()
    assert load(path).to_dict()==w.project.to_dict()
    with patch.object(QFileDialog,'getOpenFileName',return_value=(str(path),'')):w.open_project()
    assert w.filepath==path and w.project.to_dict()==w.saved_state
    # Failed imports and cancelled replacement must retain the current project.
    before=w.project.to_dict();bad=Path(folder)/'bad.scenario_structure_bsp';bad.write_bytes(b'x'*64)
    with patch.object(QFileDialog,'getOpenFileName',return_value=(str(bad),'')):w.open_project(True)
    assert errors and w.project.to_dict()==before;errors.clear()
    w.project.notes='unsaved'
    with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Cancel),patch.object(QFileDialog,'getOpenFileName') as picker:
        w.open_project(True);picker.assert_not_called()
    assert w.project.notes=='unsaved'
    # Existing subdivision/vertex/history commands also work on imported mesh faces.
    small=Path(folder)/'small.scenario_structure_bsp';fixture(small)
    w.saved_state=w.project.to_dict()
    with patch.object(QFileDialog,'getOpenFileName',return_value=(str(small),'')):w.open_project()
    before=w.project.to_dict();w.select_face(w.project.brushes[1].id,0);w.subdivisions.setValue(3);w.subdivide_selection()
    assert len(w.project.brushes[1].faces)==9
    w.undo();assert w.project.to_dict()==before;w.redo()
    w.select(w.project.brushes[1].id);w.make_room()
    assert errors and w.project.brushes[1].kind=='mesh';errors.clear()
    assert source.read_bytes()==original
    w.saved_state=w.project.to_dict();w.close()
print('BSP UI PASS: menu, Blood Gulch rendering, units/framing, sky box, UV edits, undo/redo, save/reopen, subdivision, invalid import/cancel and source preservation.')
