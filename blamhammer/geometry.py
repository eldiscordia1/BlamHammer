from __future__ import annotations

from dataclasses import dataclass
import copy
import math
import numpy as np
import manifold3d as md
from .model import Brush, Face, Project, Marker


def normal(points):
    n = np.cross(points[1:-1] - points[0], points[2:] - points[0]).sum(axis=0)
    length = np.linalg.norm(n)
    if length < 1e-8:
        raise ValueError('Degenerate face: zero area.')
    return n / length


def primitive(shape='box', center=(0, 0, 100), size=(200, 200, 200), material='', segments=16):
    if any(float(x) <= 0 for x in size):
        raise ValueError('Brush dimensions must be positive.')
    if shape in ('ramp', 'wedge'):
        verts = [[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,1,1],[1,1,1]]
        faces = [[3,2,1,0], [0,1,5,4], [1,2,5], [2,3,4,5], [3,0,4]]
    elif shape == 'cylinder':
        segments = max(3, min(64, segments))
        verts = [[math.cos(i*2*math.pi/segments), math.sin(i*2*math.pi/segments), z]
                 for z in (-1,1) for i in range(segments)]
        faces = [list(range(segments-1,-1,-1)), list(range(segments,2*segments))]
        faces += [[i,(i+1)%segments,(i+1)%segments+segments,i+segments] for i in range(segments)]
    else:
        verts = [[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]]
        faces = [[3,2,1,0],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]
    vertices = (np.asarray(verts, float)*np.asarray(size)/2 + np.asarray(center)).tolist()
    return Brush(shape.title(), vertices, [Face(f, material) for f in faces], 'room' if shape=='room' else 'solid')


def bounds(brush):
    v = np.asarray(brush.vertices)
    return v.min(axis=0), v.max(axis=0)


def translate(brush, delta, indices=None):
    v = np.asarray(brush.vertices, dtype=float)
    target = list(range(len(v))) if indices is None else list(indices)
    v[target] += np.asarray(delta)
    brush.vertices = v.tolist()


def transform(brush, center=None, size=None, rotation=None):
    lo, hi = bounds(brush)
    old_center = (lo + hi) / 2
    vertices = np.asarray(brush.vertices, dtype=float) - old_center
    if size is not None:
        if min(size) <= 0 or np.any(hi-lo < 1e-6):
            raise ValueError('Cannot resize to zero thickness.')
        vertices *= np.asarray(size) / (hi-lo)
    if rotation is not None:
        for axis, deg in enumerate(rotation):
            angle = math.radians(deg)
            a, b = [(1,2),(2,0),(0,1)][axis]
            matrix = np.eye(3)
            matrix[a,a] = matrix[b,b] = math.cos(angle)
            matrix[a,b], matrix[b,a] = -math.sin(angle), math.sin(angle)
            vertices = vertices @ matrix.T
    brush.vertices = (vertices + (old_center if center is None else center)).tolist()


def face_triangles(vertices, indices):
    if len(indices)==3:
        yield list(indices)
        return
    points = vertices[indices]
    n = normal(points)
    axis = int(np.argmax(np.abs(n)))
    flat = points[:,[(1,2),(2,0),(0,1)][axis]].copy()
    flat[:,1] *= np.sign(n[axis])
    # CCW ear clipping retains collinear boundary points without zero-area triangles.
    for tri in md.triangulate([flat], allow_convex=False):
        yield [indices[int(i)] for i in tri]


def triangles(brush):
    vertices = np.asarray(brush.vertices, float)
    for fi, face in enumerate(brush.faces):
        for tri in face_triangles(vertices, face.indices):
            yield fi, tri


def uv_for(points, face, n):
    # World-aligned projection stays continuous across CSG splits.
    axis = int(np.argmax(np.abs(n)))
    axes = [(1,2),(0,2),(0,1)][axis]
    uv = np.asarray(points)[:,axes].copy()
    if face.uv_axes is not None:
        mapping = np.asarray(face.uv_axes)
        uv = np.asarray(points) @ mapping[:,:3].T + mapping[:,3]
    angle = math.radians(face.rotation)
    uv = uv @ np.array([[math.cos(angle),math.sin(angle)],[-math.sin(angle),math.cos(angle)]])
    return uv / np.asarray(face.scale) + np.asarray(face.offset)


def validate_brush(brush):
    v = np.asarray(brush.vertices, dtype=float)
    for f in brush.faces:
        p = v[f.indices]
        n = normal(p)
        if np.max(np.abs((p-p[0]) @ n)) > 0.01:
            raise ValueError(f'{brush.name}: non-planar face. Move a whole face/edge or triangulate first.')
        for i in range(len(p)):
            if np.dot(np.cross(p[(i+1)%len(p)]-p[i], p[(i+2)%len(p)]-p[(i+1)%len(p)]), n) < -1e-6:
                raise ValueError(f'{brush.name}: concave face. Triangulate before this edit.')
    if brush.kind=='mesh':return
    m = to_manifold(brush, {})
    if m.volume() <= 1e-5:
        raise ValueError(f'{brush.name}: zero or inverted volume.')


