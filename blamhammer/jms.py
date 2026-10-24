from collections import Counter
import hashlib
from pathlib import Path, PureWindowsPath
import shutil
import numpy as np
from .geometry import world_surfaces
from .model import atomic_write


def material_names(materials, hek):
    names = [PureWindowsPath(m).stem if m!='+sky' else m for m in materials]
    requested = Counter(n.casefold() for n in names)
    tags = (Path(hek)/'tags').resolve()
    installed = {}
    if hek and tags.is_dir():
        for path in tags.rglob('*.shader_*'):
            installed.setdefault(path.stem.casefold(),[]).append(path.resolve())
    for i,(material,name) in enumerate(zip(materials,names)):
        if material=='+sky' or max(requested[name.casefold()],len(installed.get(name.casefold(),[])))<2:
            continue
        source = tags.joinpath(*PureWindowsPath(material).parts).resolve()
        if not hek or not source.is_relative_to(tags) or not source.is_file():
            raise ValueError(f'Configure HCEEK with the selected shader to resolve duplicate names: {material}')
        # Tool matches basenames; a stable private copy preserves the exact selected shader.
        key = str(PureWindowsPath(material)).casefold().encode('utf-8')
        alias = 'bh_'+hashlib.sha256(key).hexdigest()[:24]+'_s'
        target = (tags/'blamhammer/shaders'/(alias+source.suffix)).resolve()
        if not target.is_relative_to(tags) or any(p!=target for p in installed.get(alias,[])):
            raise ValueError(f'Generated shader alias conflicts with another tag: {alias}')
        target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists() or target.read_bytes()!=source.read_bytes():
            if target.exists():shutil.copy2(target,str(target)+'.blamhammer.bak')
            shutil.copy2(source,target)
        names[i] = alias
    return names


def export_jms(project, path):
    surfaces = world_surfaces(project)
    materials = list(dict.fromkeys((s.material,s.flags) for s in surfaces))
    shaders = list(dict.fromkeys(material for material,_ in materials))
    if '' in shaders:
        raise ValueError('Unassigned faces: apply real Halo shaders before exporting.')
    names = dict(zip(shaders,material_names(shaders,project.hek)))
    lines=['8200','0','1','frame','-1','-1','0\t0\t0\t1','0\t0\t0',str(len(materials))]
    for material,flags in materials:
        name=names[material]+flags
        if '\n' in name or '\r' in name:
            raise ValueError('Invalid material name.')
        lines.extend([name,'<none>'])
    lines += ['0','1','unnamed',str(3*len(surfaces))]
    def nums(values):
        return '\t'.join(f'{float(x):.9f}' for x in values)
    for s in surfaces:
        if not np.isfinite(s.uv).all():
            raise ValueError('Invalid UV coordinates.')
        for pos,uv in zip(s.points,s.uv):
            lines.extend(['0',nums(pos),nums(s.normal),'-1','0',nums([*uv,0])])
    lines.append(str(len(surfaces)))
    for i,s in enumerate(surfaces):
        lines.extend(['0',str(materials.index((s.material,s.flags))),f'{i*3}\t{i*3+1}\t{i*3+2}'])
    atomic_write(path,'\n'.join(lines)+'\n',backup=True)
    return len(surfaces)
