from __future__ import annotations

from pathlib import Path, PureWindowsPath
import json
import os
import re
import shutil
import subprocess
import threading
import time
from .model import tag_path, atomic_write
from .jms import export_jms


def detect_hek():
    candidates = []
    if os.environ.get('HCEEK_ROOT'):
        candidates.append(Path(os.environ['HCEEK_ROOT']))
    steam = Path(os.environ.get('PROGRAMFILES(X86)',r'C:\Program Files (x86)'))/'Steam'
    libraries = [steam]
    config = steam/'steamapps/libraryfolders.vdf'
    if config.exists():
        libraries += [Path(p.replace('\\\\','\\')) for p in re.findall(r'"path"\s+"([^"]+)"',config.read_text())]
    candidates += [lib/'steamapps/common/HCEEK' for lib in libraries]
    return next((str(p) for p in candidates if (p/'tool.exe').is_file()),'')


def beneath(root, relative):
    relative = tag_path(relative)
    root = Path(root).resolve()
    result = root.joinpath(*relative.split('\\')).resolve()
    if not result.is_relative_to(root):
        raise ValueError('Path escapes the configured root.')
    return result


class Toolchain:
    def __init__(self, project, log=print):
        self.project=project
        self.root=Path(project.hek)
        self.log=log
        self.cancelled=threading.Event()
        self.process=None

    @property
    def scenario_ref(self):
        return self.project.level_dir+'\\'+PureWindowsPath(self.project.level_dir).name

    @property
    def scenario(self):
        return beneath(self.root/'tags',self.scenario_ref+'.scenario')

    @property
    def bsp(self):
        return beneath(self.root/'tags',self.project.level_dir+'\\'+self.project.bsp+'.scenario_structure_bsp')

    @property
    def jms(self):
        return beneath(self.root/'data',self.project.level_dir+'\\models\\'+self.project.bsp+'.jms')

    def validate(self):
        self.project.validate()
        if not (self.root/'tool.exe').is_file():
            raise ValueError('Configure the HCEEK folder containing tool.exe in Tools > Settings.')
        if not (self.root/'tags/globals/globals.globals').is_file():
            raise ValueError('HCEEK tags are not extracted. Run HCEEK (Extract).bat in the tools folder.')

    def validate_materials(self):
        materials={f.material for b in self.project.brushes for f in b.faces}
        for material in materials:
            if material=='+sky':
                continue
            if not material or not beneath(self.root/'tags',material).is_file():
                raise ValueError(f'Missing shader tag: {material or "unassigned face"}')

    def cancel(self):
        self.cancelled.set()
        if self.process and self.process.poll() is None:
            self.process.terminate()

    def run(self, args, outputs, fresh):
        self.validate()
        if self.cancelled.is_set():
            raise RuntimeError('Build cancelled.')
        before={p:p.stat().st_mtime_ns if p.exists() else None for p in fresh}
        for p in outputs:
            if p.exists():
                shutil.copy2(p,str(p)+'.blamhammer.bak')
        command=[str(self.root/'tool.exe'),*args]
        self.log('> '+subprocess.list2cmdline(command))
        logs=self.root/'reports/blamhammer'
        logs.mkdir(parents=True,exist_ok=True)
        log_file=logs/(time.strftime('%Y%m%d-%H%M%S')+'-'+args[0]+'.log')
        flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
        lines=[]
        with log_file.open('w',encoding='utf-8') as record:
            self.process=subprocess.Popen(command,cwd=self.root,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=flags)
            timer=threading.Timer(600,self.cancel)
            timer.start()
            try:
                for line in self.process.stdout:
                    line=line.rstrip()
                    record.write(line+'\n'); record.flush()
                    lines.append(line)
                    self.log(line)
                code=self.process.wait()
            finally:
                timer.cancel()
                self.process.stdout.close()
        self.log(f'Exit code: {code} · log: {log_file}')
        if self.cancelled.is_set():
            raise RuntimeError('Build cancelled or exceeded 10 minutes. Partial outputs must not be treated as successful.')
        if code!=0:
            raise RuntimeError(f'Tool failed (exit {code}). See {log_file}')
        if any(re.search(r'###\s*(?:ERROR|FAILED)|ASSERTION FAILED|FATAL ERROR',line,re.I) for line in lines):
            raise RuntimeError(f'Tool reported an error. See {log_file}')
        for p in outputs:
            if not p.is_file() or p.stat().st_size==0:
                raise RuntimeError(f'Tool did not produce a nonempty output: {p}')
        for p in fresh:
            if before[p]==p.stat().st_mtime_ns:
                raise RuntimeError(f'Tool left a stale output unchanged: {p}')
        self.log('Verified outputs: '+', '.join(str(p) for p in outputs))

    def build_bsp(self):
        self.validate()
        self.validate_materials()
        count=export_jms(self.project,self.jms)
        self.log(f'Exported {count} triangles to {self.jms}')
        new_scenario=not self.scenario.exists()
        self.run(['structure',self.project.level_dir,self.project.bsp],[self.bsp,self.scenario],[self.bsp])
        if new_scenario:
            from .scenario import claim_new_scenario
            claim_new_scenario(self.scenario)
        self.write_handoff()
        return self.scenario

    def compile_scenario(self):
        from .scenario import synchronize
        if not self.scenario.is_file():
            self.build_bsp()
        count=synchronize(self.project,self.scenario)
        self.log(f'Scenario synchronized and re-read: {count} placements, {self.project.scenario_type}.')
        self.build_bsp()
        self.write_handoff(synchronized=True)

    def lightmaps(self):
        if not self.scenario.is_file():
            raise ValueError('Build BSP before calculating lightmaps.')
        bitmap=self.bsp.with_suffix('.bitmap')
        self.run(['lightmaps',self.scenario_ref,self.project.bsp,'0','0.3'],[bitmap],[bitmap])

    def build_map(self):
        if not self.scenario.is_file():
            raise ValueError('Build BSP and prepare the scenario first.')
        output=self.root/'maps'/(PureWindowsPath(self.scenario_ref).name+'.map')
        self.run(['build-cache-file',self.scenario_ref,'classic','none'],[output],[output])
        self.log('MAP packaged. In-game spawn, lighting and gameplay validation is a separate check.')
        return output

    def open_editor(self, editor):
        if editor not in ('sapien','guerilla'):
            raise ValueError('Unsupported editor.')
        self.validate()
        if not self.scenario.is_file():
            raise ValueError('Build BSP to create the scenario first.')
        exe=self.root/(editor+'.exe')
        if not exe.is_file():
            raise ValueError(f'Missing {exe}')
        subprocess.Popen([str(exe),str(self.scenario)],cwd=self.root)

    def write_handoff(self,synchronized=False):
        data={'scenario':str(self.scenario),'scenario_type':self.project.scenario_type,'sky':self.project.sky,
              'status':'Synchronized to scenario tag.' if synchronized else 'Planning markers; place these in Sapien unless explicitly synchronized.',
              'markers':[dict(name=m.name,kind=m.kind,position_world_units=[x/100 for x in m.position],
                              yaw_degrees=m.yaw,team=m.team,tag=m.tag) for m in self.project.markers]}
        path=self.jms.parent/'scenario-placement.json'
        atomic_write(path,json.dumps(data,indent=2)+'\n')
        self.log(f'Sapien placement guide: {path}')