def to_manifold(brush, sources):
    if brush.kind=='mesh':
        raise ValueError('Imported BSP meshes support face and vertex edits; CSG and clipping require solid brushes or rooms.')
    ts, ids = [], []
    v = np.asarray(brush.vertices, dtype=np.float32)
    face_ids = []
    for f in brush.faces:
        fid = len(sources)
        sources[fid] = (copy.deepcopy(f), normal(v[f.indices]), brush.id)
        face_ids.append(fid)
    for fi, tri in triangles(brush):
        ts.append(tri)
        ids.append(face_ids[fi])
    mesh = md.Mesh(vert_properties=v, tri_verts=np.array(ts,dtype=np.uint32), face_id=np.array(ids,dtype=np.uint32))
    result = md.Manifold(mesh)
    if result.status() != md.Error.NoError:
        raise ValueError(f'{brush.name}: mesh is not a closed manifold ({result.status()}).')
    return result


@dataclass
class Surface:
    points: np.ndarray
    normal: np.ndarray
    uv: np.ndarray
    material: str
    brush_id: str
    flags: str = ''


def world_surfaces(project):
    project.validate()
    sources, rooms, solids, imported = {}, [], [], []
    for brush in project.brushes:
        validate_brush(brush)
        if brush.kind=='mesh':
            vertices = np.asarray(brush.vertices,float)
            for fi,tri in triangles(brush):
                face = brush.faces[fi];points = vertices[tri];n = normal(points)
                imported.append(Surface(points,n,uv_for(points,face,n),face.material,brush.id,face.flags))
            continue
        (rooms if brush.kind == 'room' else solids).append(to_manifold(brush,sources))
    if not rooms:
        raise ValueError('Create a Room to enclose playable space before exporting a level.')
    result = md.Manifold.batch_boolean(rooms, md.OpType.Add)
    if solids:
        result = result - md.Manifold.batch_boolean(solids, md.OpType.Add)
    if result.status() != md.Error.NoError or result.is_empty():
        raise ValueError('Room/solid subtraction left no valid playable volume.')
    mesh = result.to_mesh()
    output = imported
    for tri, fid in zip(mesh.tri_verts, mesh.face_id):
        face, src_normal, brush_id = sources[int(fid)]
        points = mesh.vert_properties[tri[::-1],:3].astype(float)
        output.append(Surface(points, normal(points), uv_for(points,face,src_normal), face.material,brush_id,face.flags))
    return output


def from_manifold(result, sources, name, kind='solid'):
    if result.is_empty() or result.status() != md.Error.NoError:
        raise ValueError('Operation removed the entire brush.')
    mesh = result.to_mesh()
    faces = []
    for tri, fid in zip(mesh.tri_verts,mesh.face_id):
        face = copy.deepcopy(sources[int(fid)][0]) if int(fid) in sources else Face([])
        face.indices = [int(x) for x in tri]
        faces.append(face)
    return Brush(name,mesh.vert_properties[:,:3].astype(float).tolist(),faces,kind)


def boolean(a,b,operation):
    if a.kind != b.kind:
        raise ValueError('Select two solids or two rooms for this operation.')
    sources={}
    ma,mb = to_manifold(a,sources),to_manifold(b,sources)
    result = {'union':lambda:ma+mb,'subtract':lambda:ma-mb,'intersect':lambda:ma^mb}[operation]()
    return from_manifold(result,sources,operation.title(),a.kind)


