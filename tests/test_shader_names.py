from pathlib import Path
import tempfile
import unittest
from reclaimer.model.jms import read_jms
from blamhammer.geometry import demo
from blamhammer.jms import export_jms,material_names
from blamhammer.materials import scan_materials
from blamhammer.toolchain import Toolchain


class ShaderNameTests(unittest.TestCase):
    def test_duplicate_names_keep_exact_selection_and_refresh_copies(self):
        with tempfile.TemporaryDirectory() as folder:
            tags=Path(folder)/'tags'
            first='level_a\\grass.shader_environment';second='level_b\\grass.shader_environment'
            for ref,data in ((first,b'first shader'),(second,b'second shader')):
                file=tags/Path(ref);file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(data)
            p=demo(hek=folder,materials=[first,second,first]);before=p.to_dict()
            Toolchain(p).validate_materials()
            output=Path(folder)/'test.jms';export_jms(p,output)
            parsed=read_jms(output.read_text());names=[m.name for m in parsed.materials]
            self.assertEqual(len(set(names)),2)
            self.assertTrue(all(len(n)<=31 and n.endswith('_s') for n in names))
            copies=[tags/'blamhammer/shaders'/(n+'.shader_environment') for n in names]
            self.assertEqual({f.read_bytes() for f in copies},{b'first shader',b'second shader'})
            self.assertEqual({m.path for m in scan_materials(folder)},{first,second})
            self.assertEqual(material_names([first],folder),material_names([first,second],folder)[:1])
            self.assertEqual(material_names([first,'+sky'],folder)[1],'+sky')
            self.assertEqual(p.to_dict(),before)
            self.assertEqual((tags/Path(second)).read_bytes(),b'second shader')
            first_alias=tags/'blamhammer/shaders'/(material_names([first],folder)[0]+'.shader_environment')
            (tags/Path(first)).write_bytes(b'updated first shader')
            export_jms(p,output)
            self.assertEqual(first_alias.read_bytes(),b'updated first shader')
            self.assertEqual(Path(str(first_alias)+'.blamhammer.bak').read_bytes(),b'first shader')
            collision=tags/'unrelated'/first_alias.name;collision.parent.mkdir();collision.write_bytes(b'other tag')
            with self.assertRaisesRegex(ValueError,'conflicts'):material_names([first],folder)
            (tags/Path(first)).unlink()
            with self.assertRaisesRegex(ValueError,'Missing shader'):Toolchain(p).validate_materials()

    def test_unique_names_unchanged_and_duplicate_export_requires_source(self):
        self.assertEqual(material_names(['level\\metal.shader_environment','+sky'],''),['metal','+sky'])
        with self.assertRaisesRegex(ValueError,'Configure HCEEK'):
            material_names(['level_a\\grass.shader_environment','level_b\\grass.shader_environment'],'')


if __name__=='__main__':unittest.main()
