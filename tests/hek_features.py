"""Opt-in real compiler check; writes only levels/blamhammer/blamhammer_features."""
import json
from pathlib import Path
from reclaimer.model.jms import read_jms
from blamhammer.model import load,save
from blamhammer.geometry import demo,primitive,subdivide,clip_brushes,validate_brush,world_surfaces
from blamhammer.toolchain import Toolchain,detect_hek

root=Path(__file__).resolve().parent.parent
p=demo(hek=detect_hek(),materials=['levels\\test\\tutorial\\shaders\\example_tutorial_'+name+'.shader_environment'
                                  for name in ('metal','metal_floor','panels')])
p.sky='sky\\sky_icefields\\sky_icefields'
p.markers[0].position=[-650,-650,50];p.markers[0].yaw=45
p.markers[1].position=[650,-650,50];p.markers[1].yaw=135
assert p.hek,'Install/extract HCEEK first.'
p.name='Subdivision and clip verification'
p.level_dir='levels\\blamhammer\\blamhammer_features';p.bsp='blamhammer_features'
terrain=primitive('box',(250,250,100),(500,600,200),p.brushes[1].faces[0].material)
terrain.name='Editable terrain grid'
terrain.faces[1].material=p.brushes[0].faces[0].material
terrain.faces[1].scale=[150,125];terrain.faces[1].offset=[.25,.5];terrain.faces[1].rotation=15
terrain=subdivide(terrain,6,[1])
for v in terrain.vertices:
    if abs(v[2]-200)<1e-6 and abs(v[0]-250)<249 and abs(v[1]-250)<299:
        v[2]=200+125*(1-abs(v[0]-250)/250)*(1-abs(v[1]-250)/300)
halves=clip_brushes(terrain,[1,1,0],350,'both')
for b,delta in zip(halves,(35,-35)):
    for v in b.vertices:v[0]+=delta
    validate_brush(b)
left=clip_brushes(primitive('box',(-400,300,75),(300,300,150),terrain.faces[0].material),[1,1,0],-100,'left')[0]
right=clip_brushes(primitive('box',(-400,-300,75),(300,300,150),terrain.faces[0].material),[1,1,0],-500,'right')[0]
light=primitive('box',(0,0,790),(200,200,20),p.brushes[0].faces[0].material)
light.name='Ceiling light'
light.faces[0].material='levels\\test\\tutorial\\shaders\\example_tutorial_lights_blue.shader_transparent_chicago'
p.brushes=[p.brushes[0],light]+halves+[left,right]
path=root/'examples/subdivision_clip.hceproj';save(p,path);p=load(path)
t=Toolchain(p);t.compile_scenario();t.lightmaps();output=t.build_map()
jms=t.root/'data'/Path(*p.level_dir.split('\\'))/'models'/f'{p.bsp}.jms'
parsed=read_jms(jms.read_text());surfaces=world_surfaces(p)
assert parsed is not None and len(parsed.tris)==len(surfaces)
assert len(parsed.materials)>=3
result={'status':'passed','tool_build':'2023.07.17.176677.1-QFE1','triangles':len(surfaces),
        'materials':len(parsed.materials),'bsp_bytes':t.bsp.stat().st_size,'map_bytes':output.stat().st_size,
        'jms':str(jms),'bsp':str(t.bsp),'map':str(output),'project':str(path),
        'checks':['selected-face subdivision','deformed terrain','keep left','keep right','keep both separated',
                  'closed caps','materials and UVs','save/reload','independent JMS parser','structure','lightmaps','MAP']}
(root/'artifacts/features_verification.json').write_text(json.dumps(result,indent=2))
print('REAL HCEEK FEATURE VERIFICATION PASS',result)
