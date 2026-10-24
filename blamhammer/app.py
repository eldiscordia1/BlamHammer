from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import sys
import traceback
import numpy as np
from PySide6.QtCore import Qt, QSize, QTimer, QThread, Signal, QSettings
from PySide6.QtGui import QAction, QActionGroup, QIcon, QImage, QPixmap, QColor, QSurfaceFormat
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,
    QPushButton,QComboBox,QDoubleSpinBox,QSpinBox,QLineEdit,QPlainTextEdit,QDockWidget,QTreeWidget,
    QTreeWidgetItem,QListWidget,QListWidgetItem,QSplitter,QToolBar,QFileDialog,QMessageBox,QDialog,
    QDialogButtonBox,QTabWidget,QTableWidget,QTableWidgetItem,QCheckBox,QAbstractItemView,QScrollArea)
from .model import Project,Marker,History,load,save,uid
from .geometry import primitive,bounds,transform,translate,validate_brush,boolean,world_surfaces,demo,subdivide,face_triangles
from .materials import scan_materials,preview
from .toolchain import Toolchain,detect_hek
from .viewports import OrthoView,PerspectiveView

ROOT=Path(__file__).resolve().parent.parent


def number(value=0,minimum=-100000,maximum=100000,step=25):
    widget=QDoubleSpinBox()
    widget.setRange(minimum,maximum);widget.setDecimals(3);widget.setSingleStep(step);widget.setValue(value)
    widget.setKeyboardTracking(False)
    return widget


class BuildWorker(QThread):
    message=Signal(str)
    completed=Signal(bool,str)

    def __init__(self,project,operation):
        super().__init__()
        self.chain=Toolchain(Project.from_dict(project.to_dict()),self.message.emit)
        self.operation=operation

    def run(self):
        try:
            if self.operation=='map':
                self.chain.compile_scenario();self.chain.lightmaps();self.chain.build_map()
            elif self.operation=='package':
                self.chain.lightmaps();self.chain.build_map()
            else:getattr(self.chain,self.operation)()
            self.completed.emit(True,'Verified '+self.operation.replace('_',' ')+' completed.')
        except Exception as exc:
            self.completed.emit(False,str(exc))


