from datetime import datetime
import importlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('src.models.archives'),'archive service is missing')
        self.api=importlib.import_module('src.models.archives')
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.source=self.root/'cache/data.hex'
        self.source.parent.mkdir();self.source.write_bytes(b'08000ABC')
        self.meta={'complete':True,'expected_hex_bytes':8,'sample_rate_hz':5000000,'status':{'ACTIVE_PRE':0}}
        Path(str(self.source)+'.json').write_text(json.dumps(self.meta),encoding='utf-8')
        self.dest=self.root/'archives';self.now=datetime(2026,10,14,15,7,59)

    def test_confirmed_save_copies_hex_and_metadata_without_changing_cache(self):
        result=self.api.save_archive(self.source,self.dest,now=self.now)
        self.assertEqual(result,self.dest/'20261014_1507/20261014_1507.hex')
        self.assertEqual(result.read_bytes(),b'08000ABC')
        self.assertEqual(json.loads(Path(str(result)+'.json').read_text('utf-8')),self.meta)
        self.assertTrue(self.source.exists())

    def test_same_minute_and_concurrent_saves_never_overwrite(self):
        with ThreadPoolExecutor(max_workers=3) as pool:
            paths=list(pool.map(lambda _:self.api.save_archive(self.source,self.dest,now=self.now),range(3)))
        self.assertEqual({p.parent.name for p in paths},{'20261014_1507','20261014_1507_1','20261014_1507_2'})
        for p in paths:self.assertEqual(p.read_bytes(),b'08000ABC')

    def test_incomplete_or_wrong_length_is_not_archived(self):
        for meta in ({'complete':False,'expected_hex_bytes':8},{'complete':True,'expected_hex_bytes':16}):
            Path(str(self.source)+'.json').write_text(json.dumps(meta),encoding='utf-8')
            with self.assertRaises(ValueError):self.api.save_archive(self.source,self.dest,now=self.now)
            self.assertFalse(self.dest.exists())

    def test_copy_failure_preserves_source_and_existing_archive(self):
        first=self.api.save_archive(self.source,self.dest,now=self.now)
        with patch('src.models.archives.shutil.copyfileobj',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.api.save_archive(self.source,self.dest,now=self.now)
        self.assertEqual(list(self.dest.iterdir()),[first.parent])
        self.assertEqual(self.source.read_bytes(),b'08000ABC')

    def test_archive_job_reports_failure_and_is_joinable(self):
        job=self.api.ArchiveJob(self.root/'missing.hex',self.dest);job.start();job.thread.join(3)
        self.assertTrue(job.done.is_set());self.assertTrue(job.error);self.assertIsNone(job.path)
        self.assertFalse(self.dest.exists())


if __name__=='__main__':unittest.main()
