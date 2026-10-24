"""Opt-in BSP round trip using installed stock tags; outputs stay under blamhammer."""
from pathlib import Path,PureWindowsPath
import hashlib
import json
import numpy as np
from reclaimer.hek.defs.sbsp import sbsp_def
from blamhammer.bsp import import_bsp
from blamhammer.jms import material_names
from blamhammer.model import Marker,save,load
from blamhammer.toolchain import detect_hek,Toolchain

root=Path(__file__).resolve().parent.parent
hek=Path(detect_hek());results=[]


def render_vertices(data):
    groups={}
    for lm in data.lightmaps.STEPTREE:
        for m in lm.materials.STEPTREE:
            if not m.vertices_count:continue
            values=np.frombuffer(m.uncompressed_vertices.data,dtype='<f4',count=m.vertices_count*14).reshape(-1,14)
            groups.setdefault(m.shader.filepath+'.'+m.shader.tag_class.enum_name,[]).append(values)
    return {k:np.concatenate(v) for k,v in groups.items()}


for name in ('tutorial','bloodgulch'):
    source=hek/f'tags/levels/test/{name}/{name}.scenario_structure_bsp'
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    project=import_bsp(source,str(hek))
    project.bsp='bsp_import_verification_'+name;project.level_dir='levels\\blamhammer\\'+project.bsp
    if name=='tutorial':project.markers=[Marker(position=[0,0,400])]
    file=root/f'artifacts/imported_{name}.hceproj';save(project,file);project=load(file)
    logs=[];chain=Toolchain(project,logs.append)
    try:
        chain.compile_scenario()
        original=sbsp_def.build(filepath=source).data.tagdata
        rebuilt=sbsp_def.build(filepath=chain.bsp).data.tagdata
        assert len(original.surfaces.STEPTREE)==len(rebuilt.surfaces.STEPTREE),'Render triangle count changed'
        first,last=render_vertices(original),render_vertices(rebuilt)
        names=material_names(list(first),str(hek));max_position=max_uv=0.
        for (material,vertices),exported in zip(first.items(),names):
            ref=('blamhammer\\shaders\\'+exported+PureWindowsPath(material).suffix
                 if exported!=PureWindowsPath(material).stem else material)
            candidates=last[ref]
            for vertex in vertices:
                distance=np.max(abs(candidates[:,:3]-vertex[:3]),axis=1)
                assert distance.min()<.0001,'Imported vertex moved at Halo scale'
                error=np.max(abs(candidates[distance<.0001,12:14]-vertex[12:14]),axis=1).min()
                assert error<1e-5,'Texture coordinates changed'
                max_position=max(max_position,float(distance.min()));max_uv=max(max_uv,float(error))
        result={'source':str(source),'render_triangles':len(rebuilt.surfaces.STEPTREE),
                'max_world_position_error':max_position,'max_uv_error':max_uv,
                'collision_surfaces':len(rebuilt.collision_bsp.STEPTREE[0].surfaces.STEPTREE),
                'bsp':str(chain.bsp),'project':str(file)}
        if name=='tutorial':
            chain.lightmaps();output=chain.build_map();result['map']=str(output);result['map_bytes']=output.stat().st_size
        assert hashlib.sha256(source.read_bytes()).hexdigest()==before,'Source BSP was modified'
        results.append(result);print('PASS',name,result,flush=True)
    finally:(root/f'artifacts/{name}_import_build.log').write_text('\n'.join(logs),encoding='utf-8')
(root/'artifacts/bsp_import_verification.json').write_text(json.dumps({'status':'passed','results':results},indent=2))