class Editor(QMainWindow):
    def __init__(self, project=None):
        super().__init__()
        self.project=project or Project(hek=detect_hek())
        self.history=History()
        self.selection=[];self.component=[];self.face_selection=[]
        self.tool='select';self.active_material=''
        self.filepath=None;self.saved_state=self.project.to_dict()
        self.preferences=QSettings('BlamHammer','BlamHammer')
        self.busy=False;self.worker=None;self.syncing=False
        self.csg_preview=False;self.csg_surfaces=[]
        self.resize(1540,960)
        self.setMinimumSize(1000,700)
        self.setWindowTitle('BlamHammer! — Halo CE MCC')
        self.setDockNestingEnabled(True)
        self.create_viewports()
        self.create_controls()
        self.create_menus()
        self.create_docks()
        self.refresh()
        self.scan_assets()
        self.statusBar().showMessage('F: faces · Ctrl-click: add/remove faces · 3D: WASD to move, hold right mouse to look')
        self.log('Ready. Add a Room, place solid brushes inside it, apply Halo materials, then Build MAP.')
        self.log('100 editor units = 1 Halo world unit. Builds preserve backups and verify real output files.')

    def create_viewports(self):
        self.perspective=PerspectiveView(self)
        self.top=OrthoView(self,'TOP (X/Y)',(0,1))
        self.front=OrthoView(self,'FRONT (X/Z)',(0,2))
        self.side=OrthoView(self,'SIDE (Y/Z)',(1,2))
        upper=QSplitter();upper.addWidget(self.perspective);upper.addWidget(self.top)
        lower=QSplitter();lower.addWidget(self.front);lower.addWidget(self.side)
        self.split=QSplitter(Qt.Orientation.Vertical)
        self.split.addWidget(upper);self.split.addWidget(lower)
        self.setCentralWidget(self.split)

    def action(self,label,callback,shortcut=None,checkable=False):
        a=QAction(label,self);a.setCheckable(checkable)
        a.triggered.connect(callback)
        if shortcut:a.setShortcut(shortcut)
        return a

    def create_controls(self):
        bar=QToolBar('Editing tools');bar.setMovable(False);bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea,bar)
        self.tool_actions={};group=QActionGroup(self);group.setExclusive(True)
        for title,tool,key in [('Select','select','Q'),('Draw brush','draw','B'),('Face','face','F'),
                               ('Vertex','vertex','V'),('Edge','edge','E'),('Resize','resize','R'),('Clip','clip','C'),('Entity','entity','I')]:
            a=self.action(title,lambda checked,t=tool:self.set_tool(t),key,True)
            group.addAction(a);bar.addAction(a);self.tool_actions[tool]=a
        self.tool_actions['select'].setChecked(True)
        bar.addSeparator()
        panel=QWidget();layout=QVBoxLayout(panel);layout.setContentsMargins(5,5,5,5)
        layout.addWidget(QLabel('Primitive'))
        self.shape=QComboBox();self.shape.addItems(['Box','Room','Ramp','Wedge','Cylinder','Wall','Floor','Ceiling'])
        layout.addWidget(self.shape)
        layout.addWidget(QLabel('Draw depth'))
        self.depth=number(200,1,100000);layout.addWidget(self.depth)
        layout.addWidget(QLabel('Plane offset'))
        self.plane=number();layout.addWidget(self.plane)
        layout.addWidget(QLabel('Grid size'))
        self.grid=number(self.project.grid,.01,10000);layout.addWidget(self.grid)
        self.grid.valueChanged.connect(self.set_grid)
        self.snap=QCheckBox('Snap');self.snap.setChecked(True);layout.addWidget(self.snap)
        self.snap.toggled.connect(lambda value:self.mutate(lambda:setattr(self.project,'snap',value)))
        layout.addWidget(QLabel('Clip mode'))
        self.clip_mode=QComboBox()
        for label,mode in [('Keep Left','left'),('Keep Right','right'),('Keep Both','both')]:self.clip_mode.addItem(label,mode)
        self.clip_mode.setAccessibleName('Clip mode');layout.addWidget(self.clip_mode)
        layout.addWidget(QLabel('Segments per edge'))
        self.subdivisions=QSpinBox();self.subdivisions.setRange(2,32);self.subdivisions.setValue(4)
        self.subdivisions.setAccessibleName('Subdivision segments per edge');layout.addWidget(self.subdivisions)
        self.subdivide_button=QPushButton('Subdivide faces')
        self.subdivide_button.setToolTip('Subdivide the chosen faces, or all faces of selected brushes. Then drag vertices to shape terrain.')
        self.subdivide_button.clicked.connect(self.subdivide_selection);layout.addWidget(self.subdivide_button)
        self.marker_kind=QComboBox();self.marker_kind.addItems(['player_start','weapon','vehicle','scenery'])
        layout.addWidget(QLabel('Entity type'));layout.addWidget(self.marker_kind)
        button=QPushButton('Add at origin');button.clicked.connect(self.add_primitive);layout.addWidget(button)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(panel);scroll.setMinimumWidth(160);bar.addWidget(scroll)
        toolbar=QToolBar('Project and build');self.addToolBar(toolbar)
        for text,callback,key in [('Save Project',self.save_project,'Ctrl+S'),('Export JMS',self.export,None),
                                 ('Build BSP',lambda:self.build('build_bsp'),None),('Compile Scenario',lambda:self.build('compile_scenario'),None),
                                 ('Open in Sapien',lambda:self.open_halo('sapien'),None),('Build MAP',lambda:self.build('map'),'F9')]:
            a=self.action(text,callback,key);toolbar.addAction(a)
        self.cancel_action=self.action('Cancel build',self.cancel_build);self.cancel_action.setEnabled(False);toolbar.addAction(self.cancel_action)

    def create_menus(self):
        menus={name:self.menuBar().addMenu(name) for name in ['File','Edit','View','Tools','Map','Build']}
        for name,callback,key in [('New',self.new_project,'Ctrl+N'),('Open…',self.open_project,'Ctrl+O'),('Save',self.save_project,None),
                                  ('Save As…',lambda:self.save_project(True),'Ctrl+Shift+S'),('Open BSP…',lambda:self.open_project(True),None),
                                  ('Open test room',self.open_demo,None),('Exit',self.close,'Alt+F4')]:
            menus['File'].addAction(self.action(name,callback,key))
        for name,callback,key in [('Undo',self.undo,'Ctrl+Z'),('Redo',self.redo,'Ctrl+Y'),('Duplicate',self.duplicate,'Ctrl+D'),
                                  ('Delete',self.delete_selection,'Delete'),('Select all',self.select_all,'Ctrl+A'),
                                  ('Edit vertices…',self.vertex_table,None),('Triangulate selected',self.triangulate,None),
                                  ('Subdivide faces',self.subdivide_selection,'Ctrl+Shift+D')]:
            menus['Edit'].addAction(self.action(name,callback,key))
        menus['View'].addAction(self.action('Frame all',self.frame_all,'Home'))
        menus['View'].addAction(self.action('Frame selected',lambda:self.frame_all(True),'Shift+F'))
        self.csg_action=self.action('Preview exported CSG',self.toggle_csg,'F6',True);menus['View'].addAction(self.csg_action)
        menus['Tools'].addAction(self.action('Project / HCEEK settings…',self.settings))
        menus['Tools'].addAction(self.action('Rescan materials',self.scan_assets))
        menus['Tools'].addAction(self.action('Open scenario in Guerilla',lambda:self.open_halo('guerilla')))
        for operation in ('union','subtract','intersect'):
            menus['Map'].addAction(self.action('CSG '+operation,lambda checked,o=operation:self.csg(o)))
        menus['Map'].addAction(self.action('Make selected brush a room',self.make_room))
        menus['Map'].addAction(self.action('Validate export geometry',self.validate_geometry))
        for name,operation in [('Build BSP','build_bsp'),('Compile Scenario','compile_scenario'),('Bake draft lightmaps','lightmaps'),
                               ('Build MAP (complete pipeline)','map'),('Package current Sapien scenario','package')]:
            menus['Build'].addAction(self.action(name,lambda checked,o=operation:self.build(o)))
        self.view_menu=menus['View']

    def dock(self,name,widget,area):
        d=QDockWidget(name,self);d.setObjectName(name);d.setWidget(widget);self.addDockWidget(area,d)
        self.view_menu.addAction(d.toggleViewAction());return d

    def create_docks(self):
        self.console=QPlainTextEdit();self.console.setReadOnly(True);self.console.setMaximumBlockCount(10000)
        self.console.setMinimumHeight(100)
        self.dock('Build output',self.console,Qt.DockWidgetArea.BottomDockWidgetArea)
        self.tree=QTreeWidget();self.tree.setHeaderLabels(['Scene','Type']);self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.itemSelectionChanged.connect(self.tree_selection)
        self.tree.setMinimumWidth(280)
        right=QTabWidget();right.addTab(self.tree,'Scene')
        props=QWidget();form=QFormLayout(props)
        self.name_edit=QLineEdit();form.addRow('Name',self.name_edit)
        self.name_edit.editingFinished.connect(self.rename_selected)
        self.position=[number() for _ in range(3)];self.dimensions=[number(200,.1) for _ in range(3)];self.rotation=[number(0,-360,360,15) for _ in range(3)]
        for label,fields in [('Position',self.position),('Size',self.dimensions),('Rotate Δ°',self.rotation)]:
            row=QWidget();layout=QHBoxLayout(row);layout.setContentsMargins(0,0,0,0)
            for axis,field in zip('XYZ',fields):
                field.setPrefix(axis+' ');field.setAccessibleName(label+' '+axis);layout.addWidget(field)
            form.addRow(label,row)
        button=QPushButton('Apply transform');button.clicked.connect(self.apply_transform);form.addRow(button)
        self.faces=QComboBox();self.faces.currentIndexChanged.connect(self.face_changed);form.addRow('Face',self.faces)
        self.face_selection_label=QLabel();self.face_selection_label.setWordWrap(True);form.addRow(self.face_selection_label)
        self.material_label=QLabel('No face selected');self.material_label.setWordWrap(True);self.material_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow('Shader',self.material_label)
        self.uv_scale=[number(100,-100000,100000,25) for _ in range(2)]
        self.uv_offset=[number(0,-10000,10000,.25) for _ in range(2)]
        self.uv_rotation=number(0,-36000,36000,15)
        for label,fields in [('UV size',self.uv_scale),('UV offset',self.uv_offset)]:
            row=QWidget();layout=QHBoxLayout(row);layout.setContentsMargins(0,0,0,0)
            for axis,field in zip('UV',fields):field.setPrefix(axis+' ');layout.addWidget(field)
            form.addRow(label,row)
        form.addRow('UV rotation',self.uv_rotation)
        button=QPushButton('Apply UV mapping');button.clicked.connect(self.apply_uv);form.addRow(button)
        self.team=QComboBox();self.team.addItems(['Red / 0','Blue / 1']);form.addRow('Marker team',self.team)
        self.marker_yaw=number(0,-360,360,15);form.addRow('Marker yaw',self.marker_yaw)
        self.tag_edit=QLineEdit();self.tag_edit.setPlaceholderText('Relative tag path including extension')
        form.addRow('Entity tag',self.tag_edit)
        row=QWidget();layout=QHBoxLayout(row);layout.setContentsMargins(0,0,0,0)
        button=QPushButton('Browse tag…');button.clicked.connect(self.browse_marker_tag);layout.addWidget(button)
        button=QPushButton('Apply marker');button.clicked.connect(self.apply_marker);layout.addWidget(button);form.addRow(row)
        hint=QLabel('MP weapons use .item_collection.\nCompile Scenario writes markers to an editor-owned scenario. External Sapien edits are protected.');hint.setWordWrap(True);form.addRow(hint)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(props)
        right.addTab(scroll,'Properties');self.properties_tabs=right
        self.dock('Objects',right,Qt.DockWidgetArea.RightDockWidgetArea)
        browser=QWidget();layout=QVBoxLayout(browser)
        self.search=QLineEdit();self.search.setPlaceholderText('Search installed Halo shaders…');self.search.textChanged.connect(self.filter_materials)
        layout.addWidget(self.search)
        self.material_list=QListWidget();self.material_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.material_list.setResizeMode(QListWidget.ResizeMode.Adjust);self.material_list.setIconSize(QSize(64,64));self.material_list.setGridSize(QSize(155,100));self.material_list.setWordWrap(True)
        self.material_list.setMinimumHeight(130)
        self.material_list.currentItemChanged.connect(self.material_selected);self.material_list.itemDoubleClicked.connect(lambda item:self.apply_material())
        layout.addWidget(self.material_list)
        self.preview_info=QLabel('Select a shader; double-click to apply.');self.preview_info.setWordWrap(True);layout.addWidget(self.preview_info)
        button=QPushButton('Apply shader to selection / face');button.clicked.connect(self.apply_material);layout.addWidget(button)
        self.material_dock=self.dock('Halo materials',browser,Qt.DockWidgetArea.BottomDockWidgetArea)
        self.preview_timer=QTimer(self);self.preview_timer.timeout.connect(self.load_visible_previews);self.preview_timer.start(120)
        self.resizeDocks([self.material_dock],[300],Qt.Orientation.Horizontal)

    def log(self,text):
        self.console.appendPlainText(text)

    def error(self,text):
        self.log('ERROR: '+text);self.statusBar().showMessage(text,15000)

    def selected_brush(self):
        if self.face_selection:
            return next((b for b in self.project.brushes if b.id==self.face_selection[-1][0]),None)
        return next((b for b in self.project.brushes if b.id in self.selection),None)

    def selected_marker(self):
        return next((m for m in self.project.markers if m.id in self.selection),None)

    def select(self,identifier,additive=False):
        if additive and identifier:
            if identifier in self.selection:self.selection.remove(identifier)
            else:self.selection.append(identifier)
        else:self.selection=[identifier] if identifier else []
        self.face_selection=[];self.component=[];self.refresh(False)

    def select_face(self,identifier,index,additive=False):
        brush=next((b for b in self.project.brushes if b.id==identifier),None)
        if brush is None or not 0<=index<len(brush.faces):
            if not additive:self.select(None)
            return
        face=(identifier,index)
        if not additive:self.face_selection=[face]
        elif face in self.face_selection:self.face_selection.remove(face)
        else:self.face_selection.append(face)
        self.selection=list(dict.fromkeys(bid for bid,_ in self.face_selection))
        self.component=[];self.refresh(False)

    def select_all(self):
        if QApplication.focusWidget() in (self.search,self.name_edit,self.tag_edit,self.console):return
        self.selection=[b.id for b in self.project.brushes+self.project.markers]
        self.face_selection=[];self.component=[];self.refresh(False)

    def tree_selection(self):
        if self.syncing:return
        self.selection=[item.data(0,Qt.ItemDataRole.UserRole) for item in self.tree.selectedItems()]
        self.face_selection=[];self.component=[];self.refresh_properties();self.redraw(False)

    def redraw(self,geometry=True):
        self.perspective.invalidate_cache(geometry)
        for view in (self.perspective,self.top,self.front,self.side):view.update()

    def refresh(self,geometry=True):
        brushes={b.id:b for b in self.project.brushes}
        self.face_selection=[(bid,fi) for bid,fi in self.face_selection
                             if bid in self.selection and bid in brushes and 0<=fi<len(brushes[bid].faces)]
        self.syncing=True
        self.tree.clear()
        for obj in self.project.brushes+self.project.markers:
            item=QTreeWidgetItem([obj.name,obj.kind]);item.setData(0,Qt.ItemDataRole.UserRole,obj.id)
            self.tree.addTopLevelItem(item);item.setSelected(obj.id in self.selection)
        self.grid.setValue(self.project.grid);self.snap.setChecked(self.project.snap)
        self.syncing=False
        self.refresh_properties();self.redraw(geometry)
        if geometry:self.update_title()

    def update_title(self):
        dirty=self.project.to_dict()!=self.saved_state
        self.setWindowTitle(f'{"* " if dirty else ""}{self.project.name} — BlamHammer! · Halo CE MCC')

    def refresh_properties(self):
        self.syncing=True
        brush,marker=self.selected_brush(),self.selected_marker()
        obj=brush or marker
        self.name_edit.setText(obj.name if obj else '')
        self.faces.clear();self.faces.addItem('All faces')
        count=len(self.face_selection)
        self.face_selection_label.setText(f'{count} {"face" if count==1 else "faces"} selected · values from last selected face' if count else '')
        if brush:
            lo,hi=bounds(brush)
            for widget,value in zip(self.position,(lo+hi)/2):widget.setValue(float(value))
            for widget,value in zip(self.dimensions,hi-lo):widget.setValue(float(value))
            self.faces.addItems([f'{i+1}: {Path(f.material).stem or "unassigned"}' for i,f in enumerate(brush.faces)])
            index=self.face_selection[-1][1] if self.face_selection else -1
            self.faces.setCurrentIndex(index+1)
            face=brush.faces[max(0,index)]
            self.material_label.setText(face.material or 'Unassigned — choose a real shader')
            for w,v in zip(self.uv_scale,face.scale):w.setValue(v)
            for w,v in zip(self.uv_offset,face.offset):w.setValue(v)
            self.uv_rotation.setValue(face.rotation)
        elif marker:
            for w,v in zip(self.position,marker.position):w.setValue(v)
            self.team.setCurrentIndex(marker.team);self.tag_edit.setText(marker.tag);self.marker_yaw.setValue(marker.yaw)
        self.syncing=False

    def set_tool(self,tool):
        self.tool=tool;self.tool_actions[tool].setChecked(True);self.redraw(False)
        if tool in ('face','vertex','edge','resize'):self.properties_tabs.setCurrentIndex(1)
        hints={'draw':'Drag a rectangle in a 2D view. Depth and plane offset are on the left.',
               'clip':'Choose Keep Left / Right / Both, then drag a directed line in a 2D view. The cut snaps to the grid.',
               'vertex':'Drag a square vertex in a 2D view. Subdivide faces to make terrain grids; vertex movement uses grid snapping.',
               'edge':'Select a brush, then drag an edge in a 2D view. Invalid faces are rejected.',
               'entity':'Click a 2D view to place the chosen entity at the construction plane.',
               'resize':'Select a brush, then drag near a bounding corner in a 2D view.',
               'face':'Click a face in 3D. Ctrl-click adds/removes faces; material, UV and subdivision changes apply to all selected faces.'}
        self.statusBar().showMessage(hints.get(tool,'Select and drag in 2D. Ctrl-click for multiple objects.'))

    def restore(self,state):
        self.project=Project.from_dict(state);self.refresh()

    def commit_drag(self,before):
        if self.project.to_dict()==before:return
        self.project.validate()
        originals={b['id']:b for b in before['brushes']}
        for b in self.project.brushes:
            original=originals.get(b.id,{})
            if (original.get('vertices')!=b.vertices or
                [f['indices'] for f in original.get('faces',[])]!=[f.indices for f in b.faces]):validate_brush(b)
        self.history.record(before);self.invalidate_csg();self.refresh()

    def mutate(self,callback):
        if self.syncing or self.busy:return False
        before=self.project.to_dict()
        try:
            callback();self.commit_drag(before)
            return True
        except Exception as exc:
            self.restore(before);self.error(str(exc))
            return False

    def invalidate_csg(self):
        self.csg_preview=False;self.csg_surfaces=[];self.csg_action.setChecked(False)

    def undo(self):
        if self.busy:return
        self.project=self.history.undo(self.project);self.invalidate_csg();self.refresh()

    def redo(self):
        if self.busy:return
        self.project=self.history.redo(self.project);self.invalidate_csg();self.refresh()

    def set_grid(self,value):
        self.mutate(lambda:setattr(self.project,'grid',value))

    def add_primitive(self):
        def change():
            shape=self.shape.currentText().lower()
            sizes={'room':(1600,2000,800),'wall':(400,25,400),'floor':(400,400,25),'ceiling':(400,400,25)}
            size=sizes.get(shape,(200,200,self.depth.value()))
            b=primitive(shape,(0,0,size[2]/2+self.plane.value()),size,self.active_material)
            self.project.brushes.append(b);self.selection=[b.id]
        self.mutate(change)

    def place_marker(self,position):
        m=Marker(name=self.marker_kind.currentText().replace('_',' ').title(),kind=self.marker_kind.currentText(),position=position.tolist())
        self.project.markers.append(m);self.selection=[m.id]

    def delete_selection(self):
        def change():
            self.project.brushes=[b for b in self.project.brushes if b.id not in self.selection]
            self.project.markers=[m for m in self.project.markers if m.id not in self.selection]
            self.selection=[]
        self.mutate(change)

    def duplicate(self):
        def change():
            selected=[]
            for collection in (self.project.brushes,self.project.markers):
                for obj in list(collection):
                    if obj.id in self.selection:
                        new=copy.deepcopy(obj);new.id=uid();new.name+=' copy'
                        if hasattr(new,'vertices'):translate(new,[self.project.grid,self.project.grid,0])
                        else:new.position[0]+=self.project.grid
                        collection.append(new);selected.append(new.id)
            self.selection=selected
        self.mutate(change)

    def rename_selected(self):
        if self.syncing:return
        obj=self.selected_brush() or self.selected_marker()
        if obj:self.mutate(lambda:setattr(obj,'name',self.name_edit.text().strip() or obj.name))

    def apply_transform(self):
        def change():
            brush=self.selected_brush()
            if brush:transform(brush,[w.value() for w in self.position],[w.value() for w in self.dimensions],[w.value() for w in self.rotation])
            marker=self.selected_marker()
            if marker:marker.position=[w.value() for w in self.position]
        self.mutate(change)
        for w in self.rotation:w.setValue(0)

    def face_changed(self,index):
        if self.syncing:return
        brush=self.selected_brush()
        if brush and index>0:self.select_face(brush.id,index-1)
        else:self.face_selection=[];self.refresh_properties();self.redraw(False)

    def selected_faces(self):
        chosen=set(self.face_selection)
        for b in self.project.brushes:
            if b.id in self.selection:
                for i,face in enumerate(b.faces):
                    if not chosen or (b.id,i) in chosen:yield face

    def apply_uv(self):
        def change():
            for f in self.selected_faces():
                f.scale=[w.value() for w in self.uv_scale];f.offset=[w.value() for w in self.uv_offset];f.rotation=self.uv_rotation.value()
        self.mutate(change)

    def apply_marker(self):
        def change():
            m=self.selected_marker()
            if m:m.team=self.team.currentIndex();m.tag=self.tag_edit.text().strip();m.yaw=self.marker_yaw.value()
        self.mutate(change)

    def browse_marker_tag(self):
        path,_=QFileDialog.getOpenFileName(self,'Select Halo object tag',str(Path(self.project.hek)/'tags'),'Halo tags (*.scenery *.vehicle *.weapon *.item_collection)')
        if path:
            try:self.tag_edit.setText(str(Path(path).relative_to(Path(self.project.hek)/'tags')).replace('/','\\'))
            except ValueError:self.error('Choose a tag under the configured HCEEK tags folder.')

    def scan_assets(self):
        preview.cache_clear();self.perspective.clear_textures()
        self.materials=scan_materials(self.project.hek)
        self.filter_materials(self.search.text())
        self.log(f'Found {len(self.materials)} actual Halo shader tags in {self.project.hek or "unconfigured tools folder"}.')

    def filter_materials(self,text):
        self.material_list.clear()
        entries=[('+sky','+sky · Halo special surface')]+[(m.path,m.label) for m in getattr(self,'materials',[]) if text.lower() in m.path.lower()]
        for path,label in entries:
            item=QListWidgetItem(label);item.setData(Qt.ItemDataRole.UserRole,path);item.setToolTip(path)
            self.material_list.addItem(item)

    def load_visible_previews(self):
        loaded=0
        for i in range(self.material_list.count()):
            item=self.material_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole+1):continue
            if not self.material_list.visualItemRect(item).intersects(self.material_list.viewport().rect()):continue
            path=item.data(Qt.ItemDataRole.UserRole)
            img,info=preview(self.project.hek,path)
            if img:
                q=QImage(img.tobytes(),img.width,img.height,img.width*4,QImage.Format.Format_RGBA8888).copy()
                item.setIcon(QIcon(QPixmap.fromImage(q)))
            item.setToolTip(path+'\n'+info);item.setData(Qt.ItemDataRole.UserRole+1,True)
            loaded+=1
            if loaded>=3:break

    def material_selected(self,item,previous):
        if not item:return
        self.active_material=item.data(Qt.ItemDataRole.UserRole)
        _,info=preview(self.project.hek,self.active_material)
        self.preview_info.setText(self.active_material+'\n'+info)

    def apply_material(self):
        if not self.active_material:return
        def change():
            for f in self.selected_faces():f.material=self.active_material
        self.mutate(change)

    def vertex_table(self):
        brush=self.selected_brush()
        if not brush:return
        dialog=QDialog(self);dialog.setWindowTitle('Edit vertices · JMS units');dialog.resize(480,500)
        layout=QVBoxLayout(dialog)
        layout.addWidget(QLabel('Faces must remain planar and convex. Triangulate for free deformation.'))
        table=QTableWidget(len(brush.vertices),3);table.setHorizontalHeaderLabels(['X','Y','Z'])
        for row,point in enumerate(brush.vertices):
            for col,value in enumerate(point):table.setItem(row,col,QTableWidgetItem(f'{value:g}'))
        layout.addWidget(table)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        if dialog.exec():
            self.mutate(lambda:setattr(brush,'vertices',[[float(table.item(r,c).text()) for c in range(3)] for r in range(table.rowCount())]))

    def triangulate(self):
        def change():
            chosen=set(self.face_selection)
            for b in self.project.brushes:
                if b.id in self.selection:
                    faces=[];vertices=np.asarray(b.vertices,float)
                    for fi,source in enumerate(b.faces):
                        if chosen and (b.id,fi) not in chosen:faces.append(source);continue
                        for tri in face_triangles(vertices,source.indices):
                            f=copy.deepcopy(source);f.indices=tri;faces.append(f)
                    b.faces=faces
            self.face_selection=[];self.component=[]
        self.mutate(change)

    def subdivide_selection(self):
        chosen=[b for b in self.project.brushes if b.id in self.selection]
        if not chosen:self.error('Select a brush or a face to subdivide.');return
        def change():
            for b in chosen:
                faces=[fi for bid,fi in self.face_selection if bid==b.id] if self.face_selection else None
                result=subdivide(b,self.subdivisions.value(),faces)
                self.project.brushes[self.project.brushes.index(b)]=result
            self.face_selection=[];self.component=[]
            self.set_tool('vertex')
        self.mutate(change)

    def csg(self,operation):
        chosen=[next((b for b in self.project.brushes if b.id==identifier),None) for identifier in self.selection]
        chosen=[b for b in chosen if b]
        if len(chosen)!=2:self.error('Select exactly two brushes. Subtract removes the second from the first.');return
        def change():
            result=boolean(*chosen,operation)
            self.project.brushes=[b for b in self.project.brushes if b.id not in self.selection]+[result]
            self.selection=[result.id]
        self.mutate(change)

    def make_room(self):
        if any(b.kind=='mesh' and b.id in self.selection for b in self.project.brushes):
            self.error('Imported BSP meshes are not solid brushes. Use the existing sky enclosure or add a Room.');return
        self.mutate(lambda:[setattr(b,'kind','room') for b in self.project.brushes if b.id in self.selection])

    def toggle_csg(self,checked):
        if checked:
            try:self.csg_surfaces=world_surfaces(self.project);self.csg_preview=True
            except Exception as exc:self.csg_action.setChecked(False);self.error(str(exc));return
        else:self.csg_preview=False
        self.redraw()

    def validate_geometry(self):
        try:
            surfaces=world_surfaces(self.project)
            self.log(f'Geometry valid: {len(surfaces)} export triangles. Real Tool compilation is the final topology check.')
        except Exception as exc:self.error(str(exc))

    def frame_all(self,selected=False):
        objects=[b for b in self.project.brushes if not selected or b.id in self.selection]
        if not objects:return
        vertices=np.concatenate([b.vertices for b in objects])
        lo,hi=vertices.min(axis=0),vertices.max(axis=0)
        self.perspective.target=(lo+hi)/2;self.perspective.distance=max(100,float(np.linalg.norm(hi-lo)*1.1))
        for view in (self.top,self.front,self.side):
            view.center=np.array([(lo[a]+hi[a])/2 for a in view.axes])
            view.zoom=min((view.width()-60)/max(100,hi[view.axes[0]]-lo[view.axes[0]]),(view.height()-60)/max(100,hi[view.axes[1]]-lo[view.axes[1]]))
        self.redraw(False)

    def okay_to_replace(self):
        if self.busy:self.error('Wait for the build or cancel it before replacing the project.');return False
        if self.project.to_dict()==self.saved_state:return True
        answer=QMessageBox.question(self,'Unsaved project','Save the current project first?',
             QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)
        if answer==QMessageBox.StandardButton.Save:return self.save_project()
        return answer==QMessageBox.StandardButton.Discard

    def replace_project(self,project,path=None):
        self.project=project;self.filepath=Path(path) if path else None;self.saved_state=project.to_dict();self.history=History()
        if self.filepath:self.preferences.setValue('last_project',str(self.filepath.resolve()))
        self.selection=[];self.face_selection=[];self.component=[];self.invalidate_csg();self.refresh();self.scan_assets();self.frame_all()

    def new_project(self):
        if self.okay_to_replace():self.replace_project(Project(hek=self.project.hek))

    def open_project(self,bsp_only=False):
        if not self.okay_to_replace():return
        filters='Halo CE BSP tags (*.scenario_structure_bsp)' if bsp_only else 'Projects and BSPs (*.hceproj *.scenario_structure_bsp);;BlamHammer projects (*.hceproj);;Halo CE BSP tags (*.scenario_structure_bsp)'
        folder=Path(self.project.hek)/'tags/levels' if bsp_only and self.project.hek else ROOT/'examples'
        filename,_=QFileDialog.getOpenFileName(self,'Open BSP' if bsp_only else 'Open project',str(folder),filters)
        if filename:
            try:
                if Path(filename).suffix.lower()=='.scenario_structure_bsp':
                    from .bsp import import_bsp
                    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                    try:project=import_bsp(filename,self.project.hek)
                    finally:QApplication.restoreOverrideCursor()
                    self.replace_project(project);self.saved_state=None;self.update_title()
                    self.log('Imported BSP at 100 editor units per Halo unit, with original texture mapping, collision and a +sky enclosure. Save as a new project.')
                else:self.replace_project(load(filename),filename)
            except Exception as exc:self.error(str(exc))

    def open_demo(self):
        if not self.okay_to_replace():return
        project=load(ROOT/'examples/test_room.hceproj');project.hek=self.project.hek or detect_hek()
        self.replace_project(project)

    def save_project(self,save_as=False):
        filename=str(self.filepath) if self.filepath else ''
        if save_as or not filename:
            filename,_=QFileDialog.getSaveFileName(self,'Save project',str(ROOT/(self.project.bsp+'.hceproj')),'BlamHammer projects (*.hceproj)')
        if not filename:return False
        if not filename.lower().endswith('.hceproj'):filename+='.hceproj'
        try:
            save(self.project,filename);self.filepath=Path(filename);self.saved_state=self.project.to_dict()
            self.preferences.setValue('last_project',str(self.filepath.resolve()))
            self.update_title();self.log('Saved '+filename);return True
        except Exception as exc:self.error(str(exc));return False

    def export(self):
        from .jms import export_jms
        filename,_=QFileDialog.getSaveFileName(self,'Export Halo CE JMS',str(ROOT/(self.project.bsp+'.jms')),'Halo CE geometry (*.jms)')
        if filename:
            try:self.log(f'Exported {export_jms(self.project,filename)} triangles to {filename}')
            except Exception as exc:self.error(str(exc))

    def settings(self):
        if self.busy:self.error('Wait for the build to finish before changing project settings.');return
        dialog=QDialog(self);dialog.setWindowTitle('Project and Halo CE MCC tools');dialog.resize(650,480)
        layout=QFormLayout(dialog)
        hint=QLabel('OK saves settings with the entire project. A new project will ask for a filename.');hint.setWordWrap(True);layout.addRow(hint)
        fields={}
        for key,label in [('name','Project name'),('hek','HCEEK folder'),('level_dir','Relative level directory'),('bsp','BSP name'),('sky','Sky tag path'),('author','Author')]:
            fields[key]=QLineEdit(getattr(self.project,key));layout.addRow(label,fields[key])
        row=QWidget();buttons=QHBoxLayout(row);buttons.setContentsMargins(0,0,0,0)
        browse=QPushButton('Browse HCEEK…');buttons.addWidget(browse)
        browse.clicked.connect(lambda:fields['hek'].setText(QFileDialog.getExistingDirectory(dialog,'HCEEK folder',fields['hek'].text()) or fields['hek'].text()))
        sky=QPushButton('Browse sky…');buttons.addWidget(sky)
        def choose_sky():
            filename,_=QFileDialog.getOpenFileName(dialog,'Sky tag',str(Path(fields['hek'].text())/'tags/sky'),'Halo sky (*.sky)')
            if filename:
                try:fields['sky'].setText(str(Path(filename).relative_to(Path(fields['hek'].text())/'tags').with_suffix('')).replace('/','\\'))
                except ValueError:self.error('Sky must be under tags.')
        sky.clicked.connect(choose_sky);layout.addRow(row)
        type_combo=QComboBox();type_combo.addItems(['multiplayer','singleplayer']);type_combo.setCurrentText(self.project.scenario_type);layout.addRow('Scenario type',type_combo)
        notes=QPlainTextEdit(self.project.notes);layout.addRow('Notes',notes)
        info=QLabel('Use a unique level directory. Rebuilds back up outputs. Compile Scenario stops if Sapien/Guerilla changed the scenario; use Package current Sapien scenario to keep those edits.');info.setWordWrap(True);layout.addRow(info)
        done=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        done.accepted.connect(dialog.accept);done.rejected.connect(dialog.reject);layout.addRow(done)
        if dialog.exec():
            def change():
                for key,field in fields.items():setattr(self.project,key,field.text().strip())
                self.project.scenario_type=type_combo.currentText();self.project.notes=notes.toPlainText()
            if self.mutate(change):
                self.scan_assets()
                if not self.save_project():self.log('Settings are not saved yet. Use Save Project to keep them.')

    def build(self,operation):
        if self.busy:self.error('A build is already running.');return
        self.busy=True;self.cancel_action.setEnabled(True)
        self.log('\n=== '+operation.replace('_',' ').upper()+' ===')
        self.worker=BuildWorker(self.project,operation)
        self.worker.message.connect(self.log);self.worker.completed.connect(self.build_completed)
        self.worker.finished.connect(self.build_finished)
        self.worker.start();self.statusBar().showMessage('Building — actual HCEEK output appears below. Cancel build stops the current process.')

    def build_completed(self,success,message):
        self.log(('SUCCESS: ' if success else 'FAILED: ')+message);self.statusBar().showMessage(message,20000)

    def build_finished(self):
        self.busy=False;self.cancel_action.setEnabled(False)

    def cancel_build(self):
        if self.worker:self.worker.chain.cancel()

    def open_halo(self,editor):
        if self.busy:self.error('Wait for the build before opening Halo editors.');return
        try:Toolchain(self.project,self.log).open_editor(editor)
        except Exception as exc:self.error(str(exc))

    def closeEvent(self,event):
        if self.busy:
            self.cancel_build()
            if not self.worker.wait(3000):event.ignore();self.error('Build is stopping; close again when it finishes.');return
            self.busy=False
        if not self.okay_to_replace():event.ignore();return
        self.preview_timer.stop();self.perspective.clear_textures();event.accept()


