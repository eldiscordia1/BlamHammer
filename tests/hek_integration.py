"""Opt-in integration test: writes only levels/blamhammer/blamhammer_verify."""
import json
from pathlib import Path
import tempfile
from reclaimer.hek.defs import scnr
from blamhammer.model import load,save,Marker
from blamhammer.app import ROOT
from blamhammer.toolchain import Toolchain,detect_hek
from blamhammer.scenario import synchronize
from blamhammer.materials import preview,decode_bitmap
from blamhammer.geometry import demo,world_surfaces

p=demo(hek=detect_hek(),materials=['levels\\test\\tutorial\\shaders\\example_tutorial_'+name+'.shader_environment'
                                  for name in ('metal','metal_floor','panels')])
p.sky='sky\\sky_icefields\\sky_icefields'
assert p.hek,'HCEEK is required for this test.'
p.level_dir='levels\\blamhammer\\blamhammer_verify';p.bsp='blamhammer_verify'
p.markers += [Marker(name='Weapon',kind='weapon',position=[0,-300,50],tag='item collections\\single weapons\\assault rifle.item_collection'),
              Marker(name='Vehicle',kind='vehicle',position=[-400,0,80],tag='vehicles\\warthog\\warthog.vehicle'),
              Marker(name='Scenery',kind='scenery',position=[400,-600,20],tag='scenery\\baton\\baton.scenery')]
with tempfile.TemporaryDirectory() as folder:
    file=Path(folder)/'roundtrip.hceproj';save(p,file);p=load(file)
    t=Toolchain(p);t.compile_scenario();t.lightmaps();output=t.build_map()
    d=scnr.get().build(filepath=t.scenario).data.tagdata
    assert d.type.enum_name=='multiplayer'
    spawn_count=sum(m.kind=='player_start' for m in p.markers)
    weapon_count=sum(m.kind=='weapon' for m in p.markers)
    assert len(d.player_starting_locations.STEPTREE)==spawn_count
    assert list(d.player_starting_locations.STEPTREE[0].position)==[v/100 for v in p.markers[0].position]
    assert len(d.netgame_equipments.STEPTREE)==weapon_count
    assert len(d.vehicles.STEPTREE)==1
    assert len(d.sceneries.STEPTREE)==1
    assert d.skies.STEPTREE[0].sky.filepath==p.sky
    image,info=preview(p.hek,p.brushes[0].faces[0].material)
    assert image is not None,info
    lighting=decode_bitmap(t.bsp.with_suffix('.bitmap'))
    assert max(max(pix[:3]) for pix in lighting.get_flattened_data())>0,'Entire lightmap is black'
    edited=Path(folder)/'external.scenario';edited.write_bytes(t.scenario.read_bytes())
    try:synchronize(p,edited)
    except ValueError:pass
    else:raise AssertionError('Unowned scenario was modified')
    surfaces=world_surfaces(p)
    result={'tool_build':'2023.07.17.176677.1-QFE1','surfaces':len(surfaces),'materials':len({s.material for s in surfaces}),'player_starts':spawn_count,
            'weapons':weapon_count,'vehicles':1,'scenery':1,'map_bytes':output.stat().st_size,
            'map':str(output),'lighting_nonblack':True,'save_reload':'passed','status':'passed'}
    (ROOT/'artifacts/hek_verification.json').write_text(json.dumps(result,indent=2))
    print('REAL HCEEK INTEGRATION PASS',result)
