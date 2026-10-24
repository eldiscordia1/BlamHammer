from types import SimpleNamespace
import unittest
import numpy as np
from PySide6.QtWidgets import QApplication
from blamhammer.geometry import primitive,translate,world_surfaces
from blamhammer.model import Project,Brush,Face,Marker
from blamhammer.viewports import PerspectiveView


class ViewportCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.brush=primitive(material='wall')
        self.editor=SimpleNamespace(project=Project(brushes=[self.brush]),selection=[],face_selection=[],
                                    csg_preview=False,csg_surfaces=[])
        self.view=PerspectiveView(self.editor)
        self.view.texture=lambda material:0
        self.addCleanup(self.view.close)

    def test_selection_reuses_geometry_and_restores_face_colors(self):
        v=self.view;v.prepare_batches();geometry=v._geometry;batches=v.batches
        self.editor.selection=[self.brush.id];self.editor.face_selection=[(self.brush.id,1)]
        v.invalidate_cache(False);v.prepare_selection()
        self.assertIs(v._geometry,geometry);self.assertIs(v.batches,batches)
        self.assertEqual(len(v.selected_lines),8)
        for texture,vertices in v.batches.items():
            mask=np.repeat([ref==(self.brush.id,1) for ref in v.batch_faces[texture]],3)
            np.testing.assert_allclose(vertices[mask,2:5],np.tile([1,.75,.35],(mask.sum(),1)),atol=1e-7)
            np.testing.assert_array_equal(vertices[~mask,2:5],v.base_colors[texture][~mask])
        self.editor.selection=[];self.editor.face_selection=[];v.invalidate_cache(False);v.prepare_selection()
        self.assertIs(v._geometry,geometry);self.assertEqual(len(v.selected_lines),0)
        for texture,vertices in v.batches.items():np.testing.assert_array_equal(vertices[:,2:5],v.base_colors[texture])

    def test_edits_uvs_and_csg_replace_cached_geometry(self):
        v=self.view;before=list(v.geometry());cache=v._geometry
        translate(self.brush,[25,0,50]);self.brush.faces[0].offset=[.5,.25]
        v.invalidate_cache();self.assertIsNone(v._geometry)
        after=list(v.geometry());self.assertIsNot(v._geometry,cache)
        np.testing.assert_allclose(after[0][0],before[0][0]+[25,0,50])
        np.testing.assert_allclose(after[0][2],before[0][2]+[.75,.25])
        self.editor.project.brushes.insert(0,primitive('room',(0,0,400),(1000,1000,800),'wall'))
        self.editor.csg_surfaces=world_surfaces(self.editor.project);self.editor.csg_preview=True;v.invalidate_cache()
        self.assertTrue(all(s[-1]==-1 for s in v.geometry()))
        self.editor.csg_preview=False;v.invalidate_cache()
        self.assertTrue(all(s[-1]>=0 for s in v.geometry()))

    def test_pick_keeps_nearest_face_backface_marker_and_hidden_collision_rules(self):
        v=self.view
        collision=Brush('hidden collision',[[-100,-100,350],[100,-100,350],[0,100,350]],
                        [Face([0,1,2],'wall',flags='@')],'mesh')
        self.editor.project.brushes.append(collision)
        v.ray=lambda pos:(np.array([0.,0.,400.]),np.array([0.,0.,-1.]))
        self.assertEqual(v.pick(None),(self.brush.id,1))
        cache=v._geometry
        self.assertEqual(v.pick(None),(self.brush.id,1));self.assertIs(v._geometry,cache)
        marker=Marker(position=[0,0,300]);self.editor.project.markers.append(marker)
        self.assertEqual(v.pick(None),(marker.id,-1))
        self.editor.project.markers.clear()
        v.ray=lambda pos:(np.array([0.,0.,100.]),np.array([0.,0.,1.]))
        self.assertEqual(v.pick(None),(None,-1))
        v.ray=lambda pos:(np.array([1000.,0.,400.]),np.array([0.,0.,-1.]))
        self.assertEqual(v.pick(None),(None,-1))
        self.editor.project.brushes.clear();v.invalidate_cache()
        self.assertEqual(v.pick(None),(None,-1))


if __name__=='__main__':unittest.main()
