import copy
from collections import Counter
from pathlib import Path
import tempfile
import unittest
import numpy as np
from blamhammer.geometry import primitive,subdivide,clip_brushes,validate_brush,to_manifold,triangles,transform,world_surfaces
from blamhammer.model import Project,save,load
from blamhammer.jms import export_jms


def decorated_box():
    b=primitive(center=(0,0,100),size=(400,400,200))
    for i,f in enumerate(b.faces):
        f.material=f'material_{i}.shader_environment';f.scale=[100+i,120+i];f.offset=[i/10,-i/10];f.rotation=i*7
    return b


def mapping(f):return f.material,f.scale,f.offset,f.rotation


class EditingGeometryTests(unittest.TestCase):
    def assert_closed(self,b):
        validate_brush(b)
        edges=Counter((a,c) for _,t in triangles(b) for a,c in zip(t,t[1:]+t[:1]))
        for (a,c),count in edges.items():
            self.assertEqual(count,1)
            self.assertEqual(edges[c,a],1,'T-junction or open edge')
        self.assertGreater(to_manifold(b,{}).volume(),0)

    def test_selected_quad_grid_stitches_neighbors_and_preserves_mapping(self):
        b=decorated_box();original=copy.deepcopy(b)
        s=subdivide(b,4,[1]);self.assert_closed(s)
        self.assertEqual(b,original);self.assertEqual(s.id,b.id)
        top=[p for p in s.vertices if p[2]==200]
        self.assertEqual(len(top),25)
        self.assertEqual({(p[0],p[1]) for p in top},{(x,y) for x in range(-200,201,100) for y in range(-200,201,100)})
        self.assertEqual(sum(f.material==b.faces[1].material for f in s.faces),32)
        self.assertEqual(len(s.vertices),29,'Only the selected face gets new interior vertices')
        self.assertEqual(s.faces[0],b.faces[0],'The opposite face stays unchanged')
        for i in (0,2,3,4,5):
            neighbors=[f for f in s.faces if f.material==b.faces[i].material]
            self.assertEqual(len(neighbors),1,'Unselected faces must remain single polygons')
            self.assertEqual([v for v in neighbors[0].indices if v<len(b.vertices)],b.faces[i].indices)
        for f in s.faces:self.assertEqual(mapping(f),mapping(b.faces[int(f.material.split('_')[1].split('.')[0])]))
        self.assertAlmostEqual(to_manifold(s,{}).volume(),to_manifold(b,{}).volume(),delta=1)
        center=next(i for i,p in enumerate(s.vertices) if p==[0,0,200])
        s.vertices[center][2]=325
        self.assert_closed(s)
        self.assertGreater(to_manifold(s,{}).volume(),to_manifold(b,{}).volume())

    def test_adjacent_faces_whole_brush_triangles_ngons_and_rotation(self):
        for shape in ('box','ramp','cylinder'):
            for selected in ([1],[1,2],None):
                with self.subTest(shape=shape,selected=selected):
                    b=primitive(shape,material='metal');transform(b,rotation=(13,27,41))
                    s=subdivide(b,3,selected);self.assert_closed(s)
                    self.assertAlmostEqual(to_manifold(s,{}).volume(),to_manifold(b,{}).volume(),delta=5)
        s=subdivide(subdivide(decorated_box(),2,[1]),2,[1,2])
        self.assert_closed(s)
        neighbor=next(i for i,f in enumerate(s.faces) if f.material=='material_2.shader_environment')
        self.assert_closed(subdivide(s,2,[neighbor]))
        s=subdivide(primitive('ramp'),2,[1])
        for i,f in enumerate(s.faces):
            if len(f.indices)==4:self.assert_closed(subdivide(s,2,[i]))

    def test_subdivision_rejects_bad_input_without_mutation(self):
        b=decorated_box();original=copy.deepcopy(b)
        for segments in (0,1,33,2.5,True):
            with self.assertRaises(ValueError):subdivide(b,segments)
        for faces in ([],[-1],[99]):
            with self.assertRaises(ValueError):subdivide(b,2,faces)
        dense=subdivide(b,8)
        with self.assertRaisesRegex(ValueError,'limit'):subdivide(dense,32)
        self.assertEqual(b,original)

    def test_all_clip_modes_closed_caps_mapping_and_volume(self):
        b=decorated_box();original=copy.deepcopy(b)
        for n,offset in (([1,0,0],0),([1,2,3],75),([0,0,8],100)):
            n=np.asarray(n,float);n/=np.linalg.norm(n)
            both=clip_brushes(b,n,offset,'both')
            self.assertEqual(len(both),2);self.assertNotEqual(both[0].id,both[1].id)
            self.assertAlmostEqual(sum(to_manifold(x,{}).volume() for x in both),to_manifold(b,{}).volume(),delta=10)
            for side,sign,half in zip(('left','right'),(1,-1),both):
                self.assert_closed(half)
                single=clip_brushes(b,n,offset,side)
                self.assertEqual(len(single),1)
                self.assertAlmostEqual(to_manifold(single[0],{}).volume(),to_manifold(half,{}).volume(),delta=1)
                v=np.asarray(half.vertices)
                self.assertGreaterEqual(float(np.min(sign*(v@n-offset))),-.0001)
                caps=0
                for f in half.faces:
                    pts=v[f.indices]
                    if np.max(np.abs(pts@n-offset))<.0001:
                        caps+=1;self.assertEqual(mapping(f),mapping(b.faces[0]))
                    else:
                        # Match the original geometric plane, independently of Manifold face IDs.
                        source=next(source for source in b.faces if any(
                            np.max(np.abs(pts[:,axis]-np.asarray(b.vertices)[source.indices,axis][0]))<.0001
                            and np.ptp(np.asarray(b.vertices)[source.indices,axis])==0 for axis in range(3)))
                        self.assertEqual(mapping(f),mapping(source))
                self.assertGreater(caps,0)
        self.assertEqual(b,original)

    def test_clip_tangent_outside_invalid_and_room(self):
        b=decorated_box();b.kind='room'
        self.assertEqual(clip_brushes(b,[1,0,0],0,'right')[0].kind,'room')
        for offset in (200,500):
            with self.assertRaises(ValueError):clip_brushes(b,[1,0,0],offset,'both')
            with self.assertRaises(ValueError):clip_brushes(b,[1,0,0],offset,'left')
        self.assert_closed(clip_brushes(b,[1,0,0],-500,'left')[0])
        self.assertEqual(clip_brushes(b,[1,0,0],-200,'left')[0],b)
        self.assertEqual(clip_brushes(b,[1,0,0],200,'right')[0],b)
        for n,offset,mode in (([0,0,0],0,'left'),([float('nan'),0,0],0,'left'),([1,0,0],float('inf'),'left'),([1,0,0],0,'bad')):
            with self.assertRaises(ValueError):clip_brushes(b,n,offset,mode)

    def test_terrain_clipped_halves_save_reload_and_independent_jms_reader(self):
        terrain=subdivide(decorated_box(),4,[1])
        for p in terrain.vertices:
            if p[2]==200 and abs(p[0])<200 and abs(p[1])<200:p[2]+=100*(1-abs(p[0])/200)*(1-abs(p[1])/200)
        halves=clip_brushes(terrain,[1,1,0],0,'both')
        p=Project(brushes=[primitive('room',(0,0,400),(1200,1200,800),'wall.shader_environment')]+halves)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'terrain.hceproj';save(p,path);reloaded=load(path)
            self.assertEqual(p.to_dict(),reloaded.to_dict())
            surfaces=world_surfaces(reloaded)
            edges=Counter((tuple(a),tuple(b)) for s in surfaces for a,b in zip(s.points,np.roll(s.points,-1,axis=0)))
            for (a,b),count in edges.items():self.assertEqual(count,edges[b,a])
            jms=Path(folder)/'terrain.jms';count=export_jms(reloaded,jms)
            from reclaimer.model.jms import read_jms
            model=read_jms(jms.read_text());self.assertEqual(len(model.tris),count)
            self.assertGreater(count,20)


if __name__=='__main__':unittest.main()
