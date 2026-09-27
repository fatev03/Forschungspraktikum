"""Original tiny synthetic inputs only; no production artifact is opened/copied."""

import base64
import builtins
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from structure_audit.colabfold_a3m_lossless import (
    ColabFoldA3MError, ColabFoldA3MResult, ColabFoldA3MReaderResult, parse_colabfold_a3m,
)


AA20 = 'ACDEFGHIKLMNPQRSTVWY'
RAW = (b'#opaque\tannotation\r\n>repeat first\r\nxA.-cCggGx\r\n'
       b'>repeat query\r\nA-\r\nCG\r\n>repeat first\r\nA-CG\r\n>other\nC-X-')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def json_hash(value):
    return sha(json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=False, allow_nan=False).encode('utf-8'))


def contract(root, raw=RAW, query='ACG', selector=None):
    """Write a new toy file in a temporary directory; never use external inputs."""
    path = root / 'toy.a3m'
    path.write_bytes(raw)
    fields = 'name version database database_version search_settings'.split()
    artifact = dict(artifact_id='toy', path=str(path), sha256=sha(raw), format='a3m',
        source_kind='caller_declared_colabfold_mmseqs2_style_a3m',
        source_kind_status='caller_supplied_not_verified',
        producer=dict.fromkeys(fields),
        provenance=dict(details=None, missing_reason='Not supplied for synthetic input'))
    artifact['producer']['missing_reasons'] = {k: 'Not supplied' for k in fields}
    config = dict(profile_id='colabfold_a3m_lossless_v1', profile_version='1.0',
        profile_selection='explicit_only', allowed_input_roots=[str(root)],
        expected_artifact_sha256=sha(raw),
        query_selector=selector or {'record_occurrence_id': 'record:1@header_line:4'},
        canonical_query_sequence=query, canonical_query_sequence_sha256=sha(query.encode('ascii')),
        query_gap_policy='preserve_and_map_to_null',
        lowercase_x_policy=dict(handling='retain_with_locator_and_anchor',
            match_column_contribution='none', coverage_contribution='none',
            match_denominator_contribution='none', frequency_entropy_contribution='none'),
        unknown_tokens=['X'], unknown_policy='retain_as_unknown')
    return dict(artifact=artifact, config=config)


def metric_policy(**changes):
    policy = dict(include_query_in_statistics=True,
        sequence_duplicate_key='parsed_match_tokens', duplicate_policy='keep',
        representative_selection='first_eligible_occurrence_in_file_order',
        gap_denominator='all_observations', unknown_denominator='all_observations',
        frequency_denominator='valid_amino_acids', entropy_alphabet=AA20, entropy_log_base=2,
        entropy_gap_policy='exclude', entropy_unknown_policy='exclude', entropy_pseudocount=0,
        coverage_token_policy='valid_amino_acids', coverage_denominator='canonical_query_length',
        coverage_aggregation='any_contributing_row')
    policy.update(changes)
    return policy


def synthetic_binding(args):
    """Map the toy A-CG query onto three invented canonical residue rows."""
    rows = [dict(residue_index=i, model_id='77', chain_id='', segment=2, record_group='ATOM',
        residue_id=number, insertion_code='B' if i == 1 else '', residue_name=name,
        label_chain_id='LABEL', label_seq_id=i+1, source_lines=[10+i], atom_names=['CA'],
        selected_altloc='A', missing_backbone_atoms=['N', 'C', 'O'], warnings=[])
        for i, (name, number) in enumerate([('ALA', -3), ('CYS', 8), ('GLY', 19)])]
    columns = [dict(query_column=i, sequence_position=p, reason='query_gap' if p is None else None)
               for i, p in enumerate([1, None, 2, 3])]
    sequence = [dict(sequence_position=i+1, residue_index=i, reason=None) for i in range(3)]
    binding = dict(binding_id='toy-binding', artifact_id='toy',
        artifact_sha256=args['artifact']['sha256'], record_occurrence_id='record:1@header_line:4',
        canonical_query_sequence_sha256=sha(b'ACG'), target_id='toy-target', role='receptor',
        model_id='77', chain_id='', segment=2, column_map=columns, sequence_map=sequence,
        residue_map=rows, map_source=dict(artifact_id='toy-structure', sha256='a'*64,
                                        source_run_id='toy-map-run', model_id='77'))
    reseal_binding(binding)
    return binding


def reseal_binding(binding):
    for key in ('column_map', 'sequence_map', 'residue_map'):
        binding[key+'_sha256'] = json_hash(binding[key])


class ColabFoldLosslessTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.args = contract(self.root)

    def result(self):
        return parse_colabfold_a3m(**self.args)

    def data(self):
        return self.result().to_dict()

    def file(self, raw, selector=None, query='ACG'):
        self.args = contract(self.root, raw, query, selector or {'header_line': 1, 'raw_header': '>q'})

    def enable_metrics(self, **changes):
        self.args['config'].update(metrics_enabled=True, metric_policy=metric_policy(**changes))

    def enable_binding(self):
        self.args['config']['binding_enabled'] = True
        self.args['binding'] = synthetic_binding(self.args)

    def error(self, code=None):
        with self.assertRaises(ColabFoldA3MError) as caught:
            self.result()
        e = caught.exception
        self.assertFalse(any(hasattr(e, k) for k in ('result', 'rows', 'metrics', 'binding')))
        d = e.diagnostics[0]
        self.assertEqual(d['severity'], 'fatal')
        if code:
            self.assertEqual(d['code'], code)
        json.dumps(e.diagnostics, allow_nan=False)
        return d

    def test_lossless_bytes_fragments_line_endings_and_nonfirst_query(self):
        result = self.result()
        self.assertIsInstance(result, ColabFoldA3MResult)
        d = result.to_dict()
        self.assertEqual(result.reconstruct_bytes(), RAW)
        self.assertEqual(base64.b64decode(d['artifact']['raw_bytes_base64']), RAW)
        self.assertEqual(d['reconstructed_sha256'], sha(RAW))
        self.assertEqual(d['query']['selected_occurrence'], 'record:1@header_line:4')
        self.assertEqual(d['records'][1]['raw_sequence_tokens'], 'A-CG')
        self.assertEqual([f['line_ending'] for f in d['records'][1]['sequence_fragments']], ['CRLF', 'CRLF'])
        self.assertEqual(d['records'][-1]['header_fragment']['line_ending'], 'LF')
        self.assertEqual(d['records'][-1]['sequence_fragments'][0]['line_ending'], 'none')
        self.assertEqual(d['position_bases']['source_character'], 1)
        self.assertEqual(d['position_bases']['parsed_column'], 0)

    def test_locators_point_to_exact_source_bytes(self):
        d = self.data()
        lines = RAW.splitlines(keepends=True)
        for row in d['records']:
            for token in row['tokens']:
                self.assertEqual(RAW[token['artifact_byte_offset']:token['artifact_byte_offset']+1],
                                 token['raw_token'].encode('ascii'))
                self.assertEqual(chr(lines[token['source_line']-1][token['source_character']-1]),
                                 token['raw_token'])
                self.assertEqual(token['record_occurrence_id'], row['record_occurrence_id'])
        xs = d['unknown_token_summary']['lowercase_x']
        self.assertEqual((xs['count'], xs['affected_occurrences']), (2, 1))
        self.assertEqual([p['insertion_anchor'] for p in xs['locators']], [0, 4])
        self.assertEqual([p['source_character'] for p in xs['locators']], [1, 10])
        self.assertEqual(d['insertion_transform_summary'], dict(
            standard_insertion=3, insertion_padding=1, unknown_lowercase_insertion=2))
        for token in d['records'][0]['tokens']:
            if token['raw_token'] in 'xcg.':
                self.assertIsNone(token['parsed_column'])
                self.assertIsNone(token['query_sequence_position'])

    def test_query_gaps_remain_as_projection_tokens_without_canonical_positions(self):
        d = self.data()
        self.assertEqual(d['records'][1]['parsed_match_tokens'], 'A-CG')
        self.assertEqual([t['parsed_column'] for t in d['records'][1]['tokens']], [0, 1, 2, 3])
        self.assertTrue(all(t['query_sequence_position'] is None for t in d['records'][1]['tokens']))
        self.assertIsNone(d['records'][0]['tokens'][3]['query_sequence_position'])
        self.assertIsNone(d['binding'])

    def test_preamble_is_opaque_even_when_numeric_and_wrong(self):
        for preamble in (b'#999\t17\n', '#not metadata \u03bb\r\n'.encode('utf-8')):
            with self.subTest(preamble=preamble):
                raw = preamble+b'>q\nACG\n'
                self.file(raw, {'header_line': 2, 'raw_header': '>q'})
                result = self.result()
                self.assertEqual(result.reconstruct_bytes(), raw)
                p = result.data['raw_preamble']
                self.assertEqual(p['source_line'], 1)
                self.assertIsNone(p['parse_result']['semantic_fields'])

    def test_duplicate_id_inventory_is_separate_from_sequences(self):
        d = self.data()
        ids = d['raw_id_duplicate_summary']
        self.assertEqual((ids['unique_count'], ids['duplicate_occurrences'], ids['duplicate_member_count']), (2, 2, 3))
        self.assertEqual(ids['groups'][0]['header_lines'], [2, 4, 7])
        self.assertEqual(ids['groups'][0]['header_relationship'], 'mixed_full_header_and_id')
        seq = d['sequence_duplicate_summary']
        self.assertEqual(seq['raw']['unique_count'], 3)
        self.assertEqual(seq['parsed']['unique_count'], 2)
        self.assertEqual(len({r['record_occurrence_id'] for r in d['records']}), 4)
        self.assertEqual([r['raw_header'] for r in d['records'][:3]], ['>repeat first', '>repeat query', '>repeat first'])

    def test_same_id_with_different_sequences_does_not_trigger_sequence_error(self):
        self.file(b'>q\nACG\n>q\nCCG\n')
        self.enable_metrics(duplicate_policy='error')
        d = self.data()
        self.assertEqual(d['raw_id_duplicate_summary']['groups'][0]['header_relationship'], 'same_full_header')
        self.assertEqual(d['sequence_duplicate_summary']['parsed']['duplicate_groups'], 0)

    def test_both_explicit_selector_forms_select_same_occurrence(self):
        first = self.data()
        self.args['config']['query_selector'] = dict(header_line=4, raw_header='>repeat query')
        second = self.data()
        self.assertEqual(first['query']['selected_occurrence'], second['query']['selected_occurrence'])
        self.assertEqual(first['records'], second['records'])

    def test_missing_selector_never_selects_by_id_sequence_or_order(self):
        self.args['config']['query_selector'] = None
        d = self.error('ambiguous_query_occurrence')
        self.assertEqual(len(d['details']['candidates']), 2)
        self.file(b'>q\nACG\n')
        self.args['config']['query_selector'] = None
        self.error('invalid_query_selector')
        self.file(b'>q\nCCC\n')
        self.args['config']['query_selector'] = None
        self.error('invalid_query_selector')

    def test_bad_selectors_fail_closed(self):
        selectors = [{}, {'raw_record_id': 'repeat'}, {'header_line': True, 'raw_header': '>repeat first'},
            {'header_line': 3, 'raw_header': '>repeat first'}, {'header_line': 4, 'raw_header': '>repeat'},
            {'record_occurrence_id': 'record:1@header_line:4', 'header_line': 4},
            {'record_occurrence_id': 'record:01@header_line:4'},
            {'record_occurrence_id': 'record:1@header_line:2'},
            {'record_occurrence_id': 'record:12@header_line:4'}, {'record_occurrence_id': 1}]
        for selector in selectors:
            with self.subTest(selector=selector):
                self.args['config']['query_selector'] = selector
                self.error()

    def test_generic_canonical_sequences_and_gaps(self):
        for seq in ['W', 'MSTNK', AA20]:
            with self.subTest(seq=seq):
                query = '-'+seq[:1]+'--'+seq[1:]+'-'
                self.file(('>q\r\n'+query).encode(), query=seq)
                d = self.data()
                self.assertEqual(d['query']['canonical_sequence'], seq)
                self.assertEqual(d['inventory']['alignment_width'], len(seq)+4)
                tokens = d['records'][0]['tokens']
                self.assertEqual(sum(t['raw_token'] != '-' for t in tokens), len(seq))
                self.assertTrue(all(t['query_sequence_position'] is None for t in tokens))

    def test_query_forbids_insertions_padding_unknown_and_stop(self):
        for token in 'ax.X*BZJUO':
            with self.subTest(token=token):
                self.file(('>q\nA'+token+'CG\n').encode())
                d = self.error('invalid_query_token')
                self.assertEqual(d['locator']['source_character'], 2)

    def test_query_sequence_and_hash_must_match(self):
        self.file(b'>q\nACC\n')
        self.error('query_mismatch')
        self.file(b'>q\nACG\n')
        self.args['config']['canonical_query_sequence_sha256'] = '0'*64
        self.error('query_mismatch')

    def test_only_supported_uppercase_unknown_pairs(self):
        for tokens, policy in [([], 'retain_as_unknown'), (['X'], 'reject'), (['B'], 'retain_as_unknown'),
                               (['X', 'X'], 'retain_as_unknown'), (['X'], 'ignore'), ('X', 'retain_as_unknown')]:
            with self.subTest(tokens=tokens, policy=policy):
                self.args['config'].update(unknown_tokens=tokens, unknown_policy=policy)
                self.error('unsupported_config')

    def test_x_reject_and_retain_are_explicit(self):
        self.args['config'].update(unknown_tokens=[], unknown_policy='reject')
        d = self.error('uppercase_unknown_without_policy')
        self.assertEqual(d['locator']['source_line'], 10)
        self.args['config'].update(unknown_tokens=['X'], unknown_policy='retain_as_unknown')
        self.assertEqual(self.data()['unknown_token_summary']['uppercase_X']['count'], 1)
        self.file(b'>q\nACG\n>other\nxAxCxGx\n')
        self.args['config'].update(unknown_tokens=[], unknown_policy='reject')
        self.assertEqual(self.data()['unknown_token_summary']['lowercase_x']['count'], 4)

    def test_unsupported_tokens_are_never_normalized(self):
        for token in 'BZJUObzjuo*?012_ \t\u03bb':
            with self.subTest(token=token):
                self.file(('>q\nACG\n>other\nA'+token+'CG\n').encode())
                d = self.error('unsupported_token')
                self.assertEqual(d['details']['token'], token)
                self.assertEqual(d['locator']['source_line'], 4)

    def test_invalid_structure_encoding_and_containers_fail(self):
        cases = [b'', b'#only preamble\n', b'>q\n', b'>q\n>other\nACG\n', b'>q\n\nACG\n',
            b'ACG\n>q\nACG\n', b'> q\nACG\n', b'>q\rACG\r', b'>q\nAC\x00G',
            b'\xef\xbb\xbf>q\nACG', b'>q\nAC\xffG', b'{\\rtf1 content}', b'<html>text</html>',
            b'#STOCKHOLM 1.0\nq ACG\n//', b'HHsearch 1.5\n', b'\x1f\x8bcompressed']
        for raw in cases:
            with self.subTest(raw=raw):
                self.file(raw)
                self.error()

    def test_nonleading_or_repeated_preamble_rejected(self):
        for raw in (b'>q\nACG\n#late\n', b'#first\n#second\n>q\nACG\n'):
            with self.subTest(raw=raw):
                self.file(raw)
                self.error('preamble_profile_mismatch')

    def test_ragged_rows_rejected_after_projection(self):
        for seq in ('AC', 'ACGG', 'ax...'):
            with self.subTest(seq=seq):
                self.file(('>q\nACG\n>other\n'+seq+'\n').encode())
                self.error('ragged_rows')

    def test_profile_not_inferred_or_aliased(self):
        original = deepcopy(self.args)
        for key, val in [('profile_id', 'a3m_match_columns_v1'), ('profile_id', None),
                         ('profile_version', '1.1'), ('profile_selection', 'auto'),
                         ('query_gap_policy', 'remove')]:
            with self.subTest(key=key, val=val):
                self.args = deepcopy(original)
                self.args['config'][key] = val
                self.error('profile_mismatch')
        self.args = deepcopy(original)
        del self.args['config']['profile_id']
        self.error('unsupported_config')

    def test_source_declaration_and_exact_suffix_required(self):
        original = deepcopy(self.args)
        for key, val in [('source_kind', 'verified_mmseqs2'), ('format', 'fasta'),
                         ('source_kind_status', 'verified')]:
            with self.subTest(key=key):
                self.args = deepcopy(original)
                self.args['artifact'][key] = val
                self.error('unsupported_format')
        for suffix in ('.fasta', '.a3m.gz', '.A3M', '.a2m', '.hhm', '.sto'):
            with self.subTest(suffix=suffix):
                self.args = deepcopy(original)
                path = self.root/('other'+suffix)
                path.write_bytes(RAW)
                self.args['artifact']['path'] = str(path)
                self.error('unsupported_format')

    def test_unknown_fields_or_non_json_types_rejected_before_hooks(self):
        class Hostile(dict):
            def __deepcopy__(self, memo):
                raise AssertionError('User hook must not run')
        for bad in (Hostile(self.args['config']), {'unexpected': object()},
                    {'unexpected': float('nan')}, {'unexpected': float('inf')}):
            with self.subTest(kind=type(bad)):
                self.args['config'] = bad
                self.error('invalid_contract')
        cyclic = {}; cyclic['cycle'] = cyclic
        self.args['config'] = cyclic
        self.error('invalid_contract')

    def test_provenance_remains_unknown_and_declarations_are_inert(self):
        self.args['artifact']['provenance'] = dict(details={'path': '/must/not/be/opened'}, missing_reason=None)
        d = self.data()
        self.assertIsNone(d['provenance_snapshot']['producer']['version'])
        self.assertIsNone(d['provenance_snapshot']['producer']['database'])
        self.assertEqual(d['provenance_snapshot']['source_kind_status'], 'caller_supplied_not_verified')
        self.assertTrue(any(x['code'] == 'incomplete_provenance' for x in d['diagnostics']))

    def test_missing_provenance_reasons_fail_closed(self):
        self.args['artifact']['producer']['missing_reasons'].pop('name')
        self.error('invalid_contract')

    def test_result_is_json_detached_and_deterministic(self):
        before = deepcopy(self.args)
        result = self.result()
        original = result.to_dict()
        self.assertEqual(original, self.data())
        self.assertEqual(json.loads(json.dumps(original, allow_nan=False)), original)
        changed = result.to_dict(); changed['records'][0]['tokens'][0]['raw_token'] = 'z'
        self.args['config']['unknown_tokens'].append('B')
        self.assertEqual(original, result.to_dict())
        self.assertEqual(before['artifact'], self.args['artifact'])

    def test_hashes_cover_exact_bytes_and_contract_snapshots(self):
        d = self.data()
        self.assertEqual(d['contract_hashes']['artifact'], json_hash(self.args['artifact']))
        self.assertEqual(d['contract_hashes']['config'], json_hash(self.args['config']))
        self.assertIsNone(d['contract_hashes']['binding'])
        self.assertEqual(d['artifact']['raw_sha256'], sha(RAW))
        self.assertEqual(Path(self.args['artifact']['path']).read_bytes(), RAW)
        self.args['config']['expected_artifact_sha256'] = '0'*64
        self.error('artifact_hash_mismatch')
        self.args['artifact']['sha256'] = '0'*64
        self.error('artifact_hash_mismatch')

    def test_change_during_parse_is_fatal_before_result_return(self):
        original = ColabFoldA3MResult.to_dict
        def mutate(result):
            Path(self.args['artifact']['path']).write_bytes(b'>changed\nACG\n')
            return original(result)
        with patch.object(ColabFoldA3MResult, 'to_dict', mutate):
            self.error('artifact_hash_mismatch')

    def test_paths_are_exact_regular_local_files_under_roots(self):
        original = deepcopy(self.args)
        link = self.root/'link.a3m'; link.symlink_to(self.root/'toy.a3m')
        folder = self.root/'dir.a3m'; folder.mkdir()
        for path in ('toy.a3m', str(self.root/'missing.a3m'), str(link), str(folder),
                     str(self.root)+'/../'+self.root.name+'/toy.a3m', str(self.root/'*.a3m')):
            with self.subTest(path=path):
                self.args = deepcopy(original); self.args['artifact']['path'] = path
                self.error()
        self.args = deepcopy(original)
        self.args['config']['allowed_input_roots'] = [str(folder)]
        self.error('unsafe_artifact_path')

    def test_gates_default_disabled_without_statistical_execution(self):
        with patch('structure_audit.colabfold_a3m_lossless._Reader.counts', side_effect=AssertionError('No metrics')):
            d = self.data()
        self.assertIsNone(d['metrics'])
        self.assertEqual(d['metrics_status'], 'disabled')
        self.assertIsNone(d['binding'])
        self.assertEqual(d['binding_status'], 'disabled')
        self.assertIsNone(d['metric_policy_snapshot'])
        self.assertEqual(d['effective_execution_gates'], dict(metrics_enabled=False, binding_enabled=False))

    def assert_no_derived_maps_or_structure_fields(self, data):
        forbidden = {'observed_column_map', 'observed_column_map_sha256', 'column_map',
            'column_map_sha256', 'sequence_map', 'sequence_map_sha256', 'residue_map',
            'residue_map_sha256', 'query_column', 'sequence_position', 'residue_index',
            'model_id', 'chain_id', 'segment', 'residue_id', 'insertion_code', 'residue_name',
            'label_chain_id', 'label_seq_id', 'map_source', 'mapped_positions', 'binding_id',
            'target_id', 'role', 'verified', 'structural_source_bytes_verified'}
        def check(value):
            if isinstance(value, dict):
                self.assertFalse(forbidden.intersection(value), forbidden.intersection(value))
                if 'query_sequence_position' in value:
                    self.assertIsNone(value['query_sequence_position'])
                for child in value.values():
                    check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)
        check(data)

    def test_reader_only_has_no_derived_maps_structure_fields_or_metrics(self):
        # Both the returned object and the serialized JSON must obey the boundary.
        for explicit_disabled in (False, True):
            for raw_query in ('ACG', '-A--CG-'):
                with self.subTest(explicit_disabled=explicit_disabled, raw_query=raw_query):
                    raw = ('#opaque\r\n>same row\r\nx'+raw_query+'x\r\n>same query\n'+raw_query).encode()
                    self.file(raw, {'record_occurrence_id': 'record:1@header_line:4'})
                    if explicit_disabled:
                        self.args['config'].update(metrics_enabled=False, binding_enabled=False)
                    with patch('structure_audit.colabfold_a3m_lossless._Reader.bind',
                               side_effect=AssertionError('Reader must not enter binding')), \
                         patch('structure_audit.colabfold_a3m_lossless._Reader.metrics',
                               side_effect=AssertionError('Reader must not enter metrics')):
                        result = self.result()
                    self.assertIsInstance(result, ColabFoldA3MReaderResult)
                    self.assert_no_derived_maps_or_structure_fields(result.data)
                    d = json.loads(json.dumps(result.to_dict(), allow_nan=False))
                    self.assert_no_derived_maps_or_structure_fields(d)
                    self.assertIsNone(d['binding'])
                    self.assertIsNone(d['contract_hashes']['binding'])
                    self.assertIsNone(d['metrics'])
                    self.assertIsNone(d['metric_policy_snapshot'])
                    self.assertEqual(d['inventory']['alignment_width'], len(raw_query))
                    self.assertEqual(d['query']['canonical_sequence'], 'ACG')
                    self.assertEqual(d['query']['canonical_sequence_sha256'], sha(b'ACG'))
                    self.assertEqual([t['parsed_column'] for t in d['records'][1]['tokens']],
                                     list(range(len(raw_query))))
                    self.assertTrue(any(diag['code'] == 'match_projection_only' for diag in d['diagnostics']))
                    self.assertEqual(result.reconstruct_bytes(), raw)
                    self.assertEqual(d['reconstructed_sha256'], sha(raw))

    def test_reader_schema_rejects_query_or_token_binding_enrichment(self):
        for field in ('observed_column_map', 'column_map', 'sequence_map', 'residue_map'):
            with self.subTest(field=field):
                result = self.result()
                result.data['query'][field] = []
                with self.assertRaises(ValueError):
                    result.to_dict()
        result = self.result()
        result.data['records'][1]['tokens'][0]['query_sequence_position'] = 1
        with self.assertRaises(ValueError):
            result.to_dict()

    def test_metrics_without_binding_emit_projection_indices_but_no_maps(self):
        self.enable_metrics()
        with patch('structure_audit.colabfold_a3m_lossless._Reader.bind',
                   side_effect=AssertionError('Metrics must not enter binding')):
            d = self.data()
        self.assert_no_derived_maps_or_structure_fields(d)
        self.assertIsNone(d['binding'])
        self.assertEqual([c['parsed_column'] for c in d['metrics']['columns']], [0, 1, 2, 3])
        self.assertTrue(all(set(c) == {'parsed_column', 'metrics'} for c in d['metrics']['columns']))

    def test_inconsistent_execution_gates_fail_closed(self):
        original = deepcopy(self.args)
        for changes in [dict(metrics_enabled=1), dict(binding_enabled='true'), dict(metrics_enabled=True),
                        dict(metric_policy=metric_policy()), dict(binding_enabled=True)]:
            with self.subTest(changes=changes):
                self.args = deepcopy(original); self.args['config'].update(changes)
                self.error()
        self.args = deepcopy(original); self.args['binding'] = synthetic_binding(self.args)
        self.error('unsupported_config')

    def test_metric_policy_has_no_implicit_defaults(self):
        for key in metric_policy():
            with self.subTest(missing=key):
                self.enable_metrics(); del self.args['config']['metric_policy'][key]
                self.error('unsupported_config')
        for key, value in [('duplicate_policy', 'drop'), ('entropy_pseudocount', True),
                           ('entropy_log_base', True), ('include_query_in_statistics', 1),
                           ('coverage_token_policy', 'non_gap')]:
            with self.subTest(key=key):
                self.enable_metrics(**{key: value})
                self.error('unsupported_config')

    def test_hand_calculated_metrics_and_no_lowercase_x_contribution(self):
        self.enable_metrics()
        m = self.data()['metrics']
        s = m['summary']
        self.assertEqual((s['input_depth'], s['statistics_occurrence_count'], s['observation_count']), (4, 4, 16))
        self.assertEqual((s['valid_amino_acid_count'], s['gap_count'], s['unknown_count']), (10, 5, 1))
        self.assertEqual(s['gap_fraction']['value'], 5/16)
        self.assertEqual(s['unknown_fraction']['value'], 1/16)
        self.assertEqual(s['query_coverage']['value'], 1)
        col0 = m['columns'][0]['metrics']
        self.assertEqual(col0['amino_acid_frequencies']['value']['A'], .75)
        self.assertEqual(col0['amino_acid_frequencies']['value']['C'], .25)
        self.assertAlmostEqual(col0['shannon_entropy']['value'], -.75*math.log2(.75)-.25*math.log2(.25))
        col2 = m['columns'][2]['metrics']
        self.assertEqual(col2['amino_acid_frequencies']['denominator'], 3)
        self.assertEqual(col2['shannon_entropy']['value'], 0)
        self.assertEqual(m['row_coverage'][-1]['query_coverage']['value'], 1/3)

    def test_insertion_ledger_changes_leave_match_metrics_unchanged(self):
        self.enable_metrics()
        first = self.data()['metrics']
        self.args = contract(self.root, RAW.replace(b'xA.-cCggGx', b'xxxxA...-cccCggggGxxx'))
        self.enable_metrics()
        self.assertEqual(first, self.data()['metrics'])

    def test_duplicate_policy_uses_first_eligible_occurrence_without_deletion(self):
        for include, key, expected in [(True, 'parsed_match_tokens', 2), (False, 'parsed_match_tokens', 2),
                                       (True, 'raw_sequence_tokens', 3), (False, 'raw_sequence_tokens', 3)]:
            with self.subTest(include=include, key=key):
                self.enable_metrics(include_query_in_statistics=include, sequence_duplicate_key=key, duplicate_policy='count_once')
                d = self.data()
                self.assertEqual(len(d['records']), 4)
                self.assertEqual(d['metrics']['summary']['statistics_occurrence_count'], expected)
        self.file(b'>q\nACG\n>same\nACG\n>third\nACG\n')
        self.enable_metrics(include_query_in_statistics=False, duplicate_policy='count_once')
        contributions = self.data()['metrics']['statistical_contributions']
        self.assertEqual(contributions[1]['representative_occurrence_id'], 'record:1@header_line:3')
        self.assertEqual(contributions[2]['representative_occurrence_id'], 'record:1@header_line:3')

    def test_duplicate_error_includes_excluded_query(self):
        self.file(b'>q\nACG\n>other\nACG\n')
        self.enable_metrics(include_query_in_statistics=False, duplicate_policy='error')
        self.error('sequence_duplicate_policy_violation')

    def test_null_metrics_for_all_gap_all_unknown_and_empty_population(self):
        for seq, reason in [('---', 'all_gap'), ('XXX', 'no_valid_amino_acids')]:
            with self.subTest(seq=seq):
                self.file(('>q\nACG\n>other\n'+seq+'\n').encode())
                self.enable_metrics(include_query_in_statistics=False)
                m = self.data()['metrics']
                for col in m['columns']:
                    self.assertEqual(col['metrics']['shannon_entropy']['reason'], reason)
                    self.assertIsNone(col['metrics']['shannon_entropy']['value'])
                    self.assertIsNone(col['metrics']['gap_fraction']['value'])
                self.assertEqual(m['summary']['query_coverage']['value'], 0)
        self.file(b'>q\nACG\n')
        self.enable_metrics(include_query_in_statistics=False)
        m = self.data()['metrics']
        self.assertIsNone(m['summary']['query_coverage']['value'])
        self.assertEqual(m['summary']['query_coverage']['reason'], 'no_contributing_rows')
        self.assertIsNone(m['summary']['gap_fraction']['value'])

    def test_explicit_denominators_and_entropy_base(self):
        self.enable_metrics(gap_denominator='non_unknown', unknown_denominator='non_gap', entropy_log_base='e')
        m = self.data()['metrics']
        self.assertEqual(m['summary']['gap_fraction']['value'], 5/15)
        self.assertEqual(m['summary']['unknown_fraction']['value'], 1/11)
        self.assertAlmostEqual(m['columns'][0]['metrics']['shannon_entropy']['value'],
                               -.75*math.log(.75)-.25*math.log(.25))

    def test_complete_explicit_binding_verifies_supplied_map_only(self):
        self.enable_binding()
        before = deepcopy(self.args)
        d = self.data()
        self.assertTrue(d['binding']['verified'])
        self.assertEqual(d['binding']['mapped_positions'], 3)
        self.assertFalse(d['binding']['structural_source_bytes_verified'])
        self.assertEqual(d['binding']['status'], 'supplied_map_consistency_verified')
        self.assertEqual(d['binding']['snapshot'], self.args['binding'])
        self.assert_no_derived_maps_or_structure_fields(d['query'])
        self.assert_no_derived_maps_or_structure_fields(d['records'])
        self.assertEqual(before, self.args)
        self.assertIsNone(d['metrics'])
        self.assertEqual(d['contract_hashes']['binding'], json_hash(self.args['binding']))

    def test_binding_attestations_all_required(self):
        self.enable_binding(); original = deepcopy(self.args)
        for key in self.args['binding']:
            with self.subTest(missing=key):
                self.args = deepcopy(original); del self.args['binding'][key]
                self.error('query_binding_unresolved')
        for key, value in [('artifact_sha256', '0'*64), ('record_occurrence_id', 'record:2@header_line:7'),
                           ('canonical_query_sequence_sha256', '0'*64), ('chain_id', 'A'),
                           ('segment', 0), ('model_id', '1'), ('artifact_id', 'wrong'), ('role', 'ligand')]:
            with self.subTest(key=key):
                self.args = deepcopy(original); self.args['binding'][key] = value
                self.error('query_binding_unresolved')

    def test_binding_hash_tampering_detected(self):
        self.enable_binding(); original = deepcopy(self.args)
        for field in ('column_map', 'sequence_map', 'residue_map'):
            with self.subTest(field=field):
                self.args = deepcopy(original); self.args['binding'][field+'_sha256'] = '0'*64
                self.error('query_binding_unresolved')

    def test_rehashed_incomplete_or_incorrect_maps_still_fail(self):
        self.enable_binding(); original = deepcopy(self.args)
        for case in ('missing_column', 'reordered_column', 'gap_mapped', 'bool_column', 'bool_position', 'missing_position',
                     'unmapped_position', 'reused_residue', 'wrong_residue', 'wrong_chain', 'wrong_index',
                     'wrong_altloc', 'duplicate_identity', 'wrong_group', 'bad_source_line'):
            with self.subTest(case=case):
                self.args = deepcopy(original); b = self.args['binding']
                if case == 'missing_column': b['column_map'].pop()
                elif case == 'reordered_column': b['column_map'].reverse()
                elif case == 'gap_mapped': b['column_map'][1]['sequence_position'] = 1
                elif case == 'bool_column': b['column_map'][0]['query_column'] = False
                elif case == 'bool_position': b['column_map'][0]['sequence_position'] = True
                elif case == 'missing_position': b['sequence_map'].pop()
                elif case == 'unmapped_position': b['sequence_map'][1]['residue_index'] = None
                elif case == 'reused_residue': b['sequence_map'][1]['residue_index'] = 0
                elif case == 'wrong_residue': b['residue_map'][1]['residue_name'] = 'ALA'
                elif case == 'wrong_chain': b['residue_map'][1]['chain_id'] = 'B'
                elif case == 'wrong_index': b['residue_map'][1]['residue_index'] = True
                elif case == 'wrong_altloc': b['residue_map'][1]['selected_altloc'] = 'B'
                elif case == 'duplicate_identity':
                    b['residue_map'][1].update(residue_id=-3, insertion_code='')
                elif case == 'wrong_group': b['residue_map'][1]['record_group'] = 'HETATM'
                elif case == 'bad_source_line': b['residue_map'][1]['source_lines'] = [0]
                reseal_binding(b)
                self.error('query_binding_unresolved')

    def test_reader_only_io_no_network_subprocess_environment_or_writer(self):
        self.enable_binding(); self.enable_metrics()
        real_open, real_io_open = builtins.open, io.open
        allowed = str(self.root/'toy.a3m')
        opened = []
        def guard(real):
            def checked(path, mode='r', *args, **kwargs):
                self.assertEqual(str(path), allowed)
                self.assertEqual(mode, 'rb')
                opened.append(str(path))
                return real(path, mode, *args, **kwargs)
            return checked
        before_environment = dict(os.environ)
        with ExitStack() as stack:
            stack.enter_context(patch('builtins.open', guard(real_open)))
            stack.enter_context(patch('io.open', guard(real_io_open)))
            for owner, names in [(socket, ('socket', 'create_connection')),
                                 (subprocess, ('Popen', 'run')),
                                 (os, ('system', 'popen', 'putenv', 'unsetenv', 'listdir', 'scandir', 'walk')),
                                 (Path, ('write_bytes', 'write_text', 'mkdir', 'unlink', 'rename', 'replace', 'touch', 'glob', 'rglob'))]:
                for name in names:
                    stack.enter_context(patch.object(owner, name, side_effect=AssertionError('Forbidden IO: '+name)))
            d = self.data()
        self.assertEqual(len(opened), 2)
        self.assertEqual(dict(os.environ), before_environment)
        self.assertTrue(d['binding']['verified'])
        self.assertEqual(Path(allowed).read_bytes(), RAW)


