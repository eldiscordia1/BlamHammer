from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import copy
import json
import math
import os
import re
import shutil
import tempfile
import uuid


def uid():
    return uuid.uuid4().hex


def tag_path(value: str) -> str:
    value = value.replace('/', '\\').strip()
    if not value or any(p in ('', '.', '..') for p in value.split('\\')):
        raise ValueError('Tag path must be relative, with no empty or parent components.')
    if any(c in value for c in ':<>"|?*\r\n\t') or value.startswith('\\'):
        raise ValueError('Invalid tag path.')
    return value


@dataclass
class Face:
    indices: list[int]
    material: str = ''
    scale: list[float] = field(default_factory=lambda: [100.0, 100.0])
    offset: list[float] = field(default_factory=lambda: [0.0, 0.0])
    rotation: float = 0.0
    uv_axes: list[list[float]] | None = None
    flags: str = ''


@dataclass
class Brush:
    name: str
    vertices: list[list[float]]
    faces: list[Face]
    kind: str = 'solid'
    id: str = field(default_factory=uid)


@dataclass
class Marker:
    name: str = 'Player start'
    kind: str = 'player_start'
    position: list[float] = field(default_factory=lambda: [0.0, 0.0, 50.0])
    yaw: float = 0.0
    team: int = 0
    tag: str = ''
    id: str = field(default_factory=uid)


@dataclass
class Project:
    name: str = 'untitled'
    brushes: list[Brush] = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)
    grid: float = 25.0
    snap: bool = True
    hek: str = ''
    level_dir: str = 'levels\\blamhammer\\untitled'
    bsp: str = 'untitled'
    scenario_type: str = 'multiplayer'
    sky: str = ''
    author: str = ''
    notes: str = ''
    version: int = 1

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or data.get('version') != 1:
            raise ValueError('Unsupported project format (expected version 1).')
        d = copy.deepcopy(data)
        try:
            d['brushes'] = [Brush(**dict(b, faces=[Face(**f) for f in b['faces']])) for b in d['brushes']]
            d['markers'] = [Marker(**m) for m in d['markers']]
            result = cls(**d)
            result.validate()
            return result
        except (TypeError, KeyError, OverflowError) as exc:
            raise ValueError(f'Invalid project data: {exc}') from exc

    def validate(self):
        def vector(v, size):
            if not isinstance(v, list) or len(v) != size or any(
                not isinstance(x, (int, float)) or not math.isfinite(x) or abs(x) > 1e7 for x in v
            ):
                raise ValueError('Invalid or non-finite coordinates.')
        if not math.isfinite(self.grid) or not 0.01 <= self.grid <= 10000:
            raise ValueError('Grid must be between 0.01 and 10000.')
        tag_path(self.level_dir)
        if not re.fullmatch(r'[a-z0-9_]{1,48}', self.bsp):
            raise ValueError('BSP name needs 1–48 lowercase letters, digits or underscores.')
        if self.scenario_type not in ('multiplayer', 'singleplayer'):
            raise ValueError('Invalid scenario type.')
        if self.sky:
            tag_path(self.sky)
        ids = set()
        if len(self.brushes) > 10000 or len(self.markers) > 10000:
            raise ValueError('Project exceeds 10,000 brushes or markers.')
        for obj in self.brushes + self.markers:
            if not isinstance(obj.id, str) or obj.id in ids:
                raise ValueError('Object IDs must be unique strings.')
            ids.add(obj.id)
        for b in self.brushes:
            minimum = 3 if b.kind=='mesh' else 4
            if b.kind not in ('solid', 'room', 'mesh') or not minimum <= len(b.vertices) <= 100000:
                raise ValueError('Invalid brush type or vertex count.')
            for p in b.vertices:
                vector(p, 3)
            if not (1 if b.kind=='mesh' else 4) <= len(b.faces) <= 100000:
                raise ValueError('Invalid face count.')
            for f in b.faces:
                if len(f.indices) < 3 or len(set(f.indices)) != len(f.indices) or any(
                    type(i) is not int or not 0 <= i < len(b.vertices) for i in f.indices
                ):
                    raise ValueError('Invalid face indices.')
                vector(f.scale, 2)
                vector(f.offset, 2)
                if not isinstance(f.flags,str) or any(c not in '!%@*^-' for c in f.flags):
                    raise ValueError('Invalid face surface flags.')
                if f.uv_axes is not None:
                    if not isinstance(f.uv_axes,list) or len(f.uv_axes)!=2:
                        raise ValueError('Invalid imported texture mapping.')
                    for axis in f.uv_axes:vector(axis,4)
                if min(abs(x) for x in f.scale) < 0.001 or not math.isfinite(f.rotation):
                    raise ValueError('Texture scale must be nonzero; rotation must be finite.')
                if f.material and f.material != '+sky':
                    tag_path(f.material)
        for m in self.markers:
            vector(m.position, 3)
            if m.kind not in ('player_start', 'weapon', 'vehicle', 'scenery'):
                raise ValueError('Unknown marker type.')
            if m.team not in (0, 1) or not math.isfinite(m.yaw):
                raise ValueError('Invalid marker team or angle.')
            if m.tag:
                tag_path(m.tag)


def atomic_write(path, content: str, backup=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if backup and path.exists():
            shutil.copy2(path, str(path) + '.bak')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save(project, path):
    project.validate()
    atomic_write(path, json.dumps(project.to_dict(), indent=2, ensure_ascii=False, allow_nan=False) + '\n', True)


def load(path):
    path = Path(path)
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('Project exceeds 64 MB.')
    return Project.from_dict(json.loads(path.read_text(encoding='utf-8-sig')))


class History:
    def __init__(self):
        self.undo_stack = []
        self.redo_stack = []

    def record(self, before):
        self.undo_stack.append(copy.deepcopy(before))
        del self.undo_stack[:-100]
        self.redo_stack.clear()

    def undo(self, current):
        if not self.undo_stack:
            return current
        self.redo_stack.append(current.to_dict())
        return Project.from_dict(self.undo_stack.pop())

    def redo(self, current):
        if not self.redo_stack:
            return current
        self.undo_stack.append(current.to_dict())
        return Project.from_dict(self.redo_stack.pop())
