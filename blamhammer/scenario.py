"""Write only editor-owned scenarios, with external-edit detection and backups."""
from pathlib import Path, PureWindowsPath
import hashlib
import json
import math
import os
import shutil
from reclaimer.hek.defs import scnr
from .model import atomic_write
from .toolchain import beneath


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ownership_file(path):
    return Path(str(path)+'.blamhammer.json')


def claim_new_scenario(path):
    atomic_write(ownership_file(path),json.dumps({'sha256':digest(path)}))


def synchronize(project, path):
    path=Path(path)
    state=ownership_file(path)
    if not state.is_file() or json.loads(state.read_text())['sha256']!=digest(path):
        raise ValueError('Scenario is not editor-owned or was changed externally. Open it in Sapien/Guerilla; use the placement guide to preserve those edits.')
    tag=scnr.get().build(filepath=path)
    d=tag.data.tagdata
    expected=project.level_dir+'\\'+project.bsp
    bsp_index=next((i for i,b in enumerate(d.structure_bsps.STEPTREE) if b.structure_bsp.filepath.lower()==expected.lower()),None)
    if bsp_index is None:
        raise ValueError('The scenario does not reference this project BSP.')
    d.type.set_to(project.scenario_type)
    for field in ('skies','player_starting_locations','sceneries','sceneries_palette','vehicles','vehicles_palette',
                  'weapons','weapons_palette','netgame_equipments'):
        getattr(d,field).STEPTREE.clear()
    if project.sky:
        sky=project.sky.removesuffix('.sky')
        if not beneath(Path(project.hek)/'tags',sky+'.sky').is_file():
            raise ValueError('Sky tag not found: '+project.sky)
        d.skies.STEPTREE.append()
        d.skies.STEPTREE[-1].sky.filepath=sky
    counts={kind:sum(m.kind==kind for m in project.markers) for kind in ('player_start','weapon','vehicle','scenery')}
    for kind,limit in [('player_start',256),('weapon',128),('vehicle',80),('scenery',2000)]:
        if counts[kind]>limit:
            raise ValueError(f'{kind}: H1 limit is {limit}.')
    for m in project.markers:
        if m.kind=='player_start':
            d.player_starting_locations.STEPTREE.append()
            item=d.player_starting_locations.STEPTREE[-1]
            item.position[:]=[x/100 for x in m.position]
            item.facing=math.radians(m.yaw)
            item.team_index=m.team
            item.bsp_index=bsp_index
            item.type_0.set_to('all_games' if project.scenario_type=='multiplayer' else 'none')
            continue
        suffix={'scenery':'.scenery','vehicle':'.vehicle','weapon':'.item_collection' if project.scenario_type=='multiplayer' else '.weapon'}[m.kind]
        if not m.tag.endswith(suffix) or not beneath(Path(project.hek)/'tags',m.tag).is_file():
            raise ValueError(f'{m.name}: choose an existing {suffix} tag.')
        ref=str(PureWindowsPath(m.tag).with_suffix(''))
        if m.kind=='weapon' and project.scenario_type=='multiplayer':
            d.netgame_equipments.STEPTREE.append()
            item=d.netgame_equipments.STEPTREE[-1]
            item.item_collection.filepath=ref
            item.position[:]=[x/100 for x in m.position]
            item.facing=math.radians(m.yaw)
            item.type_0.set_to('all_games')
            item.team_index=m.team
        else:
            field={'scenery':'sceneries','vehicle':'vehicles','weapon':'weapons'}[m.kind]
            palette=getattr(d,field+'_palette').STEPTREE
            found=next((i for i,p in enumerate(palette) if p.name.filepath==ref),None)
            if found is None:
                if len(palette)>=100:
                    raise ValueError('Object palette exceeds 100 tags.')
                palette.append(); palette[-1].name.filepath=ref
                found=len(palette)-1
            block=getattr(d,field).STEPTREE
            block.append(); item=block[-1]
            item.type=found
            item.position[:]=[x/100 for x in m.position]
            item.rotation[:]=[math.radians(m.yaw),0,0]
            if m.kind=='vehicle':
                item.body_vitality=1.0
                item.multiplayer_team_index=m.team
                item.multiplayer_spawn_flags.data=0x0f0f
    temporary=Path(str(path)+'.blamhammer.tmp')
    try:
        tag.serialize(filepath=temporary,backup=False,temp=False)
        check=scnr.get().build(filepath=temporary)
        if len(check.data.tagdata.player_starting_locations.STEPTREE)!=counts['player_start']:
            raise ValueError('Scenario verification failed; original kept.')
        shutil.copy2(path,str(path)+'.blamhammer.bak')
        os.replace(temporary,path)
        claim_new_scenario(path)
    finally:
        temporary.unlink(missing_ok=True)
    return len(project.markers)
