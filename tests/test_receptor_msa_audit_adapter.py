"""Synthetic/local contract tests; only fixture setup writes temporary files."""
import builtins
from contextlib import ExitStack
from copy import deepcopy
import glob
import io
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from structure_audit.evidence import sequence_hash
from structure_audit.provenance import hash_config, hash_file
from structure_audit.receptor_msa_audit_adapter import (
    audit_receptor_msa, ReceptorMSAAuditError, ReceptorMSAAuditResult,
)

NAME = 'receptor_msa_audit_adapter'
AA20 = 'ACDEFGHIKLMNPQRSTVWY'


def seal_contract(args):
    args['manifest']['config'][NAME] = dict(config=deepcopy(args['config']),
        artifact_sha256=hash_config(args['artifact']), binding_sha256=hash_config(args['binding']))
    args['manifest']['config_hash'] = hash_config(args['manifest']['config'])


def synthetic_msa_contract(root):
    """Write one named toy alignment and supply a map snapshot, never a structure."""
    root = Path(root).resolve()
    path = root / 'receptor.fasta'
    path.write_bytes(b'>same first row\nA-CG\n>query explicit second record\nA-CG\n>other\nC-X-\n>gapped\n--X-\n>unknown\nX---\n')
    profile = dict(name='aligned_fasta_v1', format='fasta', encoding='utf-8',
        record_id_rule='first_ascii_whitespace_token', multiline=True,
        sequence_whitespace='reject', blank_lines='reject', newline_policy='lf_or_crlf',
        lowercase='reject', dot='reject', star='reject', gap='preserve', query_insertions='reject',
        insertion_alphabet=AA20, unknown_tokens=list('XBZJUO'), unknown_policy='retain_as_unknown')
    config = dict(version='1.0', allowed_input_roots=[str(root)], parsing_profile=profile,
        parsing_profile_sha256=hash_config(profile),
        position_bases=dict(row_index=0, raw_token_index=0, query_column=0, residue_index=0,
                            sequence_position=1, source_line=1, source_character=1),
        include_query_in_statistics=True, duplicate_key='exact_parsed_alignment_tokens',
        duplicate_policy='keep', gap_denominator='all_observations', unknown_denominator='all_observations',
        frequency_denominator='valid_amino_acids', entropy_alphabet=AA20, entropy_log_base=2,
        entropy_gap_policy='exclude', entropy_unknown_policy='exclude', entropy_pseudocount=0,
        coverage_token_policy='valid_amino_acids', coverage_denominator='query_sequence_length',
        coverage_aggregation='any_contributing_row')
    declaration = dict(details=None, missing_reason='Synthetic source; generation history not supplied')
    artifact = dict(artifact_id='msa', path=str(path), sha256=hash_file(path), format='fasta',
                    source_run_id='synthetic-source', producer=deepcopy(declaration), generation=deepcopy(declaration))
    rows = [dict(residue_index=i, model_id='7', chain_id='A', segment=0, record_group='ATOM',
                 residue_id=number, insertion_code='A' if i == 0 else '', residue_name=residue,
                 label_chain_id='X', label_seq_id=i+1, source_lines=[i+10], atom_names=['CA'],
                 selected_altloc='A', missing_backbone_atoms=['N', 'C', 'O'], warnings=[])
            for i, (number, residue) in enumerate(((10, 'ALA'), (14, 'CYS'), (21, 'GLY')))]
    smap = [dict(sequence_position=i+1, residue_index=i, reason=None) for i in range(3)]
    cmap = [dict(query_column=i, sequence_position=pos, reason='query_gap' if pos is None else None)
            for i, pos in enumerate((1, None, 2, 3))]
    binding = dict(binding_id='receptor-binding', artifact_id='msa', target_id='synthetic-receptor', role='receptor',
                   chain_id='A', segment=0, model_id='7', query_record_id='query', query_sequence='ACG',
                   query_sequence_sha256=sequence_hash('ACG'), column_map=cmap, column_map_sha256=hash_config(cmap),
                   sequence_map=smap, sequence_map_sha256=hash_config(smap), residue_map=rows,
                   residue_map_sha256=hash_config(rows),
                   map_source=dict(artifact_id='supplied-map-source', sha256='a'*64,
                                   source_run_id='synthetic-map-run', model_id='7'))
    manifest = dict(schema_version='1.0', run_id='msa-audit', run_directory=str(root/'msa-audit/v0001'),
                    timestamp='2026-09-16T00:00:00+00:00', git_commit=None, git_dirty=None,
                    config={}, config_hash='0'*64, input_files=[dict(path=str(path), sha256=artifact['sha256'])],
                    random_seed=None, supplied_models=[], output_paths=[], status='completed',
                    warnings=['Synthetic fixture only'], utility_version='0.1.0')
    args = dict(artifact=artifact, binding=binding, manifest=manifest, config=config)
    seal_contract(args)
    return args


class ReceptorMSAAuditTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.args = synthetic_msa_contract(self.root)

    def result(self):
        return audit_receptor_msa(**self.args)

    def seal(self):
        seal_contract(self.args)

    def rehash_binding(self):
        b = self.args['binding']
        for key in ('column_map', 'sequence_map', 'residue_map'):
            b[key+'_sha256'] = hash_config(b[key])
        b['query_sequence_sha256'] = sequence_hash(b['query_sequence'])
        self.seal()

    def profile(self, **changes):
        p = self.args['config']['parsing_profile']
        p.update(changes)
        self.args['config']['parsing_profile_sha256'] = hash_config(p)
        self.seal()

    def file(self, content):
        a = self.args['artifact']
        Path(a['path']).write_bytes(content.encode('utf-8') if isinstance(content, str) else content)
        a['sha256'] = hash_file(a['path'])
        self.args['manifest']['input_files'] = [dict(path=a['path'], sha256=a['sha256'])]
        self.seal()

    def a3m(self, content):
        self.args['artifact'].update(format='a3m', path=str(self.root/'receptor.a3m'))
        self.profile(name='a3m_match_columns_v1', format='a3m', lowercase='remove_insertion', dot='remove_insertion_padding')
        self.file(content)

    def error(self, code=None):
        with self.assertRaises(ReceptorMSAAuditError) as caught:
            self.result()
        e = caught.exception
        self.assertFalse(any(hasattr(e, k) for k in ('result', 'rows', 'columns', 'summary')))
        d = e.diagnostics[0]
        self.assertEqual(d['severity'], 'error')
        if code:
            self.assertEqual(d['code'], code)
        return d

    def test_explicit_nonfirst_query_and_hand_calculated_statistics(self):
        r = self.result()
        self.assertIsInstance(r, ReceptorMSAAuditResult)
        s = r.summary
        self.assertEqual((s['alignment_depth'], s['unique_row_count'], s['duplicate_count']), (5, 4, 1))
        self.assertEqual((s['query_row_index'], s['alignment_width'], s['statistics_row_count']), (1, 4, 5))
        m = r.columns[0]['metrics']
        self.assertEqual((m['valid_amino_acid_count'], m['gap_count'], m['unknown_count']), (3, 1, 1))
        self.assertEqual(m['gap_fraction']['value'], .2)
        self.assertEqual(m['unknown_fraction']['value'], .2)
        f = m['amino_acid_frequencies']['value']
        self.assertEqual((f['A'], f['C']), (2/3, 1/3))
        self.assertAlmostEqual(sum(f.values()), 1)
        self.assertAlmostEqual(m['shannon_entropy']['value'], .9182958340544896)
        self.assertEqual(s['query_coverage']['value'], 1)
        self.assertEqual(r.rows[2]['query_coverage']['value'], 1/3)
        self.assertEqual(r.rows[3]['query_coverage']['value'], 0)
        self.assertEqual(s['observation_count'], 20)
        self.assertEqual(s['gap_fraction']['value'], 10/20)

    def test_a3m_insertions_padding_and_raw_position_effect(self):
        self.a3m('>other\naaA.-cCggGtt\n>query\nA-CG\n')
        r = self.result()
        row = r.rows[0]
        self.assertEqual(row['parsed_sequence'], 'A-CG')
        self.assertEqual(row['raw_sequence'], 'aaA.-cCggGtt')
        self.assertEqual(r.summary['duplicate_count'], 1)
        self.assertEqual([t['query_column'] for t in row['tokens']], [None, None, 0, None, 1, None, 2, None, None, 3, None, None])
        self.assertEqual([t['insertion_anchor'] for t in row['tokens']], [0, 0, None, 1, None, 2, None, 3, 3, None, 4, 4])
        self.assertEqual(row['tokens'][5]['source_character'], 6)
        self.assertEqual(row['tokens'][3]['action'], 'remove_insertion_padding')
        self.assertEqual(row['tokens'][5]['position_effect'], 'no_alignment_column')
        self.assertEqual(row['tokens'][4]['token_class'], 'gap')
        self.assertEqual([t['query_sequence_position'] for t in row['tokens']],
                         [None, None, 1, None, None, None, 2, None, None, 3, None, None])

    def test_multiline_crlf_missing_final_newline_and_exact_fragments(self):
        content = b'>query\tdescription\r\nA-\r\nCG\r\n>other\r\nC-X-'
        self.file(content)
        r = self.result()
        row = r.rows[0]
        self.assertEqual(row['raw_header_fragment'], '>query\tdescription\r\n')
        self.assertEqual(row['raw_fragments'], [dict(source_line=2, text='A-\r\n'), dict(source_line=3, text='CG\r\n')])
        self.assertEqual(row['tokens'][2]['source_line'], 3)
        self.assertEqual(row['tokens'][2]['source_character'], 1)
        self.assertEqual(Path(self.args['artifact']['path']).read_bytes(), content)

    def test_duplicate_policy_and_query_inclusion_matrix(self):
        for include, policy, count in ((True, 'keep', 5), (False, 'keep', 4),
                                       (True, 'count_once', 4), (False, 'count_once', 4)):
            with self.subTest(include=include, policy=policy):
                self.args['config'].update(include_query_in_statistics=include, duplicate_policy=policy)
                self.seal()
                r = self.result()
                self.assertEqual(r.summary['statistics_row_count'], count)
                self.assertEqual(r.summary['alignment_depth'], 5)
                self.assertEqual(r.summary['duplicate_count'], 1)
                self.assertTrue(r.rows[0]['contributes_to_statistics'])
                self.assertEqual(r.rows[1]['contributes_to_statistics'], include and policy == 'keep')

    def test_count_once_after_query_exclusion_keeps_equal_nonquery(self):
        self.file('>query\nA-CG\n>copy\nA-CG\n')
        self.args['config'].update(include_query_in_statistics=False, duplicate_policy='count_once')
        self.seal()
        r = self.result()
        self.assertEqual(r.summary['duplicate_groups'][0]['contributing_row_indices'], [1])
        self.assertEqual(r.rows[0]['statistics_exclusion_reason'], 'query_excluded')
        self.assertTrue(r.rows[1]['contributes_to_statistics'])

    def test_distinct_unknown_tokens_are_not_silently_merged(self):
        self.file('>query\nA-CG\n>x\nX-CG\n>b\nB-CG\n')
        self.args['config']['duplicate_policy'] = 'count_once'; self.seal()
        r = self.result()
        self.assertEqual(r.summary['unique_row_count'], 3)
        self.assertEqual(r.columns[0]['metrics']['unknown_token_counts']['B'], 1)
        self.assertEqual(r.columns[0]['metrics']['unknown_token_counts']['X'], 1)

    def test_alternative_denominators_and_natural_log(self):
        self.args['config'].update(gap_denominator='non_unknown', unknown_denominator='non_gap', entropy_log_base='e')
        self.seal()
        m = self.result().columns[0]['metrics']
        self.assertEqual(m['gap_fraction']['value'], 1/4)
        self.assertEqual(m['unknown_fraction']['value'], 1/4)
        self.assertAlmostEqual(m['shannon_entropy']['value'], -(2/3*math.log(2/3)+1/3*math.log(1/3)))

    def test_all_gap_all_unknown_and_mixed_invalid_columns_are_null(self):
        self.file('>query\nA-CG\n>x\nX-XX\n>y\nX--X\n')
        self.args['config']['include_query_in_statistics'] = False; self.seal()
        r = self.result()
        self.assertEqual([c['metrics']['shannon_entropy']['reason'] for c in r.columns],
                         ['no_valid_amino_acids', 'all_gap', 'no_valid_amino_acids', 'no_valid_amino_acids'])
        for col in r.columns:
            for field in ('gap_fraction', 'unknown_fraction', 'amino_acid_frequencies', 'shannon_entropy'):
                self.assertIsNone(col['metrics'][field]['value'])
        self.assertEqual(r.columns[1]['metrics']['gap_count'], 2)
        self.assertEqual(r.summary['query_coverage']['value'], 0)
        self.assertEqual(r.summary['unknown_fraction']['value'], 5/8)

    def test_homogeneous_valid_column_entropy_is_zero(self):
        self.file('>query\nA-CG\n')
        r = self.result()
        self.assertEqual(r.columns[0]['metrics']['shannon_entropy']['value'], 0.0)
        self.assertEqual(r.columns[0]['metrics']['amino_acid_frequencies']['value']['A'], 1)

    def test_empty_statistics_population_is_null_not_zero(self):
        self.file('>query\nA-CG\n')
        self.args['config']['include_query_in_statistics'] = False; self.seal()
        r = self.result()
        self.assertEqual(r.summary['statistics_row_count'], 0)
        self.assertIsNone(r.summary['query_coverage']['value'])
        self.assertEqual(r.summary['query_coverage']['reason'], 'no_contributing_rows')
        self.assertTrue(all(c['metrics']['shannon_entropy']['reason'] == 'no_contributing_rows' for c in r.columns))

    def test_pooled_zero_denominator_has_reason(self):
        self.file('>query\nA-CG\n>x\nXXXX\n')
        self.args['config'].update(include_query_in_statistics=False, gap_denominator='non_unknown'); self.seal()
        self.assertEqual(self.result().summary['gap_fraction'], dict(value=None, numerator=0, denominator=0, reason='zero_denominator'))

    def test_query_gap_map_and_author_label_bases_are_preserved(self):
        r = self.result()
        self.assertEqual([c['sequence_position'] for c in r.columns], [1, None, 2, 3])
        self.assertEqual([c['residue_index'] for c in r.columns], [0, None, 1, 2])
        row = r.audit['binding']['residue_map'][0]
        self.assertEqual((row['residue_id'], row['insertion_code'], row['label_seq_id'], row['label_chain_id']), (10, 'A', 1, 'X'))
        self.assertEqual(r.audit['position_bases'], self.args['config']['position_bases'])
        self.assertEqual(r.audit['map_verification'], 'supplied_map_consistency_verified')

    def test_missing_structural_residue_is_explicit_not_msa_coverage_loss(self):
        b = self.args['binding']
        b['sequence_map'][1].update(residue_index=None, reason='Unobserved supplied structural residue')
        self.rehash_binding()
        r = self.result()
        self.assertIsNone(r.columns[2]['residue_index'])
        self.assertEqual(r.summary['query_coverage']['value'], 1)
        self.assertIn('missing_residue_mapping', [d['code'] for d in r.diagnostics])

    def test_blank_chain_segment_signed_author_numbers_and_unordered_sequence_map(self):
        b = self.args['binding']; b.update(chain_id='', segment=2)
        for r in b['residue_map']:
            r.update(chain_id='', segment=2, residue_id=-r['residue_id'])
        b['sequence_map'].reverse(); self.rehash_binding()
        r = self.result()
        self.assertEqual(r.columns[0]['residue_index'], 0)
        self.assertEqual(r.audit['binding']['residue_map'][0]['residue_id'], -10)

    def test_snapshots_hashes_determinism_detached_result_and_no_mutation(self):
        before = deepcopy(self.args)
        raw_before = Path(self.args['artifact']['path']).read_bytes()
        r = self.result(); payload = r.to_dict()
        self.assertEqual(payload, self.result().to_dict())
        self.assertEqual(json.loads(json.dumps(payload, allow_nan=False)), payload)
        self.assertEqual(r.audit['manifest_sha256'], hash_config(before['manifest']))
        self.assertEqual(r.audit['binding_sha256'], hash_config(before['binding']))
        self.assertEqual(r.audit['file_sha256'], before['artifact']['sha256'])
        self.assertEqual(r.audit['parsing_profile_sha256'], hash_config(before['config']['parsing_profile']))
        self.assertEqual(self.args, before)
        payload['rows'].clear(); self.assertEqual(len(r.rows), 5)
        self.args['binding']['target_id'] = 'changed'
        self.assertEqual(r.audit['binding']['target_id'], 'synthetic-receptor')
        self.assertEqual(raw_before, Path(self.args['artifact']['path']).read_bytes())
        self.assertFalse((self.root/'msa-audit').exists())
        with self.assertRaises(TypeError):
            iter(r)

    def test_no_evidence_report_ranking_or_effective_sequence_fields(self):
        data = self.result().to_dict()
        forbidden = {'candidate_id', 'candidates', 'candidate_reports', 'checks', 'score', 'ranking', 'affinity', 'neff', 'effective_sequence_number'}
        def visit(obj):
            if isinstance(obj, dict):
                self.assertFalse(set(obj) & forbidden)
                for v in obj.values(): visit(v)
            elif isinstance(obj, list):
                for v in obj: visit(v)
        visit(data)
        self.assertIn('not N_eff', data['audit']['limitations'][1])

    def test_extra_manifest_inputs_and_declaration_paths_are_never_opened(self):
        self.args['manifest']['input_files'].append(dict(path='/missing/extra', sha256='0'*64))
        self.args['artifact']['generation'] = dict(details={'path': '/missing/history', 'command': 'inert text only'}, missing_reason=None)
        self.seal()
        self.assertEqual(self.result().summary['alignment_depth'], 5)

    def test_missing_query_and_wrong_query_sequence(self):
        self.args['binding']['query_record_id'] = 'absent'; self.seal()
        self.error('query_mismatch')
        self.args['binding'].update(query_record_id='query', query_sequence='AAA'); self.rehash_binding()
        self.error('sequence_mapping_mismatch')
        self.args['binding']['residue_map'][1]['residue_name'] = 'ALA'
        self.args['binding']['residue_map'][2]['residue_name'] = 'ALA'; self.rehash_binding()
        self.error('query_mismatch')

    def test_query_hash_mismatch(self):
        self.args['binding']['query_sequence_sha256'] = '0'*64; self.seal()
        self.error('query_mismatch')

    def test_duplicate_record_ids_even_if_sequences_differ(self):
        self.file('>query\nA-CG\n>query other description\nC-X-\n')
        d = self.error('duplicate_identity')
        self.assertEqual(d['locator']['source_line'], 3)

    def test_duplicate_error_includes_excluded_query(self):
        self.args['config'].update(duplicate_policy='error', include_query_in_statistics=False); self.seal()
        self.error('duplicate_policy_violation')

    def test_fasta_rejects_lowercase_dot_star_and_invalid_tokens(self):
        for token in ('a', '.', '*', '?', '/', '1', 'é', ' ', '\t', 'x'):
            with self.subTest(token=token):
                self.file('>query\nA-CG\n>other\n'+token+'-CG\n')
                d = self.error('invalid_token')
                self.assertEqual(d['locator']['row_index'], 1)
                self.assertEqual(d['locator']['source_character'], 1)

    def test_a3m_never_silently_discards_unsupported_insertions_or_stars(self):
        for token in ('*', 'x', 'b', 'j', 'u', '?'):
            with self.subTest(token=token):
                self.a3m('>query\nA-CG\n>other\nA-'+token+'CG\n')
                self.error('invalid_token')

    def test_query_insertions_and_unknowns_are_fatal(self):
        for token in ('a', '.', 'X', 'B', '*'):
            with self.subTest(token=token):
                self.a3m('>query\nA-'+token+'CG\n')
                self.error('invalid_token')

    def test_unknown_policy_and_explicit_token_allowlist(self):
        self.profile(unknown_policy='reject'); self.error('invalid_token')
        self.profile(unknown_policy='retain_as_unknown', unknown_tokens=['B']); self.error('invalid_token')
        self.profile(unknown_tokens=['X']); self.assertEqual(self.result().summary['unknown_count'], 3)

    def test_ragged_rows_after_a3m_parsing(self):
        self.a3m('>query\nA-CG\n>other\nAccCG\n')
        d = self.error('ragged_alignment')
        self.assertEqual(d['locator']['record_id'], 'other')
        self.assertEqual(d['locator']['observed_width'], 3)

    def test_nonphysical_unicode_newlines_and_controls_are_rejected(self):
        for token in ('\x85', '\u2028', '\u2029', '\x7f', '\v', '\f'):
            with self.subTest(token=token):
                self.file('>query description'+token+'suffix\nA-CG\n')
                self.error('alignment_parse_error')

    def test_unknown_token_retain_policy_preserves_all_declared_symbols(self):
        self.file('>query\nA-CG\n'+''.join('>'+x+'\n'+x+'-CG\n' for x in 'XBZJUO'))
        r = self.result()
        self.assertEqual(r.columns[0]['metrics']['unknown_count'], 6)
        self.assertEqual([row['tokens'][0]['original_token'] for row in r.rows[1:]], list('XBZJUO'))
        self.assertEqual(r.columns[0]['metrics']['amino_acid_frequencies']['value']['A'], 1)

    def test_duplicate_error_without_duplicates_is_valid(self):
        self.file('>query\nA-CG\n>other\nC-X-\n')
        self.args['config']['duplicate_policy'] = 'error'; self.seal()
        self.assertEqual(self.result().summary['statistics_row_count'], 2)

    def test_malformed_empty_headerless_or_zero_column_input(self):
        for content in ('', '\n', 'A-CG\n', '>query\n', '>query\nA-CG\n>empty\n',
                        '> query\nA-CG\n', '>\nA-CG\n', '>query\nA-CG\n\n',
                        '#comment\n>query\nA-CG\n', '\ufeff>query\nA-CG\n', '>query\rA-CG\r'):
            with self.subTest(content=content):
                self.file(content); self.error('alignment_parse_error')
        self.a3m('>query\nA-CG\n>other\naaaa....\n'); self.error('alignment_parse_error')

    def test_binary_invalid_utf8_is_diagnostic(self):
        self.file(b'\x80\x04pickle'); self.error('alignment_parse_error')

    def test_no_format_inference_or_non_alignment_output_import(self):
        original = deepcopy(self.args)
        for fmt in ('txt', 'pickle', 'tensor', 'embedding', 'model_output', None):
            self.args = deepcopy(original); self.args['artifact']['format'] = fmt; self.seal()
            self.error('unsupported_format')
        for suffix in ('.txt', '.pkl', '.pt', '.npy', '.fasta.gz', '.a2m'):
            self.args = deepcopy(original); self.args['artifact']['path'] = str(self.root/('artifact'+suffix)); self.seal()
            self.error('unsupported_format')

    def test_profile_config_fixed_fields_and_hash_failures(self):
        original = deepcopy(self.args)
        changes = [('duplicate_policy', 'drop'), ('gap_denominator', 'valid'), ('entropy_pseudocount', 1),
                   ('entropy_pseudocount', False), ('entropy_log_base', True), ('entropy_log_base', 2.0),
                   ('entropy_alphabet', 'AC'), ('include_query_in_statistics', 1), ('version', '2.0')]
        for k, value in changes:
            with self.subTest(key=k, value=value):
                self.args = deepcopy(original); self.args['config'][k] = value; self.seal()
                self.error('unsupported_config')
        self.args = deepcopy(original); self.args['config']['parsing_profile_sha256'] = '0'*64; self.seal()
        self.error('parsing_profile_mismatch')
        for k, value in [('star', 'remove'), ('lowercase', 'uppercase'), ('multiline', 1), ('unknown_tokens', ['X', 'X']),
                         ('unknown_tokens', ['?']), ('unknown_tokens', ['']), ('name', 'auto')]:
            self.args = deepcopy(original); self.profile(**{k: value}); self.error('parsing_profile_mismatch')

    def test_position_base_mismatch_and_boolean_index(self):
        self.args['config']['position_bases']['query_column'] = 1; self.seal(); self.error('unsupported_config')
        self.args['config']['position_bases']['query_column'] = 0
        self.args['binding']['column_map'][0]['query_column'] = False; self.rehash_binding()
        self.error('column_mapping_mismatch')

    def test_column_mapping_wrong_gap_missing_reordered_or_duplicate(self):
        original = deepcopy(self.args)
        for case in ('missing', 'duplicate', 'gap', 'residue', 'reason', 'reorder'):
            self.args = deepcopy(original); entries = self.args['binding']['column_map']
            if case == 'missing': entries.pop()
            elif case == 'duplicate': entries[1] = deepcopy(entries[0])
            elif case == 'gap': entries[1].update(sequence_position=2, reason=None)
            elif case == 'residue': entries[2]['sequence_position'] = 3
            elif case == 'reason': entries[1]['reason'] = None
            else: entries.reverse()
            self.rehash_binding(); self.error('column_mapping_mismatch')

    def test_sequence_mapping_invalid_positions_reuse_missing_reason(self):
        original = deepcopy(self.args)
        for key, value in [('sequence_position', 0), ('sequence_position', True), ('sequence_position', 4),
                           ('sequence_position', 2), ('residue_index', 1), ('residue_index', -1),
                           ('residue_index', 3), ('residue_index', True), ('residue_index', None), ('reason', 'conflict')]:
            with self.subTest(key=key, value=value):
                self.args = deepcopy(original); self.args['binding']['sequence_map'][0][key] = value
                self.rehash_binding(); self.error('sequence_mapping_mismatch')
        self.args = deepcopy(original); self.args['binding']['sequence_map'].pop(); self.rehash_binding()
        self.error('sequence_mapping_mismatch')

    def test_wrong_chain_role_model_and_residue_identity(self):
        original = deepcopy(self.args)
        for key, value in [('chain_id', 'B'), ('segment', 1), ('role', 'candidate'), ('artifact_id', 'other')]:
            self.args = deepcopy(original); self.args['binding'][key] = value; self.rehash_binding()
            self.error('chain_binding')
        self.args = deepcopy(original); self.args['binding']['model_id'] = '8'; self.rehash_binding()
        self.error('residue_map_mismatch')
        for key, value in [('residue_name', 'CYS'), ('residue_name', 'UNK'), ('record_group', 'HETATM')]:
            self.args = deepcopy(original); self.args['binding']['residue_map'][0][key] = value; self.rehash_binding()
            self.error('sequence_mapping_mismatch')

    def test_map_profile_and_binding_content_hash_mismatches(self):
        original = deepcopy(self.args)
        for key, code in [('column_map', 'column_mapping_mismatch'), ('sequence_map', 'sequence_mapping_mismatch'),
                          ('residue_map', 'residue_map_mismatch')]:
            self.args = deepcopy(original); self.args['binding'][key+'_sha256'] = '0'*64; self.seal()
            self.error(code)
        self.args = deepcopy(original); self.args['binding']['target_id'] = 'changed-without-attestation'
        self.error('manifest_contract')

    def test_rehashed_malformed_map_rows_and_duplicate_identity(self):
        original = deepcopy(self.args)
        for key, value in [('residue_index', 1), ('residue_index', False), ('model_id', '8'), ('source_lines', []),
                           ('source_lines', [0]), ('selected_altloc', 'B'), ('label_seq_id', True), ('residue_id', '10')]:
            self.args = deepcopy(original); self.args['binding']['residue_map'][0][key] = value; self.rehash_binding()
            self.error('residue_map_mismatch')
        self.args = deepcopy(original)
        r = self.args['binding']['residue_map']; r[1].update(residue_id=10, insertion_code='A'); self.rehash_binding()
        self.error('residue_map_mismatch')

    def test_manifest_inputs_config_utc_and_containment(self):
        original = deepcopy(self.args)
        for inputs in ([], original['manifest']['input_files']*2,
                       [dict(path=original['artifact']['path'], sha256='0'*64)]):
            self.args = deepcopy(original); self.args['manifest']['input_files'] = inputs
            self.error('manifest_artifact_mismatch')
        for key, value in [('timestamp', '2026-09-16T00:00:00'), ('timestamp', '2026-09-16T00:00:00+01:00'),
                           ('config_hash', '0'*64), ('output_paths', [str(self.root/'escape.json')]),
                           ('run_directory', 'relative'), ('schema_version', '2.0')]:
            self.args = deepcopy(original); self.args['manifest'][key] = value
            self.error('manifest_contract')

    def test_unsafe_paths_rejected_before_alignment_read(self):
        original = deepcopy(self.args)
        for path in ('relative.fasta', 'https://example.invalid/a.fasta', str(self.root/'*.fasta'),
                     str(self.root/'../escape.fasta'), '/outside/receptor.fasta'):
            self.args = deepcopy(original); self.args['artifact']['path'] = path; self.seal()
            with patch.object(Path, 'read_bytes', side_effect=AssertionError('Unexpected alignment read')):
                self.error('unsafe_path')

    def test_symlink_alias_and_escape_rejected(self):
        original = deepcopy(self.args)
        for name, target in [('alias.fasta', self.root/'receptor.fasta'), ('escape.fasta', Path('/missing/data.fasta'))]:
            link = self.root/name; link.symlink_to(target)
            self.args = deepcopy(original); self.args['artifact']['path'] = str(link); self.seal()
            self.error('unsafe_path')

    def test_missing_nonregular_or_stale_file(self):
        path = Path(self.args['artifact']['path'])
        path.write_bytes(path.read_bytes()+b'\n'); self.error('stale_artifact_hash')
        path.unlink(); self.error('artifact_read_error')
        path.mkdir(); self.error('artifact_read_error')

    def test_late_token_failure_has_no_partial_rows(self):
        path = Path(self.args['artifact']['path'])
        self.file(path.read_text()+'>late\nA?CG\n')
        d = self.error('invalid_token')
        self.assertEqual(d['locator']['row_index'], 5)

    def test_late_file_change_invalidates_entire_result(self):
        original = ReceptorMSAAuditResult.to_dict
        def changed(result):
            payload = original(result)
            path = Path(self.args['artifact']['path'])
            path.write_bytes(path.read_bytes()+b'\n')
            return payload
        with patch.object(ReceptorMSAAuditResult, 'to_dict', changed):
            self.error('stale_artifact_hash')

    def test_contract_strict_json_unknown_fields_and_custom_hooks(self):
        original = deepcopy(self.args)
        class Hook:
            def __deepcopy__(self, memo):
                raise AssertionError('Must not execute object hook')
        class DictHook(dict):
            def __deepcopy__(self, memo):
                raise AssertionError('Must not execute subclass hook')
        for value in (Hook(), DictHook(), float('nan'), float('inf')):
            self.args = deepcopy(original); self.args['config']['extra'] = value; self.error('invalid_contract')
        self.args = deepcopy(original); self.args['config']['cycle'] = self.args['config']; self.error('invalid_contract')
        for key in ('artifact', 'binding', 'manifest', 'config'):
            self.args = deepcopy(original); self.args[key]['extra'] = 'unsupported'; self.seal(); self.error()
            self.args = deepcopy(original); self.args[key] = []; self.error('invalid_contract')

    def test_guarded_fresh_module_and_audit_no_writes_network_process_discovery_or_third_party(self):
        module_path = Path(__file__).resolve().parents[1]/'src/structure_audit/receptor_msa_audit_adapter.py'
        allowed_reads = {Path(self.args['artifact']['path']), module_path,
                         module_path.parent/'schemas/run_manifest.schema.json'}
        before = Path(self.args['artifact']['path']).read_bytes()
        environ = dict(os.environ)
        original_open, original_io, original_import = builtins.open, io.open, builtins.__import__
        def readonly(fn):
            def guarded(file, mode='r', *args, **kwargs):
                if any(x in mode for x in 'wax+'):
                    raise AssertionError('Unexpected write')
                if Path(file) not in allowed_reads:
                    raise AssertionError('Unexpected data read: '+str(file))
                return fn(file, mode, *args, **kwargs)
            return guarded
        def imports(name, globals=None, locals=None, fromlist=(), level=0):
            if not level and name.split('.')[0] not in sys.stdlib_module_names | {'structure_audit'}:
                raise AssertionError('Third-party import: '+name)
            return original_import(name, globals, locals, fromlist, level)
        with ExitStack() as stack:
            for obj, attr in ((socket, 'socket'), (socket, 'create_connection'), (subprocess, 'Popen'),
                              (os, 'system'), (os, 'popen'), (os, 'open'), (os, 'putenv'), (os, 'unsetenv'),
                              (os, 'listdir'), (os, 'scandir'), (os, 'walk'), (glob, 'glob'), (glob, 'iglob'),
                              (Path, 'glob'), (Path, 'rglob'), (Path, 'mkdir'), (Path, 'unlink'),
                              (Path, 'rename'), (Path, 'replace'), (Path, 'touch')):
                stack.enter_context(patch.object(obj, attr, side_effect=AssertionError('Forbidden '+attr)))
            stack.enter_context(patch.object(builtins, 'open', side_effect=readonly(original_open)))
            stack.enter_context(patch.object(io, 'open', side_effect=readonly(original_io)))
            stack.enter_context(patch.object(builtins, '__import__', side_effect=imports))
            namespace = {'__name__': 'structure_audit._guarded_msa', '__package__': 'structure_audit'}
            exec(compile(module_path.read_text(), str(module_path), 'exec'), namespace)
            r = namespace['audit_receptor_msa'](**self.args)
            self.assertEqual(r.to_dict(), self.result().to_dict())
        self.assertEqual(dict(os.environ), environ)
        self.assertEqual(Path(self.args['artifact']['path']).read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
