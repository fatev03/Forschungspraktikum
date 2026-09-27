from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import tempfile
import unittest

from structure_audit.provenance import hash_file, hash_config, create_run_directory, make_manifest, write_manifest, write_json_new
from structure_audit.reporting import audit_supplied_structure
from structure_audit.validation import validate_named, validate, read_json
from helpers import FIXTURES


class ProvenanceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def manifest(self):
        directory = create_run_directory(self.root,"test")
        manifest = make_manifest(directory,{"b":2,"a":1},[FIXTURES/"minimal.pdb"],project_root=self.root)
        return directory, manifest

    def test_file_sha256(self):
        path = self.root/'in'
        path.write_bytes(b'abc')
        self.assertEqual(hash_file(path),hashlib.sha256(b'abc').hexdigest())
        path.write_bytes(b'abd')
        self.assertNotEqual(hash_file(path),hashlib.sha256(b'abc').hexdigest())

    def test_canonical_config_hash(self):
        self.assertEqual(hash_config({'b':[2,1],'a':1}),hash_config({'a':1,'b':[2,1]}))
        self.assertNotEqual(hash_config({'a':1}),hash_config({'a':2}))
        self.assertNotEqual(hash_config({'b':[2,1]}),hash_config({'b':[1,2]}))

    def test_hash_refuses_non_json(self):
        for value in ({'a':float('nan')},{1:'invalid'},{'a':object()}):
            with self.assertRaises(ValueError):
                hash_config(value)

    def test_versioned_directory_preserves_existing_results(self):
        first=create_run_directory(self.root,'run')
        (first/'output').write_text('existing')
        second=create_run_directory(self.root,'run')
        self.assertEqual(first.name,'v0001')
        self.assertEqual(second.name,'v0002')
        self.assertEqual((first/'output').read_text(),'existing')

    def test_concurrent_directory_allocation(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            dirs=list(pool.map(lambda _:create_run_directory(self.root,'same'),range(12)))
        self.assertEqual(len(set(dirs)),12)
        self.assertTrue(all(p.is_dir() for p in dirs))

    def test_unsafe_run_ids_rejected(self):
        for run_id in ('../outside','a/b','.', '/', 'x'*101):
            with self.subTest(run_id=run_id),self.assertRaises(ValueError):
                create_run_directory(self.root,run_id)

    def test_run_symlink_parent_rejected(self):
        (self.root/'elsewhere').mkdir()
        (self.root/'run').symlink_to(self.root/'elsewhere',target_is_directory=True)
        with self.assertRaises(ValueError):
            create_run_directory(self.root,'run')

    def test_manifest_roundtrip_and_missing_git(self):
        directory,manifest=self.manifest()
        write_manifest(directory/'manifest.json',manifest)
        actual=read_json(directory/'manifest.json')
        self.assertEqual(actual,manifest)
        self.assertIsNone(actual['git_commit'])
        self.assertTrue(any('git_unavailable' in w for w in actual['warnings']))

    def test_manifest_overwrite_refused(self):
        directory,manifest=self.manifest()
        write_manifest(directory/'manifest.json',manifest)
        with self.assertRaises(FileExistsError):
            write_manifest(directory/'manifest.json',manifest)

    def test_manifest_tampered_config_rejected(self):
        directory,manifest=self.manifest()
        manifest['config']['a']=2
        with self.assertRaisesRegex(ValueError,'hash mismatch'):
            write_manifest(directory/'manifest.json',manifest)

    def test_manifest_invalid_schema_fields(self):
        _,manifest=self.manifest()
        for field,value in [('random_seed',True),('random_seed',-1),('status','success'),('input_files',[{'path':'a','sha256':'not-a-hash'}])]:
            bad=deepcopy(manifest);bad[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                validate_named(bad,'run_manifest')

    def test_manifest_utc_and_path_validation(self):
        directory,manifest=self.manifest()
        manifest['timestamp']='2026-01-01T10:00:00'
        with self.assertRaisesRegex(ValueError,'UTC'):
            write_manifest(directory/'manifest.json',manifest)
        manifest['timestamp']='2026-01-01T10:00:00+00:00'
        manifest['output_paths']=[str(self.root/'outside.json')]
        with self.assertRaisesRegex(ValueError,'escapes'):
            write_manifest(directory/'manifest.json',manifest)

    def test_json_duplicate_and_nonfinite_rejected(self):
        path=self.root/'bad.json'
        for content in ('{"a":1,"a":2}','{"a":NaN}'):
            path.write_text(content)
            with self.assertRaises(ValueError):
                read_json(path)

    def test_unknown_schema_keyword_explicit_error(self):
        with self.assertRaisesRegex(ValueError,'Unsupported schema'):
            validate(3,{'maximum':2})

    def test_complete_offline_report_and_rerun(self):
        before=hash_file(FIXTURES/'minimal.pdb')
        kwargs={'project_root':self.root,'run_id':'fixture'}
        first=audit_supplied_structure(FIXTURES/'minimal.pdb',self.root,{},**kwargs)
        second=audit_supplied_structure(FIXTURES/'minimal.pdb',self.root,{},**kwargs)
        self.assertNotEqual(first,second)
        manifest=read_json(first/'manifest.json')
        self.assertEqual(manifest['status'],'completed')
        self.assertTrue(all(Path(p).exists() for p in manifest['output_paths']))
        self.assertEqual(manifest['input_files'][0]['sha256'],before)
        self.assertEqual(hash_file(FIXTURES/'minimal.pdb'),before)
        self.assertEqual(len(read_json(first/'checks.json')['checks']),2)

    def test_report_rejects_unknown_config(self):
        with self.assertRaises(ValueError):
            audit_supplied_structure(FIXTURES/'minimal.pdb',self.root,{'auto_download':True},project_root=self.root)

    def test_failed_output_has_failure_marker(self):
        with self.assertRaises(ValueError):
            audit_supplied_structure(FIXTURES/'minimal.pdb',self.root,{'seed':-1},project_root=self.root,run_id='invalid')
        marker=read_json(self.root/'invalid/v0001/failure.json')
        self.assertEqual(marker['status'],'failed')
        self.assertFalse((self.root/'invalid/v0001/manifest.json').exists())
