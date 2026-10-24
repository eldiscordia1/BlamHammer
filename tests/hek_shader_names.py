"""Opt-in HCEEK regression: both installed grass shaders in one compiled map."""
import hashlib
import json
from pathlib import Path
from reclaimer.hek.defs import sbsp
from blamhammer.geometry import demo
from blamhammer.jms import material_names
from blamhammer.toolchain import Toolchain,detect_hek,beneath

root=Path(__file__).resolve().parent.parent
grasses=['digsite\\levels\\dusk\\shaders\\grass.shader_environment',
         'digsite\\levels\\indoor\\_dig\\shaders\\grass.shader_environment']
panel='levels\\test\\tutorial\\shaders\\example_tutorial_panels.shader_environment'
p=demo(hek=detect_hek(),materials=grasses+[panel])
assert p.hek,'HCEEK is required.'
p.level_dir='levels\\blamhammer\\blamhammer_shader_verify';p.bsp='blamhammer_shader_verify'
p.sky='sky\\sky_icefields\\sky_icefields'
before=p.to_dict();tags=Path(p.hek)/'tags'
sources=[beneath(tags,g) for g in grasses]
originals=[hashlib.sha256(f.read_bytes()).hexdigest() for f in sources]
t=Toolchain(p);t.compile_scenario();t.lightmaps();output=t.build_map()
aliases=material_names(grasses,p.hek)
expected={'blamhammer\\shaders\\'+n for n in aliases}|{str(Path(panel).with_suffix(''))}
d=sbsp.get().build(filepath=t.bsp).data.tagdata
render={m.shader.filepath for lm in d.lightmaps.STEPTREE for m in lm.materials.STEPTREE}
collision={m.shader.filepath for m in d.collision_materials.STEPTREE}
assert render==expected,(render,expected)
assert collision==expected,(collision,expected)
for source,name in zip(sources,aliases):
    assert source.read_bytes()==(tags/'blamhammer/shaders'/(name+source.suffix)).read_bytes()
assert [hashlib.sha256(f.read_bytes()).hexdigest() for f in sources]==originals
assert p.to_dict()==before
result={'status':'passed','selected_shaders':grasses,'compiled_shader_references':sorted(render),
        'original_tags_unchanged':True,'project_unchanged':True,'map':str(output),'map_bytes':output.stat().st_size}
(root/'artifacts/shader_names_verification.json').write_text(json.dumps(result,indent=2))
print('REAL HCEEK DUPLICATE SHADER PASS',result)
