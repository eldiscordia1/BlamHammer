from __future__ import annotations

import math
import copy
import numpy as np
from PySide6.QtCore import Qt, QPointF, QRectF, QTimer, QElapsedTimer
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget,QLabel
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from OpenGL.GL import *
from OpenGL.GLU import gluPerspective, gluLookAt
from .geometry import bounds, primitive, translate, normal, triangles, uv_for, clip_brushes, world_surfaces
from .materials import preview


class OrthoView(QWidget):
    def __init__(self, editor, title, axes):
        super().__init__()
        self.editor,self.title,self.axes=editor,title,axes
        self.zoom=0.2
        self.center=np.array([0.,0.])
        self.start=None
        self.last=None
        self.before=None
        self.component=None
        self.panning=False
        self.setMinimumSize(180,140)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(title+' orthographic editing viewport')

    def project(self, p):
        return QPointF(self.width()/2+(p[self.axes[0]]-self.center[0])*self.zoom,
                       self.height()/2-(p[self.axes[1]]-self.center[1])*self.zoom)

    def world(self,pos,snap=False):
        p=np.zeros(3)
        p[self.axes[0]]=(pos.x()-self.width()/2)/self.zoom+self.center[0]
        p[self.axes[1]]=-(pos.y()-self.height()/2)/self.zoom+self.center[1]
        if snap and self.editor.project.snap:
            p=np.round(p/self.editor.project.grid)*self.editor.project.grid
        return p

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.fillRect(self.rect(),QColor('#20252b'))
        grid=self.editor.project.grid
        step=grid
        while step*self.zoom<12:
            step*=2
        painter.setPen(QPen(QColor('#303740'),1))
        for axis,extent in enumerate((self.width(),self.height())):
            half=extent/2/self.zoom
            low=self.center[axis]-half
            for v in np.arange(math.floor(low/step)*step,low+half*2+step,step):
                pos=np.zeros(3);pos[self.axes[axis]]=v
                point=self.project(pos)
                if axis==0:painter.drawLine(int(point.x()),24,int(point.x()),self.height())
                else:painter.drawLine(0,int(point.y()),self.width(),int(point.y()))
        zero=self.project([0,0,0])
        painter.setPen(QPen(QColor('#49606e'),1))
        painter.drawLine(int(zero.x()),24,int(zero.x()),self.height())
        painter.drawLine(0,int(zero.y()),self.width(),int(zero.y()))
        for brush in self.editor.project.brushes:
            selected=brush.id in self.editor.selection
            painter.setPen(QPen(QColor('#ffc365' if selected else '#a8b5be' if brush.kind=='solid' else '#6e98b3'),2 if selected else 1))
            projected=[self.project(p) for p in brush.vertices]
            for face in brush.faces:
                if '@' in face.flags or '*' in face.flags:continue
                points=[projected[i] for i in face.indices]
                painter.drawPolygon(QPolygonF(points))
            if selected:
                if self.editor.tool in ('vertex','edge'):
                    for i,point in enumerate(brush.vertices):
                        selected_vertex=i in self.editor.component
                        painter.setBrush(QColor('#fff2b4' if selected_vertex else '#ffb347'))
                        q=self.project(point)
                        painter.drawRect(QRectF(q.x()-3,q.y()-3,6,6))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                elif self.editor.tool=='resize':
                    lo,hi=bounds(brush)
                    for a in (lo[self.axes[0]],hi[self.axes[0]]):
                        for b in (lo[self.axes[1]],hi[self.axes[1]]):
                            pt=lo.copy();pt[self.axes[0]]=a;pt[self.axes[1]]=b
                            q=self.project(pt)
                            painter.fillRect(QRectF(q.x()-4,q.y()-4,8,8),QColor('#ffc365'))
        for marker in self.editor.project.markers:
            q=self.project(marker.position)
            color='#ffc365' if marker.id in self.editor.selection else '#e77c75' if marker.team==0 else '#76b8f0'
            painter.setPen(QPen(QColor(color),2))
            painter.drawEllipse(q,6,6)
            painter.drawLine(q+QPointF(-10,0),q+QPointF(10,0))
            painter.drawLine(q+QPointF(0,-10),q+QPointF(0,10))
        if self.start is not None and self.last is not None and self.editor.tool in ('draw','clip'):
            painter.setPen(QPen(QColor('#ffc365'),2,Qt.PenStyle.DashLine))
            if self.editor.tool=='draw':
                painter.drawRect(QRectF(self.start,self.last).normalized())
            else:
                painter.drawLine(self.start,self.last)
                delta=self.last-self.start;length=math.hypot(delta.x(),delta.y())
                if length>1:
                    direction=delta/length;side=QPointF(-direction.y(),direction.x())
                    painter.drawPolyline(QPolygonF([self.last-direction*12+side*5,self.last,self.last-direction*12-side*5]))
                painter.drawText(self.last+QPointF(8,-8),self.editor.clip_mode.currentText())
        painter.fillRect(0,0,self.width(),24,QColor('#303943'))
        painter.setPen(QColor('#dce5ec'))
        painter.drawText(9,17,f'{self.title}   ·   grid {grid:g}   ·   {self.editor.tool}')
        painter.end()

    def hit(self,pos):
        for marker in reversed(self.editor.project.markers):
            q=self.project(marker.position)
            if (q-pos).manhattanLength()<18:return marker.id
        candidates=[]
        for b in self.editor.project.brushes:
            lo,hi=bounds(b)
            rect=QRectF(self.project(lo),self.project(hi)).normalized().adjusted(-4,-4,4,4)
            if rect.contains(pos):
                candidates.append((rect.width()*rect.height(),b.id))
        return min(candidates)[1] if candidates else None

    def mousePressEvent(self,event):
        self.setFocus()
        pos=event.position()
        self.last=pos
        if event.button()==Qt.MouseButton.MiddleButton:
            self.panning=True
            return
        if event.button()!=Qt.MouseButton.LeftButton or self.editor.busy:return
        self.start=pos
        self.before=self.editor.project.to_dict()
        self.component=None
        brush=self.editor.selected_brush()
        if self.editor.tool in ('vertex','edge') and brush:
            if self.editor.tool=='vertex':
                distances=[(self.project(p)-pos).manhattanLength() for p in brush.vertices]
                # Keep a vertex chosen in another view when several vertices project together.
                i=min(range(len(distances)),key=lambda i:(distances[i],i not in self.editor.component))
                self.component=[i] if distances[i]<18 else []
            else:
                edges={tuple(sorted((f.indices[i],f.indices[(i+1)%len(f.indices)]))) for f in brush.faces for i in range(len(f.indices))}
                best=(float('inf'),None)
                p=np.array([pos.x(),pos.y()])
                for a,b in edges:
                    qa,qb=self.project(brush.vertices[a]),self.project(brush.vertices[b])
                    va,vb=np.array([qa.x(),qa.y()]),np.array([qb.x(),qb.y()])
                    d=vb-va;t=np.clip(np.dot(p-va,d)/max(np.dot(d,d),1e-6),0,1)
                    distance=float(np.linalg.norm(p-va-t*d))
                    if distance<best[0]:best=(distance,[a,b])
                self.component=best[1] if best[0]<12 else []
            self.editor.component=self.component or []
            self.editor.redraw(False)
        elif self.editor.tool not in ('draw','clip','entity','resize'):
            found=self.hit(pos)
            additive=bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            self.editor.select(found,additive)
        self.update()

    def mouseMoveEvent(self,event):
        pos=event.position()
        if self.panning and self.last is not None:
            self.center+=np.array([self.last.x()-pos.x(),pos.y()-self.last.y()])/self.zoom
            self.last=pos;self.update();return
        if self.start is None:return
        self.last=pos
        tool=self.editor.tool
        if tool in ('select','vertex','edge','resize') and self.editor.selection:
            delta=self.world(pos,True)-self.world(self.start,True)
            # Always apply a drag to its original snapshot, avoiding cumulative rounding.
            originals={b['id']:b for b in self.before['brushes']}
            active_brush=self.editor.selected_brush()
            for brush in self.editor.project.brushes:
                if brush.id not in self.editor.selection:continue
                if tool in ('vertex','edge') and brush is not active_brush:continue
                brush.vertices=copy.deepcopy(originals[brush.id]['vertices'])
                if tool=='resize':
                    lo,hi=bounds(brush)
                    initial=self.world(self.start)
                    new_lo,new_hi=lo.copy(),hi.copy()
                    for axis in self.axes:
                        if abs(initial[axis]-lo[axis])<abs(initial[axis]-hi[axis]):new_lo[axis]+=delta[axis]
                        else:new_hi[axis]+=delta[axis]
                    if np.all(new_hi-new_lo>=0.1):
                        vertices=(np.asarray(brush.vertices)-lo)/(hi-lo)*(new_hi-new_lo)+new_lo
                        brush.vertices=vertices.tolist()
                elif tool in ('vertex','edge'):
                    if self.component:translate(brush,delta,self.component)
                else:translate(brush,delta)
            if tool=='select':
                for marker,original in zip(self.editor.project.markers,self.before['markers']):
                    if marker.id in self.editor.selection:
                        marker.position=(np.asarray(original['position'])+delta).tolist()
            self.editor.redraw()
        self.update()

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.MiddleButton:
            self.panning=False;return
        if event.button()!=Qt.MouseButton.LeftButton or self.start is None:return
        tool=self.editor.tool
        start,end=self.world(self.start,True),self.world(event.position(),True)
        before=self.before
        try:
            if tool=='draw':
                size=np.abs(end-start)
                hidden=({0,1,2}-set(self.axes)).pop()
                size[hidden]=self.editor.depth.value()
                if all(size[a]>=0.1 for a in self.axes):
                    center=(start+end)/2
                    center[hidden]=self.editor.plane.value()+size[hidden]/2
                    brush=primitive(self.editor.shape.currentText().lower(),center,size,self.editor.active_material)
                    self.editor.project.brushes.append(brush)
                    self.editor.selection=[brush.id]
            elif tool=='clip':
                brush=self.editor.selected_brush()
                direction=end-start
                if brush and np.linalg.norm(direction)>0.1:
                    n=np.zeros(3);n[self.axes[0]]=-direction[self.axes[1]];n[self.axes[1]]=direction[self.axes[0]]
                    n/=np.linalg.norm(n)
                    replacements=clip_brushes(brush,n,float(np.dot(n,start)),self.editor.clip_mode.currentData())
                    index=self.editor.project.brushes.index(brush)
                    self.editor.project.brushes[index:index+1]=replacements
                    self.editor.selection=[b.id for b in replacements]
                    self.editor.face_selection=[];self.editor.component=[]
            elif tool=='entity':
                hidden=({0,1,2}-set(self.axes)).pop()
                end[hidden]=self.editor.plane.value()
                self.editor.place_marker(end)
            self.editor.commit_drag(before)
        except Exception as exc:
            self.editor.restore(before)
            self.editor.error(str(exc))
        self.start=self.last=self.before=None
        self.editor.redraw(False)

    def wheelEvent(self,event):
        pos=event.position()
        before=self.world(pos)
        self.zoom=np.clip(self.zoom*1.2**(event.angleDelta().y()/120),0.01,20)
        after=self.world(pos)
        self.center+=[before[a]-after[a] for a in self.axes]
        self.update()

    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape and self.before:
            self.editor.restore(self.before);self.start=self.last=self.before=None
        else:super().keyPressEvent(event)


