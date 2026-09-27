"""Synthetic fixture construction writes only into a caller-created test directory.

The adapter under test is read-only. No target data or upstream package is used.
"""
import builtins
from contextlib import ExitStack
from copy import deepcopy
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

from helpers import atom, backbone
from structure_audit import canonical_residue_map, read_structure
from structure_audit.evidence import sequence_hash
from structure_audit.provenance import hash_config, hash_file
from structure_audit.supplied_conformer_output_adapter import (
    ConformerImportError, ConformerImportResult, import_supplied_conformers,
)


def seal_contract(args):
    args['manifest']['config']['supplied_conformer_output_adapter'] = {
        'config': deepcopy(args['config']), 'artifacts_sha256': hash_config(args['artifacts']),
        'bindings_sha256': hash_config(args['bindings'])}
    args['manifest']['config_hash'] = hash_config(args['manifest']['config'])


def synthetic_conformer_contract(root):
    """Create exactly two small local files and three explicit sample bindings."""
    root = Path(root).resolve()
    pdb = root / 'samples.pdb'
    pdb.write_text(''.join(f'MODEL     {model:4d}\n'
                          + backbone(res=10, icode='A', offset=offset)
                          + backbone(res=14, offset=offset+4, skip=('O',) if model == 2 else ())
                          + 'ENDMDL\n' for model, offset in ((1, 0), (2, 2))))
    cif = root / 'sample.cif'
    fields = ('group_PDB id type_symbol label_atom_id label_alt_id label_comp_id '
              'label_asym_id label_seq_id auth_atom_id auth_comp_id auth_asym_id '
              'auth_seq_id pdbx_PDB_ins_code Cartn_x Cartn_y Cartn_z occupancy pdbx_PDB_model_num').split()
    lines = ['data_synthetic', 'loop_', *['_atom_site.'+f for f in fields]]
    for model in (7, 9):
        for pos, res, ins in ((1, 10, 'A'), (2, 14, '?')):
            for i, (name, element) in enumerate((('N', 'N'), ('CA', 'C'), ('C', 'C'), ('O', 'O'))):
                lines.append(f'ATOM {pos*4+i} {element} {name} . GLY X {pos} {name} GLY AA {res} {ins} {pos*4+i} 0 {model} 1.0 {model}')
    cif.write_text('\n'.join(lines)+'\n')
    null_declaration = {'details': None, 'missing_reason': 'Not supplied in synthetic fixture'}
    producer = {'name': 'synthetic-only', 'version': 'fixture-1', 'model_id': 'fixture-model',
                'checkpoint_id': None, 'seed': None,
                'missing_reasons': {'checkpoint_id': 'No model ran', 'seed': 'No RNG or inference ran'}}
    artifacts = {aid: {'kind': kind, 'path': str(path), 'sha256': hash_file(path),
                       'source_run_id': 'fixture-source', 'producer': deepcopy(producer),
                       'generation': deepcopy(null_declaration), 'conversion': deepcopy(null_declaration)}
                 for aid, kind, path in (('pdb', 'pdb', pdb), ('cif', 'mmcif', cif))}
    bindings = []
    for aid, model, chain in (('pdb', '1', 'A'), ('pdb', '2', 'A'), ('cif', '9', 'AA')):
        rows = canonical_residue_map(read_structure(artifacts[aid]['path'], model_id=model))
        bindings.append({'binding_id': 'binding-'+model, 'artifact_id': aid,
                         'ensemble_id': 'synthetic-ensemble', 'sample_id': 'sample-'+model,
                         'target_id': 'synthetic-target', 'model_id': model,
                         'selection_reason': 'Explicit fixture selection; other models out of scope',
                         'residue_map': rows, 'residue_map_sha256': hash_config(rows),
                         'chains': [{'chain_id': chain, 'segment': 0, 'role': 'target',
                                     'sequence': 'GG', 'sequence_sha256': sequence_hash('GG'),
                                     'entries': [{'sequence_position': pos, 'residue_index': pos-1, 'reason': None}
                                                 for pos in (1, 2)], 'missing_reason': None}]})
    config = {'version': '1.0', 'allowed_input_roots': [str(root)], 'altloc': 'A'}
    # Build a supplied manifest snapshot directly; do not invoke git or allocate outputs.
    manifest = {'schema_version': '1.0', 'run_id': 'fixture-import',
                'run_directory': str(root/'fixture-import/v0001'), 'timestamp': '2026-09-16T00:00:00+00:00',
                'git_commit': None, 'git_dirty': None, 'config': {}, 'config_hash': '0'*64,
                'input_files': [{'path': a['path'], 'sha256': a['sha256']} for a in artifacts.values()],
                'random_seed': None,
                'supplied_models': [{'model_id': 'fixture-model', 'checkpoint_id': None, 'seed': None}],
                'output_paths': [], 'status': 'completed', 'warnings': ['Synthetic-only; no model ran'],
                'utility_version': '0.1.0'}
    args = {'artifacts': artifacts, 'bindings': bindings, 'manifest': manifest, 'config': config}
    seal_contract(args)
    return args


class SuppliedConformerAdapterTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.args = synthetic_conformer_contract(self.root)

    def result(self):
        return import_supplied_conformers(**self.args)

    def seal(self):
        seal_contract(self.args)

    def error(self, code=None):
        with self.assertRaises(ConformerImportError) as caught:
            self.result()
        error = caught.exception
        if code:
            self.assertEqual(error.diagnostics[0]['code'], code)
        self.assertEqual(error.diagnostics[0]['severity'], 'error')
        self.assertFalse(hasattr(error, 'samples'))
        self.assertFalse(hasattr(error, 'result'))
        return error.diagnostics[0]

    def update_file(self, aid, text, *, maps=True):
        a = self.args['artifacts'][aid]
        Path(a['path']).write_text(text)
        a['sha256'] = hash_file(a['path'])
        for item in self.args['manifest']['input_files']:
            if item['path'] == a['path']:
                item['sha256'] = a['sha256']
        if maps:
            for b in self.args['bindings']:
                if b['artifact_id'] == aid:
                    b['residue_map'] = canonical_residue_map(read_structure(a['path'], model_id=b['model_id']))
                    b['residue_map_sha256'] = hash_config(b['residue_map'])
        self.seal()

    def test_three_explicit_samples_pdb_and_mmcif_identity(self):
        before = deepcopy(self.args)
        result = self.result()
        self.assertIsInstance(result, ConformerImportResult)
        self.assertEqual(len(result.samples), 3)
        self.assertEqual([s['model_id'] for s in result.samples], ['1', '2', '9'])
        self.assertEqual([s['sample_id'] for s in result.samples], ['sample-1', 'sample-2', 'sample-9'])
        self.assertEqual(result.samples[2]['format'], 'mmcif')
        row = result.samples[2]['residue_map'][0]
        self.assertEqual((row['chain_id'], row['label_chain_id'], row['residue_id'], row['label_seq_id'], row['insertion_code']),
                         ('AA', 'X', 10, 1, 'A'))
        self.assertEqual(result.samples[0]['chains'][0]['status'], 'matched')
        self.assertEqual(result.samples[1]['residue_map'][1]['missing_backbone_atoms'], ['O'])
        self.assertEqual(self.args, before)
        self.assertFalse((self.root/'fixture-import').exists())

    def test_snapshots_hashes_and_strict_json_detached(self):
        result = self.result()
        payload = result.to_dict()
        self.assertEqual(json.loads(json.dumps(payload, allow_nan=False)), payload)
        self.assertEqual(payload['audit']['bindings'], self.args['bindings'])
        self.assertEqual(payload['audit']['manifest_sha256'], hash_config(self.args['manifest']))
        self.assertEqual(payload['samples'][0]['binding_sha256'], hash_config(self.args['bindings'][0]))
        payload['samples'].clear()
        self.assertEqual(len(result.samples), 3)
        self.args['artifacts']['pdb']['producer']['name'] = 'changed-caller'
        self.assertEqual(result.samples[0]['artifact']['producer']['name'], 'synthetic-only')
        with self.assertRaises(TypeError):
            iter(result)

    def test_no_candidate_confidence_or_report_fields(self):
        data = self.result().to_dict()
        self.assertEqual(set(data), {'samples', 'diagnostics', 'audit'})
        forbidden = {'candidate_id', 'candidates', 'b_factors', 'plddt', 'checks', 'candidate_reports', 'score'}
        def visit(obj):
            if isinstance(obj, dict):
                self.assertFalse(set(obj) & forbidden)
                for value in obj.values(): visit(value)
            elif isinstance(obj, list):
                for value in obj: visit(value)
        visit(data)
        self.assertEqual(data['samples'][0]['identity_status'], 'verified_local')
        self.assertIn('no equilibrium population', data['audit']['limitations'][1])

    def test_unknown_sequence_and_provenance_retained(self):
        c = self.args['bindings'][0]['chains'][0]
        c.update(sequence=None, sequence_sha256=None, entries=None, missing_reason='Not supplied')
        p = self.args['artifacts']['pdb']['producer']
        for k in ('name', 'version', 'model_id', 'checkpoint_id', 'seed'):
            p[k] = None
        p['missing_reasons'] = {k: 'Unknown source' for k in ('name', 'version', 'model_id', 'checkpoint_id', 'seed')}
        self.seal()
        r = self.result()
        self.assertIsNone(r.samples[0]['chains'][0]['sequence'])
        self.assertEqual(r.samples[0]['producer_verification'], 'caller_supplied_not_verified')
        self.assertIn('sequence_not_supplied', [d['code'] for d in r.diagnostics])

    def test_partial_mapping_preserves_missing_and_unmapped(self):
        c = self.args['bindings'][0]['chains'][0]
        c['entries'][1].update(residue_index=None, reason='Explicitly unmapped')
        self.seal()
        r = self.result()
        self.assertEqual(r.samples[0]['chains'][0]['status'], 'partial')
        self.assertEqual(r.samples[0]['chains'][0]['unmapped_observed_residues'], [1])
        self.assertIn('partial_sequence_mapping', [d['code'] for d in r.diagnostics])

    def test_sequence_mismatch_and_wrong_hash(self):
        c = self.args['bindings'][0]['chains'][0]
        c['sequence'] = 'GA'; self.seal()
        self.error('sequence_binding')
        c['sequence_sha256'] = sequence_hash('GA'); self.seal()
        self.error('sequence_mismatch')

    def test_invalid_sequence_mapping_entries(self):
        original = deepcopy(self.args)
        for entries in ([{'sequence_position': 1, 'residue_index': 0, 'reason': None}],
                        [{'sequence_position': 1, 'residue_index': 0, 'reason': None},
                         {'sequence_position': 2, 'residue_index': 0, 'reason': None}],
                        [{'sequence_position': 1, 'residue_index': None, 'reason': None},
                         {'sequence_position': 2, 'residue_index': 1, 'reason': None}]):
            with self.subTest(entries=entries):
                self.args = deepcopy(original)
                self.args['bindings'][0]['chains'][0]['entries'] = entries
                self.seal(); self.error('sequence_binding')

    def test_wrong_chain_role_segment_or_inventory(self):
        original = deepcopy(self.args)
        for key, value in (('chain_id', 'B'), ('segment', 1), ('segment', True), ('role', 'candidate')):
            with self.subTest(key=key, value=value):
                self.args = deepcopy(original)
                self.args['bindings'][0]['chains'][0][key] = value
                self.seal(); self.error('chain_binding')

    def test_ter_and_blank_chain_are_preserved_no_cross_chain_mapping(self):
        text = 'MODEL        1\n'+backbone(res=10, chain='')+'TER\n'+backbone(res=20, chain='')+'ENDMDL\n'
        self.args['bindings'] = self.args['bindings'][:1]
        del self.args['artifacts']['cif']
        c = self.args['bindings'][0]['chains'][0]
        c.update(chain_id='', sequence='G', sequence_sha256=sequence_hash('G'),
                 entries=[{'sequence_position': 1, 'residue_index': 0, 'reason': None}])
        other = deepcopy(c); other['segment'] = 1; other['entries'][0]['residue_index'] = 1
        self.args['bindings'][0]['chains'].append(other)
        self.update_file('pdb', text)
        self.assertEqual([r['segment'] for r in self.result().samples[0]['residue_map']], [0, 1])
        c['entries'][0]['residue_index'] = 1
        self.seal(); self.error('chain_binding')

    def test_default_altloc_no_fallback(self):
        path = self.root/'samples.pdb'
        text = path.read_text().replace(' CA GLY', ' CABGLY')
        self.update_file('pdb', text)
        sample = self.result().samples[0]
        self.assertIn('CA', sample['residue_map'][0]['missing_backbone_atoms'])
        self.assertEqual(sample['residue_map'][0]['selected_altloc'], 'A')

    def test_native_alphaflow_headers_rejected_without_repair(self):
        original = (self.root/'samples.pdb').read_text()
        for header in ('MODEL 0', 'MODEL 1', 'MODEL 123'):
            with self.subTest(header=header):
                self.update_file('pdb', original.replace('MODEL        1', header), maps=False)
                before = (self.root/'samples.pdb').read_bytes()
                d = self.error('native_alphaflow_model_header')
                self.assertEqual(d['locator'], 1)
                self.assertEqual(d['artifact_id'], 'pdb')
                self.assertEqual(before, (self.root/'samples.pdb').read_bytes())

    def test_standard_pdb_zero_model_is_not_unpadded_native_header(self):
        text = (self.root/'samples.pdb').read_text().replace('MODEL        1', 'MODEL        0')
        self.args['bindings'][0]['model_id'] = '0'
        self.update_file('pdb', text)
        self.assertEqual(self.result().samples[0]['model_id'], '0')

    def test_no_implicit_model_selection(self):
        original = deepcopy(self.args)
        for model in (None, '', '7', '01'):
            with self.subTest(model=model):
                self.args = deepcopy(original)
                self.args['bindings'][0]['model_id'] = model
                self.seal(); self.error()

    def test_stale_map_and_map_hash(self):
        b = self.args['bindings'][0]
        b['residue_map'][0]['chain_id'] = 'wrong'
        self.seal(); self.error('residue_map_mismatch')
        b['residue_map_sha256'] = hash_config(b['residue_map'])
        self.seal(); self.error('residue_map_mismatch')

    def test_manifest_config_and_attestation_tampering(self):
        self.args['manifest']['config_hash'] = '0'*64
        self.error('manifest_contract')
        self.seal()
        self.args['bindings'][0]['sample_id'] = 'changed'
        self.error('manifest_contract')

    def test_manifest_input_missing_duplicated_or_wrong_hash(self):
        original = deepcopy(self.args)
        for inputs in ([], original['manifest']['input_files']*2,
                       [{**x, 'sha256': '0'*64} for x in original['manifest']['input_files']]):
            with self.subTest(inputs=inputs):
                self.args = deepcopy(original)
                self.args['manifest']['input_files'] = inputs
                self.error('manifest_artifact_mismatch')

    def test_manifest_timestamp_and_output_containment(self):
        self.args['manifest']['timestamp'] = '2026-09-16T00:00:00'
        self.error('manifest_contract')
        self.args['manifest']['timestamp'] = '2026-09-16T00:00:00+00:00'
        self.args['manifest']['output_paths'] = [str(self.root/'escaped.json')]
        self.error('manifest_contract')

    def test_unconsumed_manifest_inputs_not_opened(self):
        self.args['manifest']['input_files'].append({'path': '/nonexistent/not-consumed.pdb', 'sha256': '0'*64})
        self.assertEqual(len(self.result().samples), 3)

    def test_producer_manifest_and_missing_reasons(self):
        self.args['artifacts']['pdb']['producer']['model_id'] = 'different'
        self.seal(); self.error('manifest_producer_mismatch')
        self.args['artifacts']['pdb']['producer']['model_id'] = 'fixture-model'
        self.args['artifacts']['pdb']['producer']['missing_reasons'] = {}
        self.seal(); self.error('invalid_contract')

    def test_producer_seed_and_forbidden_verified_claim(self):
        original = deepcopy(self.args)
        for seed in (-1, True, '7'):
            self.args = deepcopy(original)
            p = self.args['artifacts']['pdb']['producer']; p['seed'] = seed
            del p['missing_reasons']['seed']
            self.seal(); self.error('invalid_contract')
        self.args = deepcopy(original)
        self.args['artifacts']['pdb']['producer']['status'] = 'verified'
        self.seal(); self.error('invalid_contract')

    def test_generation_conversion_declarations_are_inert_snapshots(self):
        a = self.args['artifacts']['cif']
        a['generation'] = {'details': {'model_variant': 'synthetic-only', 'steps': 3, 'tmax': 0.2}, 'missing_reason': None}
        a['conversion'] = {'details': {'tool': 'synthetic fixture builder', 'source_sha256': '0'*64,
                                     'description': 'Declared example, not independently verified'}, 'missing_reason': None}
        self.seal()
        self.assertEqual(self.result().samples[2]['artifact'], a)
        a['generation']['missing_reason'] = 'contradicts supplied details'
        self.seal(); self.error('invalid_contract')

    def test_duplicate_binding_sample_and_selected_model(self):
        original = deepcopy(self.args)
        for field, value in (('binding_id', 'binding-1'), ('sample_id', 'sample-1'), ('model_id', '1')):
            with self.subTest(field=field):
                self.args = deepcopy(original)
                self.args['bindings'][1][field] = value
                self.seal(); self.error('duplicate_identity')
        self.args = deepcopy(original)
        self.args['bindings'][1].update(ensemble_id='another', sample_id='sample-1')
        self.seal(); self.error('duplicate_identity')

    def test_target_conflict_unbound_and_unregistered_artifacts(self):
        original = deepcopy(self.args)
        self.args['bindings'][1]['target_id'] = 'different-target'
        self.seal(); self.error('target_conflict')
        self.args = deepcopy(original); self.args['bindings'] = self.args['bindings'][:2]
        self.seal(); self.error('unbound_artifact')
        self.args = deepcopy(original); self.args['bindings'][0]['artifact_id'] = 'absent'
        self.seal(); self.error('invalid_contract')

    def test_source_sample_ids_are_target_scoped(self):
        b = self.args['bindings'][2]
        b.update(target_id='another-synthetic-target', ensemble_id='another-ensemble', sample_id='sample-1')
        self.seal()
        result = self.result()
        self.assertEqual(result.samples[0]['sample_id'], result.samples[2]['sample_id'])
        self.assertNotEqual(result.samples[0]['target_id'], result.samples[2]['target_id'])

    def test_unsafe_paths_rejected_before_artifact_read(self):
        original = deepcopy(self.args)
        for path in ('samples.pdb', 'https://example.invalid/sample.pdb', str(self.root/'*.pdb'),
                     str(self.root/'../escape.pdb'), '/tmp/outside.pdb'):
            with self.subTest(path=path):
                self.args = deepcopy(original); self.args['artifacts']['pdb']['path'] = path; self.seal()
                with patch('structure_audit.supplied_conformer_output_adapter.hash_file', side_effect=AssertionError('unexpected read')):
                    self.error('unsafe_path')

    def test_symlink_alias_and_escape(self):
        original = deepcopy(self.args)
        for name, target in (('alias.pdb', self.root/'samples.pdb'), ('escape.pdb', Path('/tmp/missing-external.pdb'))):
            link = self.root/name; link.symlink_to(target)
            self.args = deepcopy(original); self.args['artifacts']['pdb']['path'] = str(link); self.seal()
            self.error('unsafe_path')

    def test_stale_missing_or_nonregular_artifact(self):
        path = self.root/'samples.pdb'
        path.write_text(path.read_text()+'REMARK changed\n')
        self.error('stale_artifact_hash')
        path.unlink(); self.error('artifact_read_error')
        path.mkdir(); self.error('artifact_read_error')

    def test_same_basename_different_explicit_paths(self):
        directory = self.root/'nested'; directory.mkdir()
        source = self.args['artifacts']['cif']['path']
        dest = directory/'samples.pdb'
        dest.write_bytes((self.root/'samples.pdb').read_bytes())
        a = self.args['artifacts']['cif']; a.update(path=str(dest), kind='pdb', sha256=hash_file(dest))
        for item in self.args['manifest']['input_files']:
            if item['path'] == source: item.update(path=str(dest), sha256=a['sha256'])
        b = self.args['bindings'][2]; b['model_id'] = '1'; b['chains'][0]['chain_id'] = 'A'
        b['residue_map'] = canonical_residue_map(read_structure(dest, model_id='1'))
        b['residue_map_sha256'] = hash_config(b['residue_map']); self.seal()
        r = self.result()
        self.assertEqual(len(r.samples), 3)
        self.assertNotEqual(r.samples[0]['artifact']['path'], r.samples[2]['artifact']['path'])

    def test_duplicate_file_registry_rejected(self):
        self.args['artifacts']['duplicate'] = deepcopy(self.args['artifacts']['pdb'])
        self.seal(); self.error('invalid_contract')

    def test_unsupported_configs_formats_and_nonfinite_contract(self):
        original = deepcopy(self.args)
        for cfg in ({**original['config'], 'altloc': 'B'}, {**original['config'], 'version': '2.0'},
                    {**original['config'], 'shell': 'anything'}):
            self.args = deepcopy(original); self.args['config'] = cfg; self.seal(); self.error()
        self.args = deepcopy(original); self.args['artifacts']['pdb']['kind'] = 'pickle'
        self.seal(); self.error('unsupported_format')
        self.args = deepcopy(original); self.args['config']['bad'] = float('nan')
        self.error('invalid_contract')

    def test_mmcif_unsupported_and_malformed(self):
        path = self.root/'sample.cif'; original = path.read_text()
        self.update_file('cif', original.replace('_atom_site.auth_asym_id', '_atom_site.unknown_id'), maps=False)
        self.error('unsupported_format')
        self.update_file('cif', original+'extra\n', maps=False)
        self.error('structure_parse_error')

    def test_non_json_object_hooks_are_not_executed(self):
        class NotJSON:
            def __deepcopy__(self, memo):
                raise AssertionError('Custom hook must not execute')
        self.args['config']['object'] = NotJSON()
        self.error('invalid_contract')

    def test_b_factor_values_are_not_imported(self):
        path = self.root/'samples.pdb'
        original_maps = deepcopy([b['residue_map'] for b in self.args['bindings'][:2]])
        text = '\n'.join(line[:60]+' 99.99'+line[66:] if line.startswith('ATOM  ') else line
                         for line in path.read_text().splitlines())+'\n'
        self.update_file('pdb', text)
        result = self.result()
        self.assertEqual([s['residue_map'] for s in result.samples[:2]], original_maps)
        self.assertNotIn('99.99', json.dumps(result.to_dict()))

    def test_duplicate_atoms_and_nonfinite_coordinates(self):
        original = (self.root/'samples.pdb').read_text()
        extra = atom(100, name='CA', res=10, icode='A', residue='GLY')
        self.update_file('pdb', original.replace('MODEL        1\n', 'MODEL        1\n'+extra), maps=False)
        self.error('ambiguous_structure_identity')
        self.update_file('pdb', original.replace('   0.000', '     nan', 1), maps=False)
        self.error('nonfinite_coordinates')

    def test_hetatm_scope_retained_without_sequence_assignment(self):
        path = self.root/'samples.pdb'
        extra = atom(99, res=99, residue='HOH').replace('ATOM  ', 'HETATM')
        self.update_file('pdb', path.read_text().replace('ENDMDL', extra+'ENDMDL'))
        r = self.result()
        self.assertEqual(r.samples[0]['residue_map'][-1]['record_group'], 'HETATM')
        self.assertEqual(r.samples[0]['chains'][0]['sequence'], 'GG')
        self.assertIn('residue_scope_warning', [d['code'] for d in r.diagnostics])

    def test_late_binding_failure_has_no_partial_result(self):
        self.args['bindings'][-1]['chains'][0]['chain_id'] = 'wrong'
        self.seal()
        d = self.error('chain_binding')
        self.assertEqual(d['binding_id'], 'binding-9')

    def test_late_hash_change_is_fatal(self):
        from structure_audit.supplied_conformer_output_adapter import canonical_residue_map as original
        calls = 0
        def changed(structure, **kwargs):
            nonlocal calls
            calls += 1
            rows = original(structure, **kwargs)
            if calls == 3:
                path = self.root/'samples.pdb'
                path.write_text(path.read_text()+'REMARK late change\n')
            return rows
        with patch('structure_audit.supplied_conformer_output_adapter.canonical_residue_map', side_effect=changed):
            self.error('stale_artifact_hash')

    def test_no_io_side_effects_discovery_subprocess_checks_or_upstream_imports(self):
        import structure_audit.checks as checks
        before = {p.name: p.read_bytes() for p in (self.root/'samples.pdb', self.root/'sample.cif')}
        original_open, original_io_open, original_import = builtins.open, io.open, builtins.__import__
        def readonly(fn):
            def guarded(file, mode='r', *args, **kwargs):
                if any(c in mode for c in 'wax+'): raise AssertionError('Unexpected write')
                return fn(file, mode, *args, **kwargs)
            return guarded
        def guarded_import(name, *args, **kwargs):
            if name.split('.')[0] in {'alphaflow', 'openfold', 'MSA_Pairformer', 'torch', 'numpy', 'pandas', 'Bio'}:
                raise AssertionError('Upstream import: '+name)
            return original_import(name, *args, **kwargs)
        with ExitStack() as stack:
            for obj, attr in ((glob, 'glob'), (os, 'listdir'), (os, 'walk'), (os, 'scandir'), (Path, 'glob'), (Path, 'rglob'),
                              (socket, 'socket'), (socket, 'create_connection'), (subprocess, 'Popen'), (os, 'system'),
                              (Path, 'mkdir'), (Path, 'unlink'), (Path, 'rename'), (os, 'putenv'),
                              (checks, 'structure_integrity_check'), (checks, 'coarse_steric_clash_check')):
                stack.enter_context(patch.object(obj, attr, side_effect=AssertionError('Forbidden '+attr)))
            stack.enter_context(patch.object(builtins, 'open', side_effect=readonly(original_open)))
            stack.enter_context(patch.object(io, 'open', side_effect=readonly(original_io_open)))
            stack.enter_context(patch.object(builtins, '__import__', side_effect=guarded_import))
            self.assertEqual(self.result().to_dict(), self.result().to_dict())
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.root/'samples.pdb', self.root/'sample.cif')})


if __name__ == '__main__':
    unittest.main()
