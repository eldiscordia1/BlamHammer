"""Read Halo 1 BSP tags through Reclaimer; source tags are never modified."""
from pathlib import Path
import re
import numpy as np
from reclaimer.hek.defs.sbsp import sbsp_def
from .model import Brush,Face,Project,tag_path
from .geometry import primitive,normal,face_triangles,validate_brush,bounds


def import_bsp(path, hek=''):
    path = Path(path)
    if path.suffix.lower()!='.scenario_structure_bsp':
        raise ValueError('Choose a Halo CE .scenario_structure_bsp tag, extracted from a MAP if necessary.')
    if not 64 <= path.stat().st_size <= 128*1024*1024:
        raise ValueError('BSP tag must be between 64 bytes and 128 MB.')
    with path.open('rb') as stream:header=stream.read(64)
    if header[36:40]!=b'sbsp' or header[60:64]!=b'blam' or int.from_bytes(header[56:58],'big')!=5:
        raise ValueError('Only Halo CE / HCEEK BSP tags are supported.')
    data = sbsp_def.build(filepath=path).data.tagdata
    vertices,faces,lookup = [],[],{}

    def vertex(point):
        point = tuple(float(x)*100 for x in point)
        if not np.isfinite(point).all() or max(abs(x) for x in point)>1e7:
            raise ValueError('BSP contains invalid coordinates.')
        if point not in lookup:
            if len(vertices)>=100000:raise ValueError('BSP exceeds the 100,000 vertex limit.')
            lookup[point]=len(vertices);vertices.append(list(point))
        return lookup[point]

    def add_face(indices, material, uv=None, flags=''):
        if len(faces)>=100000:raise ValueError('BSP exceeds the 100,000 face limit.')
        points = np.asarray([vertices[i] for i in indices])
        normal(points)
        face = Face(indices,material,flags=flags)
        if uv is not None:
            if not np.isfinite(uv).all():raise ValueError('BSP contains invalid texture coordinates.')
            # Affine coordinates retain the original mapping through edits and triangulation.
            gradient = np.linalg.lstsq(points[1:]-points[0],uv[1:]-uv[0],rcond=None)[0].T
            face.uv_axes = np.column_stack((gradient,uv[0]-gradient@points[0])).tolist()
            face.scale=[1.,1.]
        faces.append(face)

    surfaces = data.surfaces.STEPTREE
    for lightmap in data.lightmaps.STEPTREE:
        for material in lightmap.materials.STEPTREE:
            count,start,total = material.vertices_count,material.surfaces,material.surface_count
            if count<0 or count>100000 or start<0 or total<0 or start+total>len(surfaces):
                raise ValueError('BSP contains an invalid vertex or surface range.')
            if not total:continue
            shader = tag_path(material.shader.filepath+'.'+material.shader.tag_class.enum_name)
            raw = material.uncompressed_vertices.data
            stride,uv_offset = 14,12
            if not raw:
                raw = material.compressed_vertices.data;stride,uv_offset=8,6
            if len(raw)<count*stride*4:raise ValueError('BSP vertex data is truncated.')
            values = np.frombuffer(raw,dtype='<f4',count=count*stride).reshape(count,stride)
            ids = [vertex(p) for p in values[:,:3]]
            uv = values[:,uv_offset:uv_offset+2].astype(float).copy();uv[:,1]=1-uv[:,1]
            for surface in surfaces[start:start+total]:
                tri = list(reversed(surface))
                if any(i<0 or i>=count for i in tri):raise ValueError('BSP contains an invalid triangle index.')
                add_face([ids[i] for i in tri],shader,uv[tri],'!')

    if not faces:raise ValueError('BSP has no render geometry to import.')
    # Keep the actual collision shell, including sky, ladders and player clips.
    for collision in data.collision_bsp.STEPTREE:
        edges = collision.edges.STEPTREE
        two_sided = set()
        for si,surface in enumerate(collision.surfaces.STEPTREE):
            flags=''
            if surface.material==-1:
                shader='+sky'
            else:
                if not 0<=surface.material<len(data.collision_materials.STEPTREE):
                    raise ValueError('BSP contains an invalid collision material.')
                material=data.collision_materials.STEPTREE[surface.material].shader
                shader=tag_path(material.filepath+'.'+material.tag_class.enum_name)
                flags='*' if surface.flags.invisible else '@'
                for bit,symbol in (('two_sided','%'),('climbable','^'),('breakable','-')):
                    if getattr(surface.flags,bit):flags+=symbol
            ids,seen = [],set()
            edge_index=surface.first_edge
            while edge_index not in seen:
                if not 0<=edge_index<len(edges):raise ValueError('BSP contains an invalid collision boundary.')
                seen.add(edge_index);edge=edges[edge_index]
                if edge.left_surface==si:
                    vi=edge.start_vertex;edge_index=edge.forward_edge
                elif edge.right_surface==si:
                    vi=edge.end_vertex;edge_index=edge.reverse_edge
                else:raise ValueError('BSP collision boundary does not match its surface.')
                if not 0<=vi<len(collision.vertices.STEPTREE):raise ValueError('BSP contains an invalid collision vertex.')
                ids.append(vertex(collision.vertices.STEPTREE[vi][:3]))
            if edge_index!=surface.first_edge or len(ids)<3:raise ValueError('BSP collision boundary is not a closed polygon.')
            if '%' in flags:
                key=(shader,flags,frozenset(ids))
                if key in two_sided:continue
                # BSP stores both sides; Tool regenerates the reverse side from %.
                two_sided.add(key)
            points=np.asarray([vertices[i] for i in ids])
            for tri in face_triangles(points,list(range(len(ids)))):add_face([ids[i] for i in tri],shader,flags=flags)

    mesh = Brush(path.stem+' geometry',vertices,faces,'mesh')
    validate_brush(mesh)
    lo,hi = bounds(mesh)
    margin=max(100.,float(np.max(hi-lo))*.05)
    lo=np.floor((lo-margin)/25)*25;hi=np.ceil((hi+margin)/25)*25
    enclosure = primitive('room',(lo+hi)/2,hi-lo,'+sky');enclosure.name='Sky enclosure'
    # Use a separate output location so compiling an import cannot replace the source.
    name=(re.sub('[^a-z0-9_]','_',path.stem.lower()).strip('_') or 'bsp')[:39]+'_import'
    base=name;number=2
    while (Path(hek)/'tags/levels/blamhammer'/name/(name+'.scenario_structure_bsp')).exists():
        name=base[:42]+'_'+str(number);number+=1
    sky='sky\\clear afternoon\\clear afternoon'
    if not (Path(hek)/'tags'/Path(sky+'.sky')).is_file():sky=''
    project = Project(name=path.stem+' (imported)',brushes=[enclosure,mesh],hek=hek,sky=sky,
                      bsp=name,level_dir='levels\\blamhammer\\'+name)
    project.validate()
    return project
