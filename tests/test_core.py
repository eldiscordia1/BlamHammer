import copy
import json
from pathlib import Path
import tempfile
import unittest
from collections import Counter
import numpy as np
from blamhammer.model import Project,History,save,load,tag_path
from blamhammer.geometry import primitive,demo,world_surfaces,bounds,transform,translate,boolean,clip,validate_brush,to_manifold
from blamhammer.jms import export_jms
from blamhammer.toolchain import Toolchain,beneath


class GeometryTests(unittest.TestCase):
    def test_primitives_are_closed_positive_volume(self):
        for shape in ('box','room','ramp','wedge','cylinder','wall','floor','ceiling'):
            with self.subTest(shape=shape):
                b=primitive(shape,material='test.shader_environment');validate_brush(b)
                self.assertGreater(to_manifold(b,{}).volume(),0)

    def test_world_is_closed_inward_and_has_no_internal_floor(self):
        p=demo(materials=['wall','floor','metal']);surfaces=world_surfaces(p)
        directed=Counter()
        for s in surfaces:
            for a,b in zip(s.points,np.roll(s.points,-1,axis=0)):
                directed[(tuple(a),tuple(b))]+=1
            self.assertAlmostEqual(float(np.linalg.norm(s.normal)),1)
            self.assertTrue(np.isfinite(s.uv).all())
        for (a,b),count in directed.items():self.assertEqual(count,directed[(b,a)])
        volume=sum(np.dot(s.points[0],np.cross(s.points[1],s.points[2]))/6 for s in surfaces)
        self.assertAlmostEqual(volume,-(1600*2000*800-400*400*200-400*400*200/2),delta=1)
        self.assertEqual({s.material for s in surfaces},{'wall','floor','metal'})
        for s in surfaces:
            midpoint=s.points.mean(axis=0)
            if abs(midpoint[2])<.001:
                self.assertFalse(100<midpoint[0]<500 and -300<midpoint[1]<500)

    def test_csg_and_clip(self):
        a=primitive(center=(0,0,0),size=(200,200,200),material='a')
        b=primitive(center=(100,0,0),size=(200,200,200),material='b')
        for operation,volume in [('union',12000000),('subtract',4000000),('intersect',4000000)]:
            result=boolean(a,b,operation);validate_brush(result)
            self.assertAlmostEqual(to_manifold(result,{}).volume(),volume,delta=1)
        cut=clip(a,[1,0,0],0)
        self.assertGreaterEqual(min(p[0] for p in cut.vertices),0)
        self.assertAlmostEqual(to_manifold(cut,{}).volume(),4000000,delta=1)

    def test_transform_and_invalid_vertex_edit(self):
        b=primitive();transform(b,center=(100,200,300),size=(100,200,300),rotation=(0,0,90))
        lo,hi=bounds(b)
        np.testing.assert_allclose((lo+hi)/2,[100,200,300]);np.testing.assert_allclose(hi-lo,[200,100,300])
        b.vertices[0][2]+=10
        with self.assertRaisesRegex(ValueError,'non-planar'):validate_brush(b)

    def test_export_requires_room_and_materials(self):
        with self.assertRaisesRegex(ValueError,'Room'):world_surfaces(Project(brushes=[primitive()]))
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError,'Unassigned'):export_jms(demo(),Path(folder)/'test.jms')

    def test_jms_can_be_independently_parsed(self):
        p=demo(materials=['wall.shader_environment','floor.shader_environment','metal.shader_environment'])
        with tempfile.TemporaryDirectory() as folder:
            filename=Path(folder)/'room.jms';count=export_jms(p,filename)
            from reclaimer.model.jms import read_jms
            text=filename.read_text()
            result=read_jms(text)
            self.assertIsNotNone(result)
            self.assertEqual(len(result.tris),count)
            self.assertEqual(len(result.verts),count*3)
            self.assertEqual(len(result.materials),3)


class PersistenceTests(unittest.TestCase):
    def test_roundtrip_backup_and_history(self):
        p=demo(materials=['a','b','c']);p.brushes[0].faces[2].scale=[23,57]
        p.brushes[0].faces[2].offset=[.25,-2.4];p.brushes[0].faces[2].rotation=37
        p.notes='UTF-8: habitación';p.author='Mapper'
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.hceproj';save(p,path)
            self.assertEqual(load(path).to_dict(),p.to_dict())
            history=History();history.record(p.to_dict());original=p.to_dict()
            translate(p.brushes[1],[25,0,0]);changed=p.to_dict()
            save(p,path);self.assertEqual(load(str(path)+'.bak').to_dict(),original)
            p=history.undo(p);self.assertEqual(p.to_dict(),original)
            p=history.redo(p);self.assertEqual(p.to_dict(),changed)

    def test_invalid_files_and_traversal_rejected(self):
        for path in ('..\\foo','C:\\outside','\\absolute','a\\..\\b','a\\\\b'):
            with self.subTest(path=path),self.assertRaises(ValueError):tag_path(path)
        p=demo().to_dict();p['brushes'][0]['vertices'][0][0]=float('nan')
        with self.assertRaises(ValueError):Project.from_dict(p)
        p=demo().to_dict();p['brushes'][0]['faces'][0]['indices'][0]=999
        with self.assertRaises(ValueError):Project.from_dict(p)
        p=demo().to_dict();p['version']=99
        with self.assertRaises(ValueError):Project.from_dict(p)

    def test_toolchain_rejects_missing_install(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Project(hek=folder)
            with self.assertRaisesRegex(ValueError,'Configure'):Toolchain(p).build_bsp()


if __name__=='__main__':unittest.main()