def subdivide(brush, divisions=4, face_indices=None):
    """Triangulated quad/triangle grids, sharing boundary vertices with adjacent faces."""
    if type(divisions) is not int or not 2 <= divisions <= 32:
        raise ValueError('Subdivision needs 2–32 segments per edge.')
    selected = set(range(len(brush.faces))) if face_indices is None else set(face_indices)
    if not selected or any(type(i) is not int or not 0 <= i < len(brush.faces) for i in selected):
        raise ValueError('Select valid faces to subdivide.')
    # Bound the work before allocation, including stitched neighboring faces.
    estimate = sum((2 if len(f.indices)==4 else len(f.indices)-2)*divisions**2
                   if i in selected else len(f.indices)*divisions
                   for i,f in enumerate(brush.faces))
    if estimate > 100000 or len(brush.vertices)+estimate > 100000:
        raise ValueError('Subdivision would exceed the 100,000 vertex/face limit. Use fewer segments or faces.')
    validate_brush(brush)
    result = copy.deepcopy(brush)
    vertices = np.asarray(brush.vertices, float)
    result.faces = []
    cache = {((i,1.0),): i for i in range(len(vertices))}

    def point(weights):
        key = tuple(sorted((i,round(w,12)) for i,w in weights.items() if w > 1e-12))
        if key not in cache:
            cache[key] = len(result.vertices)
            result.vertices.append(sum(vertices[i]*w for i,w in weights.items()).tolist())
        return cache[key]

    def face(source, indices):
        f = copy.deepcopy(source); f.indices = indices; result.faces.append(f)

    def triangle_grid(source, a, b, c):
        grid = {(i,j): point({a:1-(i+j)/divisions,b:i/divisions,c:j/divisions})
                for i in range(divisions+1) for j in range(divisions+1-i)}
        for i in range(divisions):
            for j in range(divisions-i):
                face(source,[grid[i,j],grid[i+1,j],grid[i,j+1]])
                if i+j < divisions-1:
                    face(source,[grid[i+1,j],grid[i+1,j+1],grid[i,j+1]])

    edges = set()
    for i in selected:
        ids = brush.faces[i].indices
        edges.update(tuple(sorted((a,b))) for a,b in zip(ids,ids[1:]+ids[:1]))
    for i,source in enumerate(brush.faces):
        ids = source.indices
        if i in selected:
            quad = len(ids)==4
            if quad:
                # A stitched triangle can have four indices but only three corners.
                sides = np.roll(vertices[ids],-1,axis=0)-vertices[ids]
                quad = np.all(np.linalg.norm(np.cross(sides,np.roll(sides,-1,axis=0)),axis=1)>1e-8)
            if quad:
                a,b,c,d = ids
                grid = {}
                for y in range(divisions+1):
                    for x in range(divisions+1):
                        u,v = x/divisions,y/divisions
                        grid[x,y] = point({a:(1-u)*(1-v),b:u*(1-v),c:u*v,d:(1-u)*v})
                for y in range(divisions):
                    for x in range(divisions):
                        a,b,c,d = grid[x,y],grid[x+1,y],grid[x+1,y+1],grid[x,y+1]
                        face(source,[a,b,c]); face(source,[a,c,d])
            else:
                for tri in face_triangles(vertices,ids):
                    triangle_grid(source,*tri)
        else:
            boundary = []
            for a,b in zip(ids,ids[1:]+ids[:1]):
                boundary.append(a)
                if tuple(sorted((a,b))) in edges:
                    boundary.extend(point({a:1-t/divisions,b:t/divisions}) for t in range(1,divisions))
            face(source,boundary)
    validate_brush(result)
    return result


def clip_brushes(brush, plane_normal, offset, mode='left'):
    """Positive half-space is left of the directed line in an orthographic view."""
    if mode not in ('left','right','both'):
        raise ValueError('Choose Keep Left, Keep Right, or Keep Both.')
    n = np.asarray(plane_normal,float)
    if n.shape != (3,) or not np.isfinite(n).all() or np.linalg.norm(n) < 1e-6 or not math.isfinite(offset):
        raise ValueError('Clipping plane must be finite with a nonzero normal.')
    n /= np.linalg.norm(n)
    validate_brush(brush)
    distances = np.asarray(brush.vertices)@n-offset
    low,high = float(np.min(distances)),float(np.max(distances))
    if mode=='both' and (low>=-1e-7 or high<=1e-7):
        raise ValueError('Keep Both needs a plane that cuts through the brush.')
    if (mode=='left' and low>=-1e-7) or (mode=='right' and high<=1e-7):
        return [copy.deepcopy(brush)]
    if (mode=='left' and high<=1e-7) or (mode=='right' and low>=-1e-7):
        raise ValueError('Operation removed the entire brush.')
    sources = {}
    mesh = to_manifold(brush,sources)
    if mode=='both':
        halves = list(zip(('left','right'),mesh.split_by_plane(n.tolist(),float(offset))))
        if any(m.is_empty() for _,m in halves):
            raise ValueError('Keep Both needs a plane that cuts through the brush.')
    else:
        direction = 1 if mode=='left' else -1
        halves = [(mode,mesh.trim_by_plane((n*direction).tolist(),float(offset)*direction))]
    output = []
    tolerance = max(1e-5,float(np.max(np.abs(brush.vertices)))*2e-7)
    for side,m in halves:
        clipped = from_manifold(m,sources,brush.name+' '+side,brush.kind)
        vertices = np.asarray(clipped.vertices)
        for i,f in enumerate(clipped.faces):
            points = vertices[f.indices]
            if np.max(np.abs(points@n-offset)) <= tolerance and abs(float(normal(points)@n))>1-1e-5:
                # Generated caps have no source face; inherit the first face's full mapping.
                cap = copy.deepcopy(brush.faces[0]); cap.indices = f.indices; clipped.faces[i] = cap
        validate_brush(clipped)
        output.append(clipped)
    return output


def clip(brush, plane_normal, offset):
    return clip_brushes(brush,plane_normal,offset)[0]


def demo(hek='', materials=None):
    materials = materials or ['', '', '']
    p=Project(name='BlamHammer test room',hek=hek,level_dir='levels\\blamhammer\\blamhammer_demo',bsp='blamhammer_demo')
    room=primitive('room',(0,0,400),(1600,2000,800),materials[0])
    room.name='Room · four walls, floor, ceiling'
    room.faces[0].material=materials[1]
    platform=primitive('box',(300,300,100),(400,400,200),materials[2])
    platform.name='Raised platform'
    ramp=primitive('ramp',(300,-100,100),(400,400,200),materials[2])
    ramp.name='Ramp to platform'
    p.brushes=[room,platform,ramp]
    p.markers=[Marker(position=[-300,-400,50],team=0),Marker(name='Blue start',position=[-300,400,50],team=1,yaw=180)]
    return p
