from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from functools import lru_cache
import importlib
import numpy as np
from PIL import Image
from reclaimer.hek.defs import bitm
from .toolchain import beneath


SHADERS={'shader_environment':'senv','shader_model':'soso','shader_transparent_chicago':'schi',
         'shader_transparent_chicago_extended':'scex','shader_transparent_generic':'sotr',
         'shader_transparent_water':'swat','shader_transparent_glass':'sgla',
         'shader_transparent_meter':'smet','shader_transparent_plasma':'spla'}


@dataclass
class Material:
    path: str
    label: str


def scan_materials(root):
    tags=Path(root)/'tags'
    if not tags.is_dir():
        return []
    return [Material(str(p.relative_to(tags)).replace('/','\\'),p.stem)
            for p in sorted(tags.rglob('*.shader_*')) if p.suffix[1:] in SHADERS
            and not (p.parent==tags/'blamhammer/shaders' and p.stem.startswith('bh_'))]


def bitmap_references(node):
    if hasattr(node,'tag_class') and hasattr(node,'filepath'):
        if node.tag_class.enum_name=='bitmap' and node.filepath:
            yield node.desc['NAME'],node.filepath
        return
    if isinstance(node,list):
        for child in node:
            yield from bitmap_references(child)
        if hasattr(node,'STEPTREE'):
            yield from bitmap_references(node.STEPTREE)


def decode_bitmap(path):
    path=Path(path)
    if path.stat().st_size>256*1024*1024:
        raise ValueError('Bitmap exceeds preview size limit.')
    tag=bitm.get().build(filepath=path)
    data=tag.data.tagdata
    if not data.bitmaps.STEPTREE:
        raise ValueError('Bitmap contains no images.')
    b=data.bitmaps.STEPTREE[0]
    w,h=b.width,b.height
    if not 0<w<=8192 or not 0<h<=8192 or w*h>16777216:
        raise ValueError('Bitmap dimensions exceed preview limits.')
    if b.flags.swizzled:
        raise ValueError('Swizzled Xbox bitmap; use its source TIFF for preview.')
    raw=bytes(data.processed_pixel_data.data)[b.pixels_offset:]
    fmt=b.format.enum_name
    if fmt in ('dxt1','dxt3','dxt5'):
        n={'dxt1':1,'dxt3':2,'dxt5':3}[fmt]
        return Image.frombytes('RGBA',(w,h),raw,'bcn',(n,fmt.upper()))
    if fmt in ('a8r8g8b8','x8r8g8b8'):
        return Image.frombytes('RGBA',(w,h),raw,'raw','BGRA' if fmt=='a8r8g8b8' else 'BGRX')
    if fmt in ('y8','a8','ay8'):
        return Image.frombytes('L',(w,h),raw).convert('RGBA')
    if fmt=='a8y8':
        a=np.frombuffer(raw[:w*h*2],dtype=np.uint8).reshape(h,w,2)
        return Image.fromarray(np.stack([a[:,:,0]]*3+[a[:,:,1]],axis=2),'RGBA')
    if fmt in ('r5g6b5','a1r5g5b5','a4r4g4b4'):
        packed=np.frombuffer(raw[:w*h*2],dtype='<u2').reshape(h,w)
        if fmt=='r5g6b5':
            channels=[((packed>>11)&31)*255//31,((packed>>5)&63)*255//63,(packed&31)*255//31,np.full_like(packed,255)]
        elif fmt=='a1r5g5b5':
            channels=[((packed>>10)&31)*255//31,((packed>>5)&31)*255//31,(packed&31)*255//31,(packed>>15)*255]
        else:
            channels=[((packed>>8)&15)*17,((packed>>4)&15)*17,(packed&15)*17,(packed>>12)*17]
        return Image.fromarray(np.stack(channels,axis=2).astype(np.uint8),'RGBA')
    raise ValueError(f'Preview unsupported for bitmap format {fmt}; shader remains exportable.')


@lru_cache(maxsize=256)
def preview(root,material):
    if material in ('','+sky'):
        return None,'Unassigned' if not material else '+sky · special Halo surface'
    try:
        path=beneath(Path(root)/'tags',material)
        module=importlib.import_module('reclaimer.hek.defs.'+SHADERS[path.suffix[1:]])
        tag=module.get().build(filepath=path)
        refs=list(bitmap_references(tag.data.tagdata))
        refs.sort(key=lambda ref: 0 if ref[0]=='base_map' else 1)
        if not refs:
            return None,'Shader has no bitmap dependency.'
        reference=refs[0][1]
        bitmap=beneath(Path(root)/'tags',reference+'.bitmap')
        try:
            img=decode_bitmap(bitmap)
        except (OSError,ValueError,IndexError) as decode_error:
            source=beneath(Path(root)/'data',reference+'.tif')
            if not source.is_file():
                raise decode_error
            with Image.open(source) as original:
                img=original.convert('RGBA')
        img.thumbnail((512,512))
        return img.convert('RGBA'),'Base texture: '+reference
    except Exception as exc:
        return None,f'Preview unavailable: {exc}'