class PerspectiveView(QOpenGLWidget):
    def __init__(self,editor):
        super().__init__()
        self.editor=editor
        self.target=np.array([0.,0.,300.])
        self.distance=2600.
        self.yaw=math.radians(-125)
        self.pitch=math.radians(28)
        self.last=None
        self.move_keys=set()
        self.move_clock=QElapsedTimer()
        self.move_timer=QTimer(self);self.move_timer.setInterval(16)
        self.move_timer.timeout.connect(self.move_camera)
        self.textures={}
        self.batches=None
        self._geometry=None
        self.selection_state=None
        self.selected_lines=None
        self.render_error=''
        self.setMinimumSize(180,140)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName('Perspective 3D textured viewport')
        self.caption=QLabel('3D PERSPECTIVE · textured',self)
        self.caption.setStyleSheet('background:#303943;color:#e3eaf0;padding-left:9px;')
        self.caption.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.caption.setGeometry(0,0,self.width(),24)

    def camera(self):
        eye=self.target+self.distance*np.array([math.cos(self.pitch)*math.cos(self.yaw),math.cos(self.pitch)*math.sin(self.yaw),math.sin(self.pitch)])
        forward=self.target-eye;forward/=np.linalg.norm(forward)
        right=np.cross(forward,[0,0,1]);right/=np.linalg.norm(right)
        up=np.cross(right,forward)
        return eye,forward,right,up

    def initializeGL(self):
        glClearColor(0.12,0.15,0.18,1)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_CULL_FACE)
        glFrontFace(GL_CCW)
        glEnable(GL_POLYGON_OFFSET_FILL)
        glPolygonOffset(1,1)

    def texture(self,material):
        key=(self.editor.project.hek,material)
        if key not in self.textures:
            img,_=preview(*key)
            if img is None:self.textures[key]=0
            else:
                img=img.transpose(1)
                tex=glGenTextures(1)
                glBindTexture(GL_TEXTURE_2D,tex)
                glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_REPEAT)
                glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_REPEAT)
                glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,img.width,img.height,0,GL_RGBA,GL_UNSIGNED_BYTE,img.tobytes())
                self.textures[key]=int(tex)
        return self.textures[key]

    def clear_textures(self):
        if self.isValid():
            self.makeCurrent()
            ids=[t for t in self.textures.values() if t]
            if ids:glDeleteTextures(ids)
            self.doneCurrent()
        self.textures.clear()
        self.invalidate_cache()

    def invalidate_cache(self,geometry=True):
        self.selection_state=None
        if geometry:
            self.batches=None;self._geometry=None

    def prepare_batches(self):
        groups={};self.batch_faces={}
        for points,n,uv,material,bid,fi in self.geometry():
            shade=.60+.40*abs(float(np.dot(n,[.25,.35,.902])))
            tex=self.texture(material)
            color=(shade,shade,shade) if tex else (.30,.55,.72) if material=='+sky' else (.55*shade,.58*shade,.62*shade)
            groups.setdefault(tex,[]).append(np.column_stack((uv,np.tile(color,(3,1)),points)))
            self.batch_faces.setdefault(tex,[]).append((bid,fi))
        self.batches={tex:np.ascontiguousarray(np.concatenate(parts),dtype=np.float32) for tex,parts in groups.items()}
        self.base_colors={tex:vertices[:,2:5].copy() for tex,vertices in self.batches.items()}
        self.prepare_selection()

    def prepare_selection(self):
        faces=set(self.editor.face_selection);selected=set(self.editor.selection);lines=[]
        for tex,vertices in self.batches.items():
            vertices[:,2:5]=self.base_colors[tex]
            if faces:
                mask=np.repeat([face in faces for face in self.batch_faces[tex]],3)
                vertices[mask,2:5]=(1,.75,.35)
        if self.editor.csg_preview:
            for points,n,uv,material,bid,fi in self.geometry():
                if (bid,fi) in faces or (not faces and bid in selected):
                    lines.append(points[[0,1,1,2,2,0]])
        if not self.editor.csg_preview:
            for brush in self.editor.project.brushes:
                if brush.id not in selected:continue
                v=np.asarray(brush.vertices)
                edges=[(a,b) for fi,face in enumerate(brush.faces)
                       if '@' not in face.flags and '*' not in face.flags and (not faces or (brush.id,fi) in faces)
                       for a,b in zip(face.indices,face.indices[1:]+face.indices[:1])]
                if edges:lines.append(v[np.asarray(edges)].reshape(-1,3))
        self.selected_lines=np.ascontiguousarray(np.concatenate(lines) if lines else np.empty((0,3)),dtype=np.float32)
        self.selection_state=(tuple(self.editor.selection),tuple(self.editor.face_selection))

    def geometry(self):
        if self._geometry is None:self._geometry=list(self.build_geometry())
        yield from self._geometry

    def build_geometry(self):
        if self.editor.csg_preview:
            for s in self.editor.csg_surfaces:
                if '@' in s.flags or '*' in s.flags:continue
                yield s.points,s.normal,s.uv,s.material,s.brush_id,-1
            return
        for brush in self.editor.project.brushes:
            v=np.asarray(brush.vertices)
            for fi,indices in triangles(brush):
                face=brush.faces[fi]
                if '@' in face.flags or '*' in face.flags:continue
                points=v[indices[::-1] if brush.kind=='room' else indices]
                try:n=normal(points)
                except ValueError:continue
                yield points,n,uv_for(points,face,n),face.material,brush.id,fi

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT)
        glViewport(0,0,int(self.width()*self.devicePixelRatioF()),int(self.height()*self.devicePixelRatioF()))
        glMatrixMode(GL_PROJECTION);glLoadIdentity()
        gluPerspective(55,self.width()/max(1,self.height()),1,200000)
        eye,forward,right,up=self.camera()
        glMatrixMode(GL_MODELVIEW);glLoadIdentity()
        gluLookAt(*eye,*self.target,0,0,1)
        glDisable(GL_TEXTURE_2D)
        glColor3f(.22,.28,.32)
        glBegin(GL_LINES)
        step=max(100,self.editor.project.grid)
        for v in np.arange(-2000,2001,step):
            glVertex3f(v,-2000,-1);glVertex3f(v,2000,-1)
            glVertex3f(-2000,v,-1);glVertex3f(2000,v,-1)
        glEnd()
        try:
            if self.batches is None:self.prepare_batches()
            elif self.selection_state!=(tuple(self.editor.selection),tuple(self.editor.face_selection)):self.prepare_selection()
            for tex,vertices in self.batches.items():
                if tex:glEnable(GL_TEXTURE_2D);glBindTexture(GL_TEXTURE_2D,tex)
                else:glDisable(GL_TEXTURE_2D)
                glInterleavedArrays(GL_T2F_C3F_V3F,0,vertices)
                glDrawArrays(GL_TRIANGLES,0,len(vertices))
            glDisableClientState(GL_TEXTURE_COORD_ARRAY);glDisableClientState(GL_COLOR_ARRAY);glDisableClientState(GL_VERTEX_ARRAY)
            glDisable(GL_TEXTURE_2D)
            glLineWidth(1.5)
            glColor3f(1,.72,.30)
            if len(self.selected_lines):
                glEnableClientState(GL_VERTEX_ARRAY);glVertexPointer(3,GL_FLOAT,0,self.selected_lines)
                glDrawArrays(GL_LINES,0,len(self.selected_lines));glDisableClientState(GL_VERTEX_ARRAY)
            glDisable(GL_DEPTH_TEST)
            glLineWidth(2)
            for marker in self.editor.project.markers:
                glColor3f(*((1,.7,.2) if marker.id in self.editor.selection else (.95,.3,.3) if marker.team==0 else (.3,.65,1)))
                p=np.array(marker.position)
                glBegin(GL_LINES)
                for axis in np.eye(3):glVertex3f(*(p-axis*25));glVertex3f(*(p+axis*25))
                glVertex3f(*p);glVertex3f(*(p+[0,0,70]))
                glEnd()
            glEnable(GL_DEPTH_TEST)
            self.render_error=''
        except Exception as exc:
            self.render_error=str(exc)
        self.caption.setText('3D · '+(self.render_error[:80] if self.render_error else 'CSG export preview' if self.editor.csg_preview else 'WASD move · right mouse look'))

    def ray(self,pos):
        eye,forward,right,up=self.camera()
        factor=math.tan(math.radians(55)/2)
        dx=(2*pos.x()/self.width()-1)*self.width()/self.height()*factor
        dy=(1-2*pos.y()/self.height())*factor
        direction=forward+right*dx+up*dy
        return eye,direction/np.linalg.norm(direction)

    def pick(self,pos):
        origin,direction=self.ray(pos)
        best=(float('inf'),None,-1)
        geometry=list(self.geometry())
        if geometry:
            points=np.asarray([surface[0] for surface in geometry])
            e1=points[:,1]-points[:,0];e2=points[:,2]-points[:,0]
            h=np.cross(direction,e2);det=np.einsum('ij,ij->i',e1,h)
            valid=det>1e-9
            inverse=np.divide(1.,det,out=np.zeros_like(det),where=valid)
            s=origin-points[:,0];u=np.einsum('ij,ij->i',s,h)*inverse
            q=np.cross(s,e1);v=(q@direction)*inverse
            t=np.einsum('ij,ij->i',e2,q)*inverse
            valid&=(u>=0)&(u<=1)&(v>=0)&(u+v<=1)&(t>0)
            t[~valid]=np.inf
            hit=int(np.argmin(t))
            if np.isfinite(t[hit]):best=(t[hit],geometry[hit][4],geometry[hit][5])
        for m in self.editor.project.markers:
            delta=np.asarray(m.position)-origin;t=np.dot(delta,direction)
            if t>0 and np.linalg.norm(delta-t*direction)<35 and t<best[0]:best=(t,m.id,-1)
        return best[1:]

    def mousePressEvent(self,event):
        self.setFocus();self.last=event.position()
        if event.button()==Qt.MouseButton.LeftButton and not self.editor.busy:
            bid,fi=self.pick(event.position())
            additive=bool(event.modifiers()&Qt.KeyboardModifier.ControlModifier)
            if self.editor.tool=='face':
                if self.editor.csg_preview:self.editor.error('Turn off CSG preview (F6) to select editable faces.')
                else:self.editor.select_face(bid,fi,additive)
            else:self.editor.select(bid,additive)

    def mouseMoveEvent(self,event):
        if self.last is None:return
        delta=event.position()-self.last
        if event.buttons()&Qt.MouseButton.RightButton:
            eye=self.camera()[0]
            self.yaw-=delta.x()*.008
            self.pitch=np.clip(self.pitch+delta.y()*.008,-1.5,1.5)
            self.target=eye+self.camera()[1]*self.distance
        elif event.buttons()&Qt.MouseButton.MiddleButton:
            _,_,right,up=self.camera()
            self.target+=(-right*delta.x()+up*delta.y())*self.distance*.0015
        self.last=event.position();self.update()

    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_W,Qt.Key.Key_A,Qt.Key.Key_S,Qt.Key.Key_D) and not event.modifiers():
            if not event.isAutoRepeat():
                self.move_keys.add(event.key())
                if not self.move_timer.isActive():self.move_clock.start();self.move_timer.start()
            event.accept()
        else:super().keyPressEvent(event)

    def keyReleaseEvent(self,event):
        if event.key() in self.move_keys:
            if not event.isAutoRepeat():
                self.move_keys.discard(event.key())
                if not self.move_keys:self.move_timer.stop()
            event.accept()
        else:super().keyReleaseEvent(event)

    def move_camera(self):
        elapsed=min(self.move_clock.restart()/1000,.1)
        _,forward,right,_=self.camera()
        direction=forward*(int(Qt.Key.Key_W in self.move_keys)-int(Qt.Key.Key_S in self.move_keys))
        direction+=right*(int(Qt.Key.Key_D in self.move_keys)-int(Qt.Key.Key_A in self.move_keys))
        length=np.linalg.norm(direction)
        if length:
            self.target+=direction/length*600*elapsed
            self.update()

    def focusOutEvent(self,event):
        self.move_keys.clear();self.move_timer.stop()
        super().focusOutEvent(event)

    def hideEvent(self,event):
        self.move_keys.clear();self.move_timer.stop()
        super().hideEvent(event)

    def wheelEvent(self,event):
        self.distance=np.clip(self.distance*1.15**(-event.angleDelta().y()/120),20,100000)
        self.update()
