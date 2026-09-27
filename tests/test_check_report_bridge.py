"""Synthetic contract fixtures; no real target data or model execution."""
from copy import deepcopy
from contextlib import ExitStack
import builtins
import glob
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from structure_audit import (build_check_report, CheckReport, CheckReportError, import_notebook_outputs,
    import_dl_binder_sc, read_structure, canonical_residue_map, CandidateEvidence,
    structure_integrity_check, coarse_steric_clash_check)
from structure_audit.checks import CheckResult
from structure_audit.provenance import hash_config, hash_file, make_manifest, write_json_new, write_manifest, create_run_directory
from structure_audit.validation import read_json, validate_named
from test_notebook_output_adapter import synthetic_contract, FILES
from helpers import FIXTURES, atom, backbone


def seal_contract(args):
    """Explicitly attest an intentional fixture mutation; never production inference."""
    mid = args['config']['bridge_manifest_id']
    m = args['manifests'][mid]
    m['config'] = {'check_report_bridge': {
        'config': deepcopy(args['config']), 'evidence_batches_sha256': hash_config(args['evidence_batches']),
        'check_records_sha256': hash_config(args['check_records']), 'bindings_sha256': hash_config(args['bindings']),
        'source_manifests_sha256': hash_config({k:v for k,v in args['manifests'].items() if k != mid})}}
    m['config_hash'] = hash_config(m['config'])


def bridge_fixture(root):
    """Create a self-contained local fixture from explicitly named synthetic files."""
    root = Path(root).resolve()
    for name in FILES:
        (root/name).write_bytes((FIXTURES/'notebook_outputs'/name).read_bytes())
    nb = synthetic_contract(root)
    nb_result = import_notebook_outputs(**nb)
    pdb = root/'toy.pdb'
    structure = read_structure(pdb, model_id='1')
    rows = canonical_residue_map(structure)
    sc = root/'dl_binder.sc'; sc.write_bytes((FIXTURES/'dl_binder.sc').read_bytes())
    dl_config = read_json(FIXTURES/'dl_binder_config.json')
    prov = {'model_id':'synthetic-model', 'checkpoint_id':None, 'seed':17}
    dl_manifest = make_manifest(root/'dl-run/v0001', {'dl_binder_output_adapter':dl_config}, [sc,pdb], project_root=root,supplied_models=[prov])
    dl_bindings = {'synthetic_complex':{'candidate_id':'dl-0','target_id':None,'conformer_id':None,
        'pdb_path':str(pdb),'pdb_model_id':'1','residue_map':rows,
        'chain_roles':[{'chain_id':'A','segment':0,'role':'candidate'},{'chain_id':'B','segment':0,'role':'target'}]}}
    dl_result = import_dl_binder_sc(sc,bindings=dl_bindings,manifest=dl_manifest,config=dl_config,provenance=prov)
    batches = [
        {'batch_id':'notebook','adapter':'notebook_output_adapter','adapter_version':'1.0','manifest_id':'notebook',
         'candidates':{'nb0':nb_result.candidates[0].to_dict(),'nb1':nb_result.candidates[1].to_dict()},'quarantined':{},'diagnostics':nb_result.diagnostics},
        {'batch_id':'dl','adapter':'dl_binder_output_adapter','adapter_version':'1.0','manifest_id':'dl',
         'candidates':{'dl0':dl_result[0].to_dict()},'quarantined':{},'diagnostics':[]}]
    manifests = {'notebook':nb['manifest'],'dl':dl_manifest,
        'checks':make_manifest(root/'checks-run/v0001', {}, [pdb], project_root=root),
        'bridge':make_manifest(root/'bridge-run/v0001', {}, [pdb], project_root=root)}
    cfg = read_json(FIXTURES/'check_report/config.json'); cfg['allowed_input_roots']=[str(root)]
    args = {'evidence_batches':batches,'check_records':{},'bindings':[],'manifests':manifests,'config':cfg}
    for i,(eid,aid,run,sample) in enumerate((('nb0','bpdb0','boltz-run','sample-zero'),
        ('nb0','bpdb1','boltz-run','sample-one'),('nb1','pdb1','csv-run','1'),('dl0','prediction_pdb',None,None))):
        roles = dl_bindings['synthetic_complex']['chain_roles'] if eid=='dl0' else [
            {'chain_id':'A','segment':0,'role':'target'},{'chain_id':'B','segment':0,'role':'candidate'}]
        b = {'binding_id':f'b{i}','evidence_id':eid,'artifact':{'artifact_id':aid,'path':str(pdb),
            'sha256':hash_file(pdb),'model_id':'1','source_run_id':run,'sample_id':sample,
            'residue_map':deepcopy(rows),'residue_map_sha256':hash_config(rows),'chain_roles':roles},
            'prediction_context':'complex','origin_declaration':{'origin':'design','reason':'Synthetic design declaration only'} if eid=='dl0' else None,'checks':[]}
        for j,result in enumerate((structure_integrity_check(structure),coarse_steric_clash_check(structure))):
            rid=f'r{i}-{j}'
            b['checks'].append({'check_id':f'c{i}-{j}','check':result.check,'check_version':'1.0',
                'configuration':result.configuration,'config_sha256':hash_config(result.configuration),
                'record_id':rid,'not_run_reason':None})
            args['check_records'][rid]={'manifest_id':'checks','status':result.status,'reason':None,'result':result.to_dict()}
        args['bindings'].append(b)
    seal_contract(args)
    return args


class CheckReportBridgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve(); self.kw=bridge_fixture(self.root)

    def result(self):
        return build_check_report(**self.kw).to_dict()

    def seal(self): seal_contract(self.kw)

    def fatal(self):
        with self.assertRaises(CheckReportError) as caught: self.result()
        self.assertEqual(caught.exception.diagnostics[0]['severity'],'error')
        self.assertFalse(hasattr(caught.exception,'report'))
        return caught.exception

    def test_two_adapters_multiple_samples_exact_snapshots(self):
        before=deepcopy(self.kw); r=self.result()
        self.assertEqual(len(r['candidate_reports']),3)
        self.assertEqual(len(r['bindings']),4)
        self.assertEqual(r['snapshots']['evidence_batches'],self.kw['evidence_batches'])
        self.assertEqual(r['snapshots']['check_records'],self.kw['check_records'])
        self.assertEqual(before,self.kw)
        self.assertEqual([b['artifact']['sample_id'] for b in r['bindings'][:2]],['sample-zero','sample-one'])
        self.assertNotIn('score',r); self.assertNotIn('status',r)
        self.assertTrue(all(b['identity_status']=='verified_local' for b in r['bindings']))

    def test_concrete_existing_classes_accepted(self):
        c=self.kw['evidence_batches'][0]['candidates']['nb0']
        self.kw['evidence_batches'][0]['candidates']['nb0']=CandidateEvidence(**c)
        self.kw['check_records']['r0-0']['result']=CheckResult(**self.kw['check_records']['r0-0']['result'])
        r=self.result()
        self.assertEqual(r['snapshots']['evidence_batches'][0]['candidates']['nb0'],c)

    def test_manifest_producer_map_and_context_preserved(self):
        r=self.result(); b=r['bindings'][3]
        self.assertEqual(b['run_id'],'bridge-run'); self.assertEqual(b['import_run_id'],'dl-run')
        self.assertEqual(b['producer']['model_provenance']['seed'],17)
        self.assertEqual(b['prediction_context'],'complex')
        self.assertEqual(b['artifact']['residue_map_sha256'],b['checks'][0]['check_residue_map_sha256'])
        self.assertEqual(b['checks'][0]['check_manifest']['run_id'],'checks-run')
        self.assertEqual(b['checks'][0]['config_sha256'],hash_config(b['checks'][0]['configuration']))

    def test_seven_statuses_preserve_other_checks_and_evidence(self):
        original=deepcopy(self.kw)
        for state in read_json(FIXTURES/'check_report/states.json')['states']:
            with self.subTest(state=state):
                self.kw=deepcopy(original); rec=self.kw['check_records']['r0-0']
                rec['status']=state
                if state in ('pass','warn','fail'): rec['result']['status']=state
                else: rec.update(result=None,reason='Synthetic explicit state')
                self.seal(); r=self.result()
                self.assertEqual(r['bindings'][0]['checks'][0]['status'],state)
                self.assertEqual(r['bindings'][0]['checks'][1]['status'],'pass')
                self.assertEqual(len(r['candidate_reports']),3)
                self.assertEqual(r['snapshots']['evidence_batches'],original['evidence_batches'])

    def test_missing_record_and_not_run_are_not_pass(self):
        del self.kw['check_records']['r0-0']
        e=self.kw['bindings'][0]['checks'][1]; del self.kw['check_records'][e['record_id']]
        e.update(record_id=None,not_run_reason='Explicitly skipped in synthetic fixture')
        self.seal(); checks=self.result()['bindings'][0]['checks']
        self.assertEqual([c['status'] for c in checks],['missing','not_run'])
        self.assertTrue(all(c['raw_status'] is None for c in checks))

    def test_dl_origin_defaults_unknown(self):
        self.kw['bindings'][3]['origin_declaration']=None; self.seal(); r=self.result()
        self.assertEqual(len(r['candidate_reports']),2)
        self.assertEqual(r['audit']['quarantined_evidence'][0]['origin'],'unknown')
        self.assertEqual(r['bindings'][3]['checks'][1]['status'],'pass')

    def test_all_nondesign_origins_separate_even_if_check_passes(self):
        original=deepcopy(self.kw)
        for origin in ('demo','unknown','origin_conflict'):
            with self.subTest(origin=origin):
                self.kw=deepcopy(original)
                c=self.kw['evidence_batches'][0]['candidates'].pop('nb0')
                next(m['raw_value'] for m in c['metrics'] if m['name']=='__notebook_import__')['origin']=origin
                self.kw['evidence_batches'][0]['quarantined']['nb0']=c
                self.seal(); r=self.result()
                self.assertEqual(r['audit']['quarantined_evidence'][0]['origin'],origin)
                self.assertNotIn('nb0',[x['evidence_id'] for x in r['candidate_reports']])
                self.assertEqual(r['bindings'][0]['checks'][1]['status'],'pass')

    def test_origin_upgrade_and_conflicting_declarations_quarantined(self):
        for b in self.kw['bindings'][:2]: b['origin_declaration']={'origin':'demo','reason':'Synthetic conflict'}
        self.seal(); r=self.result()
        self.assertEqual(r['audit']['quarantined_evidence'][0]['origin'],'origin_conflict')
        self.kw['bindings'][1]['origin_declaration']['origin']='design'; self.seal()
        self.assertEqual(self.result()['audit']['quarantined_evidence'][0]['origin'],'origin_conflict')

    def test_quarantine_group_and_flattened_marker_cannot_be_promoted(self):
        batch=self.kw['evidence_batches'][0]
        batch['quarantined']['nb0']=batch['candidates'].pop('nb0')
        self.seal(); self.assertEqual(self.result()['audit']['quarantined_evidence'][0]['origin'],'origin_conflict')
        c=batch['candidates']['nb0']=batch['quarantined'].pop('nb0')
        c['metrics'][0]['category']='quarantined_origin'; self.seal()
        self.assertEqual(self.result()['audit']['quarantined_evidence'][0]['origin'],'origin_conflict')

    def test_raw_only_and_nested_directional_metrics_not_reinterpreted(self):
        r=self.result(); c=r['snapshots']['evidence_batches'][0]['candidates']['nb0']
        metrics={m['name']:m for m in c['metrics']}
        self.assertEqual(metrics['boltz0:/pair_chains_iptm/0/1']['value'],0.4)
        self.assertEqual(metrics['boltz0:/pair_chains_iptm/1/0']['value'],0.6)
        self.assertIsNone(metrics['csv:/rmsd']['value'])
        self.assertTrue(any(x['name']=='csv:/rmsd' for x in r['audit']['metrics']))

    def test_unsupported_semantics_not_cleaned_by_pass(self):
        c=self.kw['evidence_batches'][1]['candidates']['dl0']
        m=next(m for m in c['metrics'] if m['name']=='binder_aligned_rmsd')
        m.update(value=None,category='unsupported_semantics',missing_reason='monomer binderlen=-1 sentinel')
        self.seal(); r=self.result()
        self.assertIn('binder_aligned_rmsd',[x['name'] for x in r['audit']['metrics']])
        self.assertNotIn('binder_aligned_rmsd',[x['name'] for x in r['candidate_reports'][2]['metric_refs']])
        self.assertEqual(r['snapshots']['evidence_batches'][1]['candidates']['dl0'],c)

    def test_null_and_nan_token_preserved(self):
        c=self.kw['evidence_batches'][0]['candidates']['nb0']
        m=next(m for m in c['metrics'] if m['name']=='csv:/plddt')
        for raw in ('nan',None):
            m.update(raw_value=raw,value=None,missing_reason='synthetic missing or nonfinite token')
            self.seal(); r=self.result()
            self.assertEqual(r['snapshots']['evidence_batches'][0]['candidates']['nb0'],c)

    def test_wrong_chain_sample_model_and_context_only_break_one_link(self):
        original=deepcopy(self.kw)
        for field,value in (('sample_id','wrong'),('model_id','2'),('chain_roles',[])):
            with self.subTest(field=field):
                self.kw=deepcopy(original); self.kw['bindings'][0]['artifact'][field]=value; self.seal()
                r=self.result(); self.assertEqual(r['bindings'][0]['checks'][0]['status'],'error')
                self.assertEqual(r['bindings'][1]['identity_status'],'verified_local')
        self.kw=deepcopy(original); self.kw['bindings'][0]['prediction_context']='monomer'; self.seal()
        self.assertEqual(self.result()['bindings'][0]['identity_status'],'error')

    def test_stale_map_is_local_error(self):
        self.kw['bindings'][0]['artifact']['residue_map'][0]['residue_id']=999; self.seal(); r=self.result()
        self.assertEqual(r['audit']['unresolved_bindings'],['b0'])
        self.assertEqual(r['bindings'][0]['checks'][1]['raw_status'],'pass')
        self.assertEqual(r['bindings'][0]['checks'][1]['status'],'error')

    def test_stale_or_missing_pdb_preserves_all_snapshots(self):
        (self.root/'toy.pdb').write_text('changed')
        r=self.result(); self.assertTrue(all(b['identity_status']=='error' for b in r['bindings']))
        self.assertEqual(r['snapshots']['evidence_batches'],self.kw['evidence_batches'])
        (self.root/'toy.pdb').unlink()
        self.assertEqual(len(self.result()['bindings']),4)

    def test_wrong_check_pdb_and_config_dont_erase_sibling(self):
        rec=self.kw['check_records']['r0-0']['result']
        rec['provenance']['input_sha256']='0'*64; self.seal(); r=self.result()
        self.assertEqual([x['status'] for x in r['bindings'][0]['checks']],['error','pass'])
        rec['provenance']['input_sha256']=hash_file(self.root/'toy.pdb')
        rec['configuration']['altloc']='B'; self.seal()
        self.assertEqual(self.result()['bindings'][0]['checks'][0]['status'],'error')

    def test_unsupported_check_version(self):
        self.kw['check_records']['r0-0']['result']['provenance']['check_version']='2.0'; self.seal()
        c=self.result()['bindings'][0]['checks'][0]
        self.assertEqual(c['status'],'unsupported'); self.assertEqual(c['raw_status'],'warn')
        self.assertEqual(c['observed_check_version'],'2.0')
        self.assertEqual(c['check_version'],'1.0')
        self.assertEqual(c['result_sha256'],hash_config(self.kw['check_records']['r0-0']['result']))

    def test_missing_provenance_and_malformed_record_preserved(self):
        del self.kw['check_records']['r0-0']['result']['provenance']['model_id']; self.seal()
        r=self.result(); self.assertEqual(r['bindings'][0]['checks'][0]['status'],'error')
        self.assertEqual(r['snapshots']['check_records'],self.kw['check_records'])

    def test_distinct_altloc_map_hashes(self):
        e=self.kw['bindings'][0]['checks'][0]
        e['configuration']['altloc']='B'; e['config_sha256']=hash_config(e['configuration'])
        self.kw['check_records']['r0-0']['result']['configuration']=deepcopy(e['configuration']); self.seal()
        r=self.result()['bindings'][0]
        self.assertNotEqual(r['artifact']['residue_map_sha256'],r['checks'][0]['check_residue_map_sha256'])

    def test_tampered_global_attestation_fatal(self):
        self.kw['bindings'][0]['prediction_context']='monomer'; self.fatal()

    def test_tampered_source_manifest_global_fatal(self):
        self.kw['manifests']['checks']['config']['bad']=True; self.seal(); self.fatal()

    def test_duplicate_evidence_binding_check_and_record_ids(self):
        original=deepcopy(self.kw)
        for mutation in ('evidence','binding','check','record'):
            with self.subTest(mutation=mutation):
                self.kw=deepcopy(original)
                if mutation=='evidence': self.kw['evidence_batches'][1]['candidates']['nb0']=self.kw['evidence_batches'][1]['candidates'].pop('dl0')
                elif mutation=='binding': self.kw['bindings'][1]['binding_id']='b0'
                elif mutation=='check': self.kw['bindings'][1]['checks'][0]['check_id']='c0-0'
                else: self.kw['bindings'][1]['checks'][0]['record_id']='r0-0'
                self.seal(); self.fatal()

    def test_unused_records_or_unbound_evidence_fatal(self):
        self.kw['check_records']['unused']=deepcopy(self.kw['check_records']['r0-0']); self.seal(); self.fatal()
        del self.kw['check_records']['unused']
        self.kw['bindings'].pop()
        del self.kw['check_records']['r3-0']; del self.kw['check_records']['r3-1']; self.seal(); self.fatal()

    def test_same_candidate_name_different_runs_stays_separate(self):
        self.kw['evidence_batches'][1]['candidates']['dl0']['candidate_id']='fixture-0'; self.seal()
        r=self.result(); self.assertEqual(len(r['candidate_reports']),3)
        self.assertEqual([c['candidate_id'] for c in r['candidate_reports']].count('fixture-0'),2)

    def test_unsafe_config_and_external_check_name_rejected(self):
        original=deepcopy(self.kw)
        for key in ('module','shell','command','glob','discover'):
            self.kw=deepcopy(original); self.kw['config'][key]='os.system'; self.seal(); self.fatal()
        self.kw=deepcopy(original); self.kw['bindings'][0]['checks'][0]['check']='os.system'; self.seal(); self.fatal()
        self.kw=deepcopy(original); self.kw['config']['callable']=lambda:None; self.fatal()

    def test_unsafe_paths_symlinks_and_output_escape_rejected(self):
        original=deepcopy(self.kw)
        for path in ('toy.pdb','https://example.invalid/x.pdb',str(self.root/'*.pdb'),str(self.root/'../toy.pdb'),'/tmp/outside.pdb'):
            with self.subTest(path=path):
                self.kw=deepcopy(original); self.kw['bindings'][0]['artifact']['path']=path; self.seal(); self.fatal()
        link=self.root/'alias.pdb'; link.symlink_to(self.root/'toy.pdb')
        self.kw=deepcopy(original); self.kw['bindings'][0]['artifact']['path']=str(link); self.seal(); self.fatal()
        self.kw=deepcopy(original); self.kw['manifests']['bridge']['output_paths']=[str(self.root/'outside.json')]
        self.fatal()

    def test_no_check_execution_network_process_discovery_or_writes(self):
        import structure_audit.checks as checks
        original_open,original_io_open=builtins.open,io.open
        def readonly(fn):
            def guarded(file,mode='r',*args,**kwargs):
                if any(c in mode for c in 'wax+'): raise AssertionError('Unexpected write')
                return fn(file,mode,*args,**kwargs)
            return guarded
        with ExitStack() as stack:
            for obj,attr in ((glob,'glob'),(os,'listdir'),(os,'walk'),(os,'scandir'),(Path,'glob'),(Path,'rglob'),
                             (socket,'socket'),(subprocess,'Popen'),(checks,'structure_integrity_check'),(checks,'coarse_steric_clash_check')):
                stack.enter_context(patch.object(obj,attr,side_effect=AssertionError('Forbidden '+attr)))
            stack.enter_context(patch.object(builtins,'open',side_effect=readonly(original_open)))
            stack.enter_context(patch.object(io,'open',side_effect=readonly(original_io_open)))
            self.assertEqual(self.result(),self.result())

    def test_file_changes_during_build_downgrade_all_affected_links(self):
        original=canonical_residue_map
        def changed(st,**kwargs):
            rows=original(st,**kwargs)
            with (self.root/'toy.pdb').open('a') as f: f.write('REMARK synthetic mutation\n')
            return rows
        with patch('structure_audit.check_report_bridge.canonical_residue_map',side_effect=changed):
            r=self.result()
        self.assertTrue(all(b['identity_status']=='error' for b in r['bindings']))
        self.assertEqual(r['snapshots']['check_records'],self.kw['check_records'])

    def replace_dl_structure(self, text, mode, integrity=None, clash=None):
        """Re-import explicitly supplied synthetic dl artifacts; no inference."""
        pdb=self.root/'dl-specific.pdb'; pdb.write_text(text)
        structure=read_structure(pdb,model_id='1'); rows=canonical_residue_map(structure)
        config=read_json(FIXTURES/'dl_binder_config.json'); config['prediction_mode']=mode
        prov={'model_id':'synthetic-model','checkpoint_id':None,'seed':17}
        sc=self.root/'dl_binder.sc'
        manifest=make_manifest(self.root/'dl-run/v0001',{'dl_binder_output_adapter':config},[sc,pdb],project_root=self.root,supplied_models=[prov])
        roles=[{'chain_id':'A','segment':0,'role':'candidate'}]
        if mode=='complex': roles.append({'chain_id':'B','segment':0,'role':'target'})
        binding={'candidate_id':'dl-0','target_id':None,'conformer_id':None,'pdb_path':str(pdb),
                 'pdb_model_id':'1','residue_map':rows,'chain_roles':roles}
        c=import_dl_binder_sc(sc,bindings={'synthetic_complex':binding},manifest=manifest,config=config,provenance=prov)[0]
        self.kw['manifests']['dl']=manifest
        self.kw['evidence_batches'][1]['candidates']['dl0']=c.to_dict()
        a=self.kw['bindings'][3]['artifact']
        a.update(path=str(pdb),sha256=hash_file(pdb),residue_map=rows,residue_map_sha256=hash_config(rows),chain_roles=roles)
        self.kw['bindings'][3]['prediction_context']=mode
        self.kw['manifests']['checks']['input_files'].append({'path':str(pdb),'sha256':hash_file(pdb)})
        for j,check in enumerate((structure_integrity_check(structure,integrity),coarse_steric_clash_check(structure,clash))):
            e=self.kw['bindings'][3]['checks'][j]
            e.update(configuration=check.configuration,config_sha256=hash_config(check.configuration))
            self.kw['check_records'][e['record_id']]={'manifest_id':'checks','status':check.status,'reason':None,'result':check.to_dict()}
        self.seal()
        return c

    def test_actual_monomer_adapter_sentinel_remains_quarantined(self):
        c=self.replace_dl_structure(backbone(), 'monomer',
            integrity={'expected_residues':[{'chain_id':'A','residue_id':1,'insertion_code':''}]})
        r=self.result(); dl=r['bindings'][3]
        self.assertEqual(dl['prediction_context'],'monomer')
        self.assertEqual(dl['checks'][0]['status'],'pass')
        for name in ('binder_aligned_rmsd','target_aligned_rmsd'):
            metric=next(m for m in c.metrics if m['name']==name)
            self.assertIsNone(metric['value'])
            self.assertIn('binderlen=-1',metric['missing_reason'])
            self.assertTrue(any(m['name']==name and m['evidence_id']=='dl0' for m in r['audit']['metrics']))
        self.assertEqual(r['snapshots']['evidence_batches'][1]['candidates']['dl0'],c.to_dict())

    def test_actual_geometric_fail_does_not_remove_integrity_pass(self):
        self.replace_dl_structure(backbone()+backbone(chain='B',offset=0.5), 'complex',
            integrity={'expected_residues':[{'chain_id':c,'residue_id':1,'insertion_code':''} for c in ('A','B')]},
            clash={'fail_at_count':1})
        r=self.result()
        self.assertEqual([c['status'] for c in r['bindings'][3]['checks']],['pass','fail'])
        self.assertEqual(len(r['candidate_reports']),3)

    def test_failed_identity_retains_declared_producer(self):
        (self.root/'toy.pdb').unlink()
        r=self.result()
        self.assertEqual(r['bindings'][3]['producer']['model_provenance']['seed'],17)
        self.assertEqual(r['bindings'][0]['producer']['name'],'synthetic-boltz')
        self.assertTrue(all(b['identity_status']=='error' for b in r['bindings']))

    def test_same_bytes_wrong_check_model_or_path_not_passed(self):
        original=deepcopy(self.kw)
        for key,value in (('model_id','2'),('input_path',str(self.root/'same-bytes.pdb'))):
            self.kw=deepcopy(original)
            self.kw['check_records']['r0-1']['result']['provenance'][key]=value
            self.seal(); r=self.result()
            self.assertEqual(r['bindings'][0]['checks'][1]['status'],'error')
            self.assertEqual(r['bindings'][0]['checks'][1]['raw_status'],'pass')

    def test_unknown_origin_in_notebook_cannot_be_declared_design(self):
        c=self.kw['evidence_batches'][0]['candidates']['nb0']
        next(m['raw_value'] for m in c['metrics'] if m['name']=='__notebook_import__')['origin']='unknown'
        self.kw['bindings'][0]['origin_declaration']={'origin':'design','reason':'Attempted upgrade'}
        self.seal(); r=self.result()
        self.assertEqual(r['audit']['quarantined_evidence'][0]['origin'],'origin_conflict')

    def test_invalid_expected_config_is_fatal_before_artifact_io(self):
        self.kw['bindings'][0]['checks'][0]['configuration']['module']='os.system'
        self.kw['bindings'][0]['checks'][0]['config_sha256']=hash_config(self.kw['bindings'][0]['checks'][0]['configuration'])
        self.seal()
        with patch('structure_audit.check_report_bridge.read_structure',side_effect=AssertionError('Unexpected structure read')):
            self.fatal()

    def test_roundtrip_export_and_exclusive_outputs(self):
        run=create_run_directory(self.root,'bridge-run')
        self.kw['manifests']['bridge']['output_paths']=[str(run/'report.json'),str(run/'manifest.json')]
        r=self.result(); validate_named(r,'check_report')
        self.assertEqual(json.loads(json.dumps(r,allow_nan=False)),r)
        write_json_new(run/'report.json',r); write_manifest(run/'manifest.json',self.kw['manifests']['bridge'])
        self.assertEqual(r['manifest_sha256'],hash_config(read_json(run/'manifest.json')))
        with self.assertRaises(FileExistsError): write_json_new(run/'report.json',r)
        self.assertNotEqual(run,create_run_directory(self.root,'bridge-run'))
        r['final_score']=0.9
        with self.assertRaises(ValueError): CheckReport(r).to_dict()


if __name__=='__main__': unittest.main()
