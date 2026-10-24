"""Exercise Settings OK/Cancel, project persistence and reopening on startup."""
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from PySide6.QtCore import Qt,QSettings,QTimer
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication,QLineEdit,QPlainTextEdit,QComboBox,QDialogButtonBox
from PySide6.QtTest import QTest
import blamhammer.app as editor_app
from blamhammer.model import Project,save,load

fmt=QSurfaceFormat();fmt.setVersion(2,1);fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
QSurfaceFormat.setDefaultFormat(fmt)
app=QApplication([])


def edit_settings(window,values,accept=True):
    def fill():
        dialog=QApplication.activeModalWidget()
        assert dialog.windowTitle()=='Project and Halo CE MCC tools'
        for field in dialog.findChildren(QLineEdit):
            label=dialog.layout().labelForField(field).text()
            if label in values:field.setText(values[label])
        if 'notes' in values:dialog.findChild(QPlainTextEdit).setPlainText(values['notes'])
        if 'type' in values:dialog.findChild(QComboBox).setCurrentText(values['type'])
        buttons=dialog.findChild(QDialogButtonBox)
        button=QDialogButtonBox.StandardButton.Ok if accept else QDialogButtonBox.StandardButton.Cancel
        QTest.mouseClick(buttons.button(button),Qt.MouseButton.LeftButton)
    QTimer.singleShot(0,fill)
    window.settings()


with tempfile.TemporaryDirectory() as folder:
    root=Path(folder);prefs=QSettings(str(root/'preferences.ini'),QSettings.Format.IniFormat)
    with patch.object(editor_app,'QSettings',return_value=prefs):
        w=editor_app.Editor(Project());errors=[];w.error=errors.append
        path=root/'saved.hceproj';save(w.project,path);w.replace_project(load(path),path)
        previous=path.read_bytes()
        values={'Project name':'Saved settings','HCEEK folder':str(root),'Relative level directory':'levels\\test\\saved',
                'BSP name':'saved_bsp','Sky tag path':'sky\\test_sky','Author':'Mapper',
                'type':'singleplayer','notes':'Persistent notes'}
        edit_settings(w,values)
        assert not errors,errors
        disk=load(path);assert disk.to_dict()==w.project.to_dict()==w.saved_state
        assert (disk.name,disk.hek,disk.level_dir,disk.bsp,disk.sky,disk.author,disk.scenario_type,disk.notes)==(
            'Saved settings',str(root),'levels\\test\\saved','saved_bsp','sky\\test_sky','Mapper','singleplayer','Persistent notes')
        assert Path(str(path)+'.bak').read_bytes()==previous
        saved=path.read_bytes();saved_state=w.project.to_dict()
        edit_settings(w,{'Project name':'Cancelled'},accept=False)
        assert path.read_bytes()==saved and w.project.to_dict()==saved_state
        edit_settings(w,{'BSP name':'../invalid'})
        assert errors and path.read_bytes()==saved and w.project.to_dict()==saved_state
        errors.clear()
        with patch.object(editor_app,'save',side_effect=OSError('Test disk failure')):
            edit_settings(w,{'Author':'Unsaved author'})
        assert errors and 'Test disk failure' in errors[-1]
        assert path.read_bytes()==saved and w.project.to_dict()!=w.saved_state
        errors.clear();w.replace_project(Project())
        with patch.object(editor_app.QFileDialog,'getSaveFileName',return_value=('','')):
            edit_settings(w,{'Project name':'Not saved'})
        assert w.filepath is None and w.project.to_dict()!=w.saved_state
        assert prefs.value('last_project')==str(path.resolve())
        new_path=root/'new.hceproj'
        with patch.object(editor_app.QFileDialog,'getSaveFileName',return_value=(str(new_path),'')):
            edit_settings(w,values)
        assert load(new_path).to_dict()==w.project.to_dict()==w.saved_state
        assert prefs.value('last_project')==str(new_path.resolve())
        w.close();prefs.sync()
        assert QSettings(str(root/'preferences.ini'),QSettings.Format.IniFormat).value('last_project')==str(new_path.resolve())

        # Run the actual startup path with the existing QApplication and an immediate event-loop exit.
        opened=[]
        real_editor=editor_app.Editor
        def capture(project):
            window=real_editor(project);opened.append(window);return window
        original_hook=sys.excepthook
        try:
            with patch.object(editor_app,'Editor',side_effect=capture),patch.object(editor_app,'QApplication',return_value=app),\
                 patch.object(QApplication,'exec',return_value=0),patch.object(sys,'argv',['blamhammer']):
                editor_app.main()
            assert opened[-1].filepath==new_path and opened[-1].project.to_dict()==load(new_path).to_dict()
            opened[-1].close()
            prefs.setValue('last_project',str(root/'missing.hceproj'))
            with patch.object(editor_app,'Editor',side_effect=capture),patch.object(editor_app,'QApplication',return_value=app),\
                 patch.object(QApplication,'exec',return_value=0),patch.object(sys,'argv',['blamhammer']):
                editor_app.main()
            assert opened[-1].filepath is None and 'Could not reopen' in opened[-1].console.toPlainText()
            opened[-1].close()
        finally:sys.excepthook=original_hook
print('UI SETTINGS PASS: all settings saved/reloaded, backups, Cancel, invalid input, save cancellation/failure, first save, remembered startup and missing-file fallback.')