def main():
    fmt=QSurfaceFormat();fmt.setVersion(2,1);fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
    fmt.setDepthBufferSize(24);fmt.setSamples(4);QSurfaceFormat.setDefaultFormat(fmt)
    app=QApplication(sys.argv);app.setApplicationName('BlamHammer!');app.setStyle('Fusion')
    filename=sys.argv[1] if len(sys.argv)>1 else QSettings('BlamHammer','BlamHammer').value('last_project','',type=str)
    startup_error=''
    try:project=load(filename) if filename else load(ROOT/'examples/test_room.hceproj')
    except (OSError,ValueError) as exc:
        startup_error=f'Could not reopen {filename}: {exc}. Opened the test room instead.'
        project=load(ROOT/'examples/test_room.hceproj');filename=''
    if not Path(project.hek).is_dir():project.hek=detect_hek()
    window=Editor(project)
    if filename:
        window.filepath=Path(filename)
        window.preferences.setValue('last_project',str(window.filepath.resolve()))
    if startup_error:window.error(startup_error)
    window.show();QTimer.singleShot(200,window.frame_all)
    def exception_hook(type_,value,tb):
        window.error(str(value));window.log(''.join(traceback.format_exception(type_,value,tb)))
    sys.excepthook=exception_hook
    return app.exec()


if __name__=='__main__':
    raise SystemExit(main())
