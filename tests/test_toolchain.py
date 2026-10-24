import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from blamhammer.model import Project
from blamhammer.toolchain import Toolchain


class BuildVerificationTests(unittest.TestCase):
    def test_exit_output_and_freshness_are_all_required(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'tool.exe').touch();(root/'tags/globals').mkdir(parents=True)
            (root/'tags/globals/globals.globals').touch()
            output=root/'test.map';chain=Toolchain(Project(hek=folder),lambda line:None)
            for code,payload,change,message in [(1,'',True,'Tool failed'),(0,'',False,'nonempty'),
                                                (0,'### ERROR invalid BSP',True,'reported an error')]:
                output.unlink(missing_ok=True)
                class Process:
                    def __init__(self,*args,**kwargs):
                        self.stdout=io.StringIO(payload)
                        if change:output.write_bytes(b'test-output')
                    def wait(self):return code
                with patch('blamhammer.toolchain.subprocess.Popen',Process):
                    with self.assertRaisesRegex(RuntimeError,message):chain.run(['build-cache-file','test'],[output],[output])
            output.write_bytes(b'old-output')
            class StaleProcess:
                def __init__(self,*args,**kwargs):self.stdout=io.StringIO('successfully built cache file')
                def wait(self):return 0
            with patch('blamhammer.toolchain.subprocess.Popen',StaleProcess):
                with self.assertRaisesRegex(RuntimeError,'stale'):chain.run(['build-cache-file','test'],[output],[output])

    def test_cancel_before_launch(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'tool.exe').touch();(root/'tags/globals').mkdir(parents=True)
            (root/'tags/globals/globals.globals').touch()
            chain=Toolchain(Project(hek=folder));chain.cancel()
            with self.assertRaisesRegex(RuntimeError,'cancelled'):chain.run(['structure'],[],[])
