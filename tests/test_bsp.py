from pathlib import Path
import tempfile
import unittest
import numpy as np
from reclaimer.hek.defs.sbsp import sbsp_def
from reclaimer.model.jms import read_jms
from blamhammer.bsp import import_bsp
from blamhammer.model import Project,save,load
from blamhammer.geometry import bounds,uv_for,normal,subdivide,translate,world_surfaces,clip_brushes
from blamhammer.jms import export_jms


def fixture(path, compressed=False):
    tag=sbsp_def.build();d=tag.data.tagdata
    d.surfaces.STEPTREE.append();d.surfaces.STEPTREE[0][:]=[0,1,2]
    d.lightmaps.STEPTREE.append();d.lightmaps.STEPTREE[0].materials.STEPTREE.append()
    m=d.lightmaps.STEPTREE[0].materials.STEPTREE[0]
    m.shader.filepath='levels\\test\\ground';m.shader.tag_class.set_to('shader_environment')
    m.vertices_count=3;m.surface_count=1
    values=np.zeros((3,8 if compressed else 14),dtype='<f4')
    values[:,:3]=[[1,2,0],[1,4,0],[5,2,0]]
    values[:,-2:]=[[.1,.2],[.3,.9],[1.3,-.1]]
    raw=m.compressed_vertices if compressed else m.uncompressed_vertices
    raw.data=bytearray(values.tobytes());raw.size=len(raw.data)
    tag.calc_internal_data();tag.serialize(filepath=path,temp=False,backup=False)
    return tag,values


class BspTests(unittest.TestCase):
    def test_units_winding_uv_sky_save_and_jms(self):
        for compressed in (False,True):
            with self.subTest(compressed=compressed),tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'fixture.scenario_structure_bsp';_,values=fixture(path,compressed)
                original=path.read_bytes();p=import_bsp(path);sky,mesh=p.brushes
                self.assertEqual(mesh.kind,'mesh');self.assertTrue(all(f.material=='+sky' for f in sky.faces))
                np.testing.assert_array_equal(mesh.vertices,values[:,:3]*100)
                f=mesh.faces[0];self.assertEqual(f.indices,[2,1,0]);self.assertEqual(f.flags,'!')
                pts=np.asarray(mesh.vertices)[f.indices];self.assertGreater(normal(pts)[2],0)
                expected=values[f.indices,-2:].astype(float);expected[:,1]=1-expected[:,1]
                np.testing.assert_allclose(uv_for(pts,f,normal(pts)),expected,atol=1e-7)
                lo,hi=bounds(mesh);slo,shi=bounds(sky)
                self.assertTrue(np.all(slo<lo) and np.all(shi>hi))
                self.assertTrue(np.all(slo%25==0) and np.all(shi%25==0))
                project=Path(folder)/'saved.hceproj';save(p,project);p=load(project)
                output=Path(folder)/'imported.jms';count=export_jms(p,output)
                model=read_jms(output.read_text());self.assertEqual(len(model.tris),count)
                self.assertTrue(next(m for m in model.materials if m.name=='ground').render_only)
                self.assertEqual(path.read_bytes(),original)
                self.assertTrue(p.level_dir.startswith('levels\\blamhammer\\'))

    def test_mesh_edits_and_uv_mapping_survive_subdivision(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'fixture.scenario_structure_bsp';fixture(path)
            p=import_bsp(path);mesh=p.brushes[1];source=mesh.faces[0]
            edited=subdivide(mesh,3,[0]);self.assertEqual(len(edited.faces),9)
            for f in edited.faces:
                self.assertEqual(f.flags,source.flags);self.assertEqual(f.uv_axes,source.uv_axes)
                pts=np.asarray(edited.vertices)[f.indices]
                np.testing.assert_allclose(uv_for(pts,f,normal(pts)),uv_for(pts,source,normal(pts)))
            translate(edited,[25,0,25]);p.brushes[1]=edited
            self.assertGreater(len(world_surfaces(p)),9)
            with self.assertRaisesRegex(ValueError,'Imported BSP'):clip_brushes(edited,[1,0,0],300)

    def test_bad_tag_ranges_and_mapping_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'fixture.scenario_structure_bsp';tag,_=fixture(path)
            with self.assertRaisesRegex(ValueError,'scenario_structure_bsp'):import_bsp(path.with_suffix('.map'))
            raw=bytearray(path.read_bytes());raw[36:40]=b'scnr';path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError,'Only Halo CE'):import_bsp(path)
            for field,value in (('vertices_count',100001),('surfaces',1),('surface_count',-1)):
                tag,_=fixture(path);setattr(tag.data.tagdata.lightmaps.STEPTREE[0].materials.STEPTREE[0],field,value)
                tag.serialize(filepath=path,temp=False,backup=False)
                with self.assertRaises(ValueError):import_bsp(path)
            tag,_=fixture(path);tag.data.tagdata.surfaces.STEPTREE[0][1]=9
            tag.serialize(filepath=path,temp=False,backup=False)
            with self.assertRaisesRegex(ValueError,'triangle index'):import_bsp(path)
            fixture(path);p=import_bsp(path);p.brushes[1].faces[0].uv_axes[0][0]=float('nan')
            with self.assertRaises(ValueError):Project.from_dict(p.to_dict())

    def test_output_never_targets_an_existing_tag(self):
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder)/'tags/levels/blamhammer/fixture_import';directory.mkdir(parents=True)
            existing=directory/'fixture_import.scenario_structure_bsp';existing.write_bytes(b'keep')
            path=Path(folder)/'fixture.scenario_structure_bsp';fixture(path)
            p=import_bsp(path,folder)
            self.assertNotEqual(p.bsp,'fixture_import');self.assertEqual(existing.read_bytes(),b'keep')

    def test_collision_flags_and_two_sided_faces_are_not_duplicated(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'fixture.scenario_structure_bsp';tag,values=fixture(path)
            d=tag.data.tagdata;d.collision_materials.STEPTREE.append()
            shader=d.collision_materials.STEPTREE[0].shader
            shader.filepath='levels\\test\\ground';shader.tag_class.set_to('shader_environment')
            d.collision_bsp.STEPTREE.append();c=d.collision_bsp.STEPTREE[0]
            for point in values[:,:3]:
                c.vertices.STEPTREE.append();c.vertices.STEPTREE[-1][:3]=point.tolist()
            for edge in ([2,1,1,2,0,1],[1,0,2,0,0,1],[0,2,0,1,0,1]):
                c.edges.STEPTREE.append();c.edges.STEPTREE[-1][:]=edge
            for _ in range(2):
                c.surfaces.STEPTREE.append();s=c.surfaces.STEPTREE[-1]
                s.material=0;s.first_edge=0;s.flags.data=7
            tag.serialize(filepath=path,temp=False,backup=False)
            mesh=import_bsp(path).brushes[1]
            self.assertEqual(len(mesh.faces),2)
            self.assertEqual(mesh.faces[1].flags,'*%^')
            c.surfaces.STEPTREE.pop();c.surfaces.STEPTREE[0].material=-1
            tag.serialize(filepath=path,temp=False,backup=False)
            self.assertEqual(import_bsp(path).brushes[1].faces[1].material,'+sky')
            c.edges.STEPTREE[0].forward_edge=99
            tag.serialize(filepath=path,temp=False,backup=False)
            with self.assertRaisesRegex(ValueError,'boundary'):import_bsp(path)


if __name__=='__main__':unittest.main()