class LegacyIsolationTest(unittest.TestCase):
    def test_old_profile_still_rejects_new_semantics_and_new_name(self):
        from test_receptor_msa_audit_adapter import synthetic_msa_contract, seal_contract
        from structure_audit.receptor_msa_audit_adapter import audit_receptor_msa, ReceptorMSAAuditError
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            for raw, name in [(b'#opaque\n>query\nA-CG\n', 'a3m_match_columns_v1'),
                              (b'>query\nA-CG\n>other\nAx-CG\n', 'a3m_match_columns_v1'),
                              (b'>query\nA-CG\n>query\nA-CG\n', 'a3m_match_columns_v1'),
                              (b'>query\nA-CG\n', 'colabfold_a3m_lossless_v1')]:
                with self.subTest(raw=raw, name=name):
                    args = synthetic_msa_contract(root)
                    path = root/'legacy.a3m'; path.write_bytes(raw)
                    args['artifact'].update(path=str(path), sha256=sha(raw), format='a3m')
                    profile = args['config']['parsing_profile']
                    profile.update(name=name, format='a3m', lowercase='remove_insertion', dot='remove_insertion_padding')
                    args['config']['parsing_profile_sha256'] = json_hash(profile)
                    args['manifest']['input_files'] = [dict(path=str(path), sha256=sha(raw))]
                    seal_contract(args)
                    with self.assertRaises(ReceptorMSAAuditError):
                        audit_receptor_msa(**args)

    def test_new_reader_never_calls_legacy_adapter(self):
        with tempfile.TemporaryDirectory() as temp:
            args = contract(Path(temp).resolve())
            with patch('structure_audit.receptor_msa_audit_adapter.audit_receptor_msa',
                       side_effect=AssertionError('No legacy delegation')):
                self.assertEqual(parse_colabfold_a3m(**args).reconstruct_bytes(), RAW)


if __name__ == '__main__':
    unittest.main()
