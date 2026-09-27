"""Read-only, single-receptor alignment audit, contract 1.0 (stdlib only).

Public API: audit_receptor_msa(*, artifact, binding, manifest, config),
ReceptorMSAAuditResult, ReceptorMSAAuditError. No writer or package-level export.
Inputs must be plain finite JSON data; all fields below are required, and extra
fields are rejected. Caller objects are copied only after plain-JSON validation.

artifact: artifact_id, path, sha256, format ('fasta'/'a3m'), source_run_id,
producer, generation. producer/generation each have exactly details (nonempty
JSON object or null), missing_reason (null with details, nonempty text otherwise).
These are inert caller declarations, not verified history. One uncompressed file
only: .fa/.fas/.fasta for fasta, .a3m for a3m, exact canonical absolute path under
allowed_input_roots. No format detection, discovery or secondary data-file reads.

binding: binding_id, artifact_id, target_id, role='receptor', chain_id (may be ''),
segment (nonnegative int), model_id (string), query_record_id, query_sequence
(nonempty uppercase AA20), query_sequence_sha256, column_map, column_map_sha256,
sequence_map, sequence_map_sha256, residue_map, residue_map_sha256, map_source.
map_source: artifact_id, sha256, source_run_id, model_id. This is a supplied
structural source reference; its bytes are NOT opened or reverified.
column_map: ordered [{query_column, sequence_position, reason}], covering every
parsed column. Query residues map sequentially to 1..len(query_sequence), query
gaps to null with reason='query_gap'. sequence_map uses the existing entries
contract: [{sequence_position, residue_index, reason}], every position exactly
once, no reused residue. Null residue_index requires a reason; mapped entries
require null reason. residue_map is the unchanged canonical default-altloc-A
table shape from mapping.canonical_residue_map. Its complete snapshot and author/
label identifiers survive; mapped rows must be standard AA ATOM residues of the
declared chain/segment/model. No Structure object or inferred alignment is made.

config: version='1.0', allowed_input_roots (unique canonical existing dirs),
parsing_profile, parsing_profile_sha256, position_bases,
include_query_in_statistics (bool), duplicate_key='exact_parsed_alignment_tokens',
duplicate_policy ('keep'/'count_once'/'error'),
gap_denominator ('all_observations'/'non_unknown'),
unknown_denominator ('all_observations'/'non_gap'),
frequency_denominator='valid_amino_acids', entropy_alphabet='ACDEFGHIKLMNPQRSTVWY',
entropy_log_base (integer 2 or string 'e'), entropy_gap_policy='exclude',
entropy_unknown_policy='exclude', entropy_pseudocount=0 (integer),
coverage_token_policy='valid_amino_acids',
coverage_denominator='query_sequence_length', coverage_aggregation='any_contributing_row'.

parsing_profile has exactly name, format, encoding='utf-8',
record_id_rule='first_ascii_whitespace_token', multiline=True,
sequence_whitespace='reject', blank_lines='reject', newline_policy='lf_or_crlf',
lowercase, dot, star='reject', gap='preserve', query_insertions='reject',
insertion_alphabet='ACDEFGHIKLMNPQRSTVWY', unknown_tokens (unique character list
drawn from XBZJUO), unknown_policy ('reject'/'retain_as_unknown').
For name='aligned_fasta_v1', format='fasta', lowercase=dot='reject'.
For name='a3m_match_columns_v1', format='a3m', lowercase='remove_insertion',
dot='remove_insertion_padding'. Only lowercase AA20 letters are insertions;
lowercase unknowns are unsupported, never discarded without validation. Query
lowercase/dot and every '*' are errors. '-' occupies a parsed column, but only
non-gap query tokens advance sequence_position. No uppercase conversion occurs.
Headers start with '>' immediately followed by an ID. IDs are unique; descriptions
are retained. Sequence lines contain no whitespace; wrapping only concatenates
lines with exact raw fragments/line endings retained. LF, CRLF, and missing final
newline are supported. Empty lines/records, comments and a BOM are unsupported.

position_bases: row_index=raw_token_index=query_column=residue_index=0,
sequence_position=source_line=source_character=1. Author/label residue identifiers
are native identifiers, not rebased. Each token records raw offset/physical
locator, parsed column or null, and insertion_anchor (number of preceding parsed
columns, i.e. a 0..width boundary). A3M raw offsets are row-local, NOT shared columns.
Token query_sequence_position records the composed query-column mapping; inserted
tokens and query-gap columns have no query sequence position.

Duplicates compare exact parsed token strings (unknown symbols stay distinct).
Input depth/unique/duplicate counts include query. 'error' rejects duplicates in
the entire input. Statistics first apply include_query, then keep all eligible
rows or contribute once per exact group (first eligible raw row is representative).
All raw rows and group membership survive; this is not subsampling an output MSA.
Column fractions use configured denominators; frequencies/entropy use only AA20.
Entropy has no smoothing. All-gap/no-valid-AA columns have null derived metrics
with reasons, including fractions; raw counts remain. Summary fractions pool all
contributing cells, including such columns. There is no pooled entropy statistic.
Row coverage = valid AA at query residue columns / query length. Summary coverage
= query positions with >=1 contributing AA / query length. Zero contributing
rows yield null, not zero. Structure-map coverage is not MSA query coverage.

manifest is the existing run_manifest schema with valid UTC timestamp, canonical
run/output paths and config_hash. Its config.receptor_msa_audit_adapter must equal
{config, artifact_sha256: hash_config(artifact), binding_sha256: hash_config(binding)}.
The alignment must match exactly one manifest input path/hash. Other manifest
inputs are preserved but never opened. No make_manifest/git/output allocation.
The manifest hash is hash_config(manifest), not a serialized JSON file byte hash.

Result: summary, rows, columns, diagnostics, audit; to_dict returns detached strict
JSON. audit retains exact input snapshots and all hashes, position conventions,
import run and source runs. File bytes are hashed before parsing and rechecked
before return. Error diagnostics include code/message/artifact_id/binding_id and
locator; no partial result is attached even on late failures. Valid missing data
is null+reason, never a substitute for a contract/token/map/hash failure.

Scope: descriptive supplied-alignment statistics only; no CandidateEvidence,
CheckReport, affinity, ranking, biological success, coevolution or model output.
Depth and unique counts are NOT N_eff/effective sequence number, evolutionary
population or natural-homolog quality. Supplied-map consistency does not verify
structural source bytes, biological identity, alignment quality or producer history.
Trusted roots, in-memory input size, and before/after file checks only; hostile
concurrent replacement is outside this local utility's threat model.
"""
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import hashlib
import math
from pathlib import Path
import re
import stat

from .evidence import sequence_hash
from .mapping import AA
from .provenance import hash_config, hash_file
from .validation import validate_named

__all__ = ['audit_receptor_msa', 'ReceptorMSAAuditResult', 'ReceptorMSAAuditError']
_NAME = 'receptor_msa_audit_adapter'
_AA = 'ACDEFGHIKLMNPQRSTVWY'
_BASES = dict(row_index=0, raw_token_index=0, query_column=0, residue_index=0,
              sequence_position=1, source_line=1, source_character=1)
_LIMITATIONS = [
    'Descriptive supplied-alignment statistics only; no biological-success or coevolution claim',
    'Depth and unique counts are not N_eff, effective sequence number, evolutionary population or natural-homolog quality',
    'Structural map/source and producer history are caller-supplied; structural source bytes are not reverified',
    'No CandidateEvidence, CheckReport, ranking, affinity, contact or model-output import',
]


class ReceptorMSAAuditError(ValueError):
    """Fatal diagnostic only; never carries partial rows, metrics or result."""

    def __init__(self, code, message, *, artifact_id=None, binding_id=None, locator=None):
        self.diagnostics = [dict(severity='error', code=code, message=message,
                                 artifact_id=artifact_id, binding_id=binding_id, locator=locator)]
        super().__init__(f'{code}: {message}')


@dataclass
class ReceptorMSAAuditResult:
    summary: dict
    rows: list
    columns: list
    diagnostics: list
    audit: dict

    def to_dict(self):
        data = deepcopy(dict(summary=self.summary, rows=self.rows, columns=self.columns,
                             diagnostics=self.diagnostics, audit=self.audit))
        hash_config(data)
        return data


def _plain(value):
    # Reject object/subclass hooks before copying or hashing caller-owned data.
    if type(value) is dict:
        if any(type(k) is not str for k in value):
            raise ValueError('JSON object keys must be strings')
        for v in value.values():
            _plain(v)
    elif type(value) is list:
        for v in value:
            _plain(v)
    elif type(value) not in (str, int, float, bool, type(None)):
        raise ValueError('Plain JSON data required')
    elif type(value) is float and not math.isfinite(value):
        raise ValueError('Finite JSON data required')


def _keys(obj, names):
    if not isinstance(obj, dict) or set(obj) != set(names.split()):
        raise ValueError(f'Expected exactly these fields: {names}')


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Nonempty string required')


def _integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f'Integer >= {minimum} required')


def _digest(value):
    if not isinstance(value, str) or not re.fullmatch('[a-f0-9]{64}', value):
        raise ValueError('Lowercase SHA-256 required')


def _path(value, roots=None):
    _text(value)
    p = Path(value)
    if (not p.is_absolute() or str(p) != value or '..' in p.parts
            or any(c in value for c in '*?[]') or p.resolve() != p):
        raise ValueError('Exact canonical absolute local path required')
    if roots is not None and not any(p.is_relative_to(r) for r in roots):
        raise ValueError('Path outside allowed_input_roots')
    return p


def _metric(numerator, denominator, reason=None):
    reason = reason or ('zero_denominator' if denominator == 0 else None)
    return dict(value=None if reason else numerator / denominator,
                numerator=numerator, denominator=denominator, reason=reason)


class _Audit:
    def __init__(self, artifact, binding, manifest, config):
        self.a, self.b, self.m, self.c = deepcopy([artifact, binding, manifest, config])
        self.phase, self.locator = 'invalid_contract', None
        self.diagnostics = []

    def fail(self, code, message):
        raise ReceptorMSAAuditError(code, message, artifact_id=self.a.get('artifact_id'),
                                   binding_id=self.b.get('binding_id'), locator=self.locator)

    def warn(self, code, message, locator=None):
        self.diagnostics.append(dict(severity='warning', code=code, message=message,
                                     artifact_id=self.a['artifact_id'], binding_id=self.b['binding_id'],
                                     locator=locator))

    def hashed(self, value, digest, code):
        _digest(digest)
        if hash_config(value) != digest:
            self.fail(code, 'Supplied canonical JSON hash does not match content')

    def prepare(self):
        self.phase = 'unsupported_config'
        _keys(self.c, 'version allowed_input_roots parsing_profile parsing_profile_sha256 position_bases '
              'include_query_in_statistics duplicate_key duplicate_policy gap_denominator unknown_denominator '
              'frequency_denominator entropy_alphabet entropy_log_base entropy_gap_policy entropy_unknown_policy '
              'entropy_pseudocount coverage_token_policy coverage_denominator coverage_aggregation')
        fixed = dict(version='1.0', duplicate_key='exact_parsed_alignment_tokens',
                     frequency_denominator='valid_amino_acids', entropy_alphabet=_AA,
                     entropy_gap_policy='exclude', entropy_unknown_policy='exclude', entropy_pseudocount=0,
                     coverage_token_policy='valid_amino_acids', coverage_denominator='query_sequence_length',
                     coverage_aggregation='any_contributing_row', position_bases=_BASES)
        if hash_config({k: self.c[k] for k in fixed}) != hash_config(fixed):
            self.fail('unsupported_config', 'Unsupported fixed version-1 configuration or position bases')
        if type(self.c['include_query_in_statistics']) is not bool:
            raise ValueError('include_query_in_statistics must be boolean')
        for key, values in [('duplicate_policy', ('keep', 'count_once', 'error')),
                            ('gap_denominator', ('all_observations', 'non_unknown')),
                            ('unknown_denominator', ('all_observations', 'non_gap'))]:
            if self.c[key] not in values:
                raise ValueError(f'Unsupported {key}')
        if not (type(self.c['entropy_log_base']) is int and self.c['entropy_log_base'] == 2
                or self.c['entropy_log_base'] == 'e'):
            raise ValueError('entropy_log_base must be integer 2 or string e')
        self.phase = 'parsing_profile_mismatch'
        p = self.c['parsing_profile']
        _keys(p, 'name format encoding record_id_rule multiline sequence_whitespace blank_lines newline_policy '
              'lowercase dot star gap query_insertions insertion_alphabet unknown_tokens unknown_policy')
        profile = dict(encoding='utf-8', record_id_rule='first_ascii_whitespace_token', multiline=True,
                       sequence_whitespace='reject', blank_lines='reject', newline_policy='lf_or_crlf',
                       star='reject', gap='preserve', query_insertions='reject', insertion_alphabet=_AA)
        if p['name'] == 'aligned_fasta_v1':
            profile.update(name=p['name'], format='fasta', lowercase='reject', dot='reject')
        elif p['name'] == 'a3m_match_columns_v1':
            profile.update(name=p['name'], format='a3m', lowercase='remove_insertion', dot='remove_insertion_padding')
        else:
            raise ValueError('Unsupported parsing profile')
        if hash_config({k: p[k] for k in profile}) != hash_config(profile):
            raise ValueError('Parsing profile fields do not match its named contract')
        unknown = p['unknown_tokens']
        if (not isinstance(unknown, list) or any(type(x) is not str or x not in tuple('XBZJUO') for x in unknown)
                or len(set(unknown)) != len(unknown) or p['unknown_policy'] not in ('reject', 'retain_as_unknown')):
            raise ValueError('Invalid explicit unknown-token policy')
        self.hashed(p, self.c['parsing_profile_sha256'], self.phase)
        self.phase = 'unsafe_path'
        roots = self.c['allowed_input_roots']
        if not isinstance(roots, list) or not roots:
            raise ValueError('Nonempty allowed_input_roots required')
        self.roots = [_path(x) for x in roots]
        if len(set(self.roots)) != len(roots) or any(not x.is_dir() for x in self.roots):
            raise ValueError('Unique existing canonical root directories required')
        self.phase = 'invalid_contract'
        _keys(self.a, 'artifact_id path sha256 format source_run_id producer generation')
        for k in ('artifact_id', 'source_run_id'):
            _text(self.a[k])
        _digest(self.a['sha256'])
        if self.a['format'] != p['format']:
            self.fail('unsupported_format', 'Artifact format must match explicit parsing profile')
        self.phase = 'unsafe_path'
        self.path = _path(self.a['path'], self.roots)
        suffixes = ('.fa', '.fas', '.fasta') if p['format'] == 'fasta' else ('.a3m',)
        if self.path.suffix.lower() not in suffixes:
            self.fail('unsupported_format', 'Only an uncompressed explicit FASTA/A3M artifact is supported')
        self.phase = 'invalid_contract'
        for k in ('producer', 'generation'):
            d = self.a[k]
            _keys(d, 'details missing_reason')
            if d['details'] is None:
                _text(d['missing_reason'])
                self.warn('incomplete_provenance', d['missing_reason'], {'field': k})
            elif not isinstance(d['details'], dict) or not d['details'] or d['missing_reason'] is not None:
                raise ValueError('Declaration requires details or null with missing_reason')
        self.prepare_binding()
        self.phase = 'manifest_contract'
        validate_named(self.m, 'run_manifest')
        self.hashed(self.m['config'], self.m['config_hash'], self.phase)
        stamp = datetime.fromisoformat(self.m['timestamp'])
        if stamp.utcoffset() is None or stamp.utcoffset().total_seconds() != 0:
            raise ValueError('Manifest timestamp must be UTC')
        run_dir = _path(self.m['run_directory'])
        if any(not _path(x).is_relative_to(run_dir) for x in self.m['output_paths']):
            raise ValueError('Manifest output outside run directory')
        attestation = dict(config=self.c, artifact_sha256=hash_config(self.a), binding_sha256=hash_config(self.b))
        if hash_config(self.m['config'].get(_NAME)) != hash_config(attestation):
            raise ValueError('Manifest must attest exact config, artifact and binding')
        matches = [x for x in self.m['input_files'] if x['path'] == self.a['path']]
        if matches != [dict(path=self.a['path'], sha256=self.a['sha256'])]:
            self.fail('manifest_artifact_mismatch', 'Exactly one matching manifest input required')

    def prepare_binding(self):
        b = self.b
        _keys(b, 'binding_id artifact_id target_id role chain_id segment model_id query_record_id query_sequence '
              'query_sequence_sha256 column_map column_map_sha256 sequence_map sequence_map_sha256 '
              'residue_map residue_map_sha256 map_source')
        for k in ('binding_id', 'artifact_id', 'target_id', 'model_id', 'query_record_id'):
            _text(b[k])
        if b['artifact_id'] != self.a['artifact_id'] or b['role'] != 'receptor' or not isinstance(b['chain_id'], str):
            self.fail('chain_binding', 'Explicit receptor/artifact/chain binding required')
        _integer(b['segment'])
        self.phase = 'query_mismatch'
        q = b['query_sequence']
        if not isinstance(q, str) or not q or any(x not in _AA for x in q):
            raise ValueError('Query must be an explicit uppercase standard-AA sequence')
        _digest(b['query_sequence_sha256'])
        if sequence_hash(q) != b['query_sequence_sha256']:
            raise ValueError('Query exact-text hash mismatch')
        self.phase = 'residue_map_mismatch'
        source = b['map_source']
        _keys(source, 'artifact_id sha256 source_run_id model_id')
        for k in ('artifact_id', 'source_run_id', 'model_id'):
            _text(source[k])
        _digest(source['sha256'])
        if source['model_id'] != b['model_id']:
            raise ValueError('Map source model does not match binding')
        rows = b['residue_map']
        if not isinstance(rows, list) or not rows:
            raise ValueError('Nonempty supplied canonical residue map required')
        self.hashed(rows, b['residue_map_sha256'], self.phase)
        seen = set()
        for i, r in enumerate(rows):
            self.locator = {'residue_index': i}
            _keys(r, 'residue_index model_id chain_id segment record_group residue_id insertion_code residue_name '
                  'label_chain_id label_seq_id source_lines atom_names selected_altloc missing_backbone_atoms warnings')
            _integer(r['residue_index']); _integer(r['segment'])
            if r['residue_index'] != i or type(r['residue_id']) is not int or r['model_id'] != b['model_id']:
                raise ValueError('Canonical indices/model/author identifier mismatch')
            for k in ('chain_id', 'insertion_code', 'residue_name'):
                if not isinstance(r[k], str):
                    raise ValueError('Canonical residue identity must retain string fields')
            _text(r['residue_name'])
            if r['record_group'] not in ('ATOM', 'HETATM') or r['selected_altloc'] != 'A':
                raise ValueError('Default-altloc-A canonical map required')
            if r['label_chain_id'] is not None and not isinstance(r['label_chain_id'], str):
                raise ValueError('Invalid label chain ID')
            if r['label_seq_id'] is not None and type(r['label_seq_id']) is not int:
                raise ValueError('Invalid label sequence ID')
            if not isinstance(r['source_lines'], list) or not r['source_lines']:
                raise ValueError('Canonical map must retain source lines')
            for line in r['source_lines']:
                _integer(line, 1)
            for k in ('atom_names', 'missing_backbone_atoms', 'warnings'):
                if not isinstance(r[k], list) or any(not isinstance(x, str) or not x for x in r[k]):
                    raise ValueError(f'Invalid canonical {k}')
            identity = tuple(r[k] for k in ('model_id', 'chain_id', 'segment', 'record_group', 'residue_id', 'insertion_code'))
            if identity in seen:
                raise ValueError('Ambiguous duplicate canonical residue identity')
            seen.add(identity)
        self.phase = 'sequence_mapping_mismatch'
        entries = b['sequence_map']
        if not isinstance(entries, list) or len(entries) != len(q):
            raise ValueError('Mapping must cover all query sequence positions')
        self.hashed(entries, b['sequence_map_sha256'], self.phase)
        positions, used = set(), set()
        self.sequence_entries = {}
        for e in entries:
            _keys(e, 'sequence_position residue_index reason')
            pos, idx = e['sequence_position'], e['residue_index']
            self.locator = {'sequence_position': pos}
            _integer(pos, 1)
            if pos > len(q) or pos in positions:
                raise ValueError('Invalid/duplicate sequence position')
            positions.add(pos)
            if idx is None:
                _text(e['reason'])
                self.warn('missing_residue_mapping', e['reason'], self.locator)
            else:
                _integer(idx)
                if idx >= len(rows) or idx in used or e['reason'] is not None:
                    raise ValueError('Invalid/reused residue or conflicting mapped reason')
                used.add(idx)
                r = rows[idx]
                if (r['chain_id'], r['segment']) != (b['chain_id'], b['segment']):
                    self.fail('chain_binding', 'Mapped residue belongs to another chain/segment')
                if r['record_group'] != 'ATOM' or AA.get(r['residue_name']) != q[pos-1]:
                    raise ValueError('Sequence disagrees with standard polymer residue')
            self.sequence_entries[pos] = e
        self.phase = 'column_mapping_mismatch'
        if not isinstance(b['column_map'], list) or not b['column_map']:
            raise ValueError('Explicit column mapping required')
        self.hashed(b['column_map'], b['column_map_sha256'], self.phase)
        for i, e in enumerate(b['column_map']):
            self.locator = {'query_column': i}
            _keys(e, 'query_column sequence_position reason')
            _integer(e['query_column'])
            if e['query_column'] != i:
                raise ValueError('Column map must contain every column in order')
            if e['sequence_position'] is not None:
                _integer(e['sequence_position'], 1)
        self.locator = None

    def verify_file(self):
        self.locator = None
        self.phase = 'unsafe_path'
        path = _path(self.a['path'], self.roots)
        self.phase = 'artifact_read_error'
        if not stat.S_ISREG(path.stat().st_mode):
            raise ValueError('Existing regular alignment file required')
        return path

    def parse(self):
        path = self.verify_file()
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != self.a['sha256']:
            self.fail('stale_artifact_hash', 'Alignment byte snapshot differs from declared hash')
        self.phase = 'alignment_parse_error'
        text = raw.decode('utf-8')
        if '\r' in text.replace('\r\n', ''):
            raise ValueError('Only LF or CRLF line endings are supported')
        # Split only physical LF/CRLF, never Unicode line separators or controls.
        parts = text.split('\n')
        fragments = [part+'\n' for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])
        rows, ids, current = [], set(), None
        for line_no, fragment in enumerate(fragments, 1):
            self.locator = {'source_line': line_no}
            line = fragment[:-2] if fragment.endswith('\r\n') else fragment[:-1] if fragment.endswith('\n') else fragment
            if not line or any(not c.isprintable() and c != '\t' for c in line):
                raise ValueError('Empty lines and control characters are unsupported')
            if line.startswith('>'):
                if not re.fullmatch(r'>[^\s>]+(?:[ \t][^\r\n]*)?', line):
                    raise ValueError('Header must start with > followed immediately by an ID')
                rid = re.split('[ \t]', line[1:], maxsplit=1)[0]
                if rid in ids:
                    self.fail('duplicate_identity', 'Record IDs must be unique')
                ids.add(rid)
                current = dict(row_index=len(rows), record_id=rid, raw_header=line, raw_header_fragment=fragment,
                               header_line=line_no, raw_fragments=[], raw_sequence='', parsed_sequence='', tokens=[])
                rows.append(current)
            else:
                if current is None:
                    raise ValueError('Sequence content before first header')
                current['raw_fragments'].append(dict(source_line=line_no, text=fragment))
                current['raw_sequence'] += line
                for char_no, token in enumerate(line, 1):
                    self.parse_token(current, token, line_no, char_no)
        if not rows:
            raise ValueError('Alignment is empty')
        for row in rows:
            self.locator = {'row_index': row['row_index'], 'source_line': row['header_line']}
            if not row['parsed_sequence']:
                raise ValueError('Empty record or zero parsed columns')
            row['raw_sequence_sha256'] = sequence_hash(row['raw_sequence'])
            row['parsed_sequence_sha256'] = sequence_hash(row['parsed_sequence'])
        self.locator = None
        query = next((r for r in rows if r['record_id'] == self.b['query_record_id']), None)
        if query is None:
            self.fail('query_mismatch', 'Explicit query_record_id absent from alignment')
        for row in rows:
            if len(row['parsed_sequence']) != len(query['parsed_sequence']):
                self.locator = {'row_index': row['row_index'], 'record_id': row['record_id'],
                                'source_line': row['header_line'], 'expected_width': len(query['parsed_sequence']),
                                'observed_width': len(row['parsed_sequence'])}
                self.fail('ragged_alignment', 'Rows must have equal parsed match-column width')
        if query['parsed_sequence'].replace('-', '') != self.b['query_sequence']:
            self.fail('query_mismatch', 'Gap-free parsed query differs from supplied sequence')
        columns, pos = [], 0
        for col, token in enumerate(query['parsed_sequence']):
            if token != '-':
                pos += 1
            columns.append(dict(query_column=col, sequence_position=pos if token != '-' else None,
                                reason=None if token != '-' else 'query_gap'))
        if hash_config(columns) != hash_config(self.b['column_map']):
            self.fail('column_mapping_mismatch', 'Explicit map differs from query token positions')
        for row in rows:
            for token in row['tokens']:
                col = token['query_column']
                token['query_sequence_position'] = columns[col]['sequence_position'] if col is not None else None
        self.rows, self.query, self.columns = rows, query, columns

    def parse_token(self, row, token, line, char):
        self.locator = dict(row_index=row['row_index'], record_id=row['record_id'], source_line=line,
                            source_character=char, raw_token_index=len(row['tokens']))
        p = self.c['parsing_profile']
        query = row['record_id'] == self.b['query_record_id']
        action, reason, effect, kind = 'preserve', 'valid_amino_acid', 'occupies_alignment_column', 'amino_acid'
        if token in _AA:
            pass
        elif token == '-':
            reason, kind = 'alignment_gap', 'gap'
        elif token in p['unknown_tokens'] and p['unknown_policy'] == 'retain_as_unknown' and not query:
            reason, kind = 'outside_standard_amino_acid_alphabet', 'unknown'
        elif token in 'acdefghiklmnpqrstvwy' and p['lowercase'] == 'remove_insertion' and not query:
            action, reason, effect, kind = 'remove_insertion', 'a3m_lowercase_insertion', 'no_alignment_column', 'insertion'
        elif token == '.' and p['dot'] == 'remove_insertion_padding' and not query:
            action, reason, effect, kind = 'remove_insertion_padding', 'a3m_insertion_padding', 'no_alignment_column', 'insertion_padding'
        else:
            self.fail('invalid_token', f'Token {token!r} is unsupported by the explicit profile/query contract')
        col = len(row['parsed_sequence'])
        if action == 'preserve':
            row['parsed_sequence'] += token
        row['tokens'].append(dict(**self.locator, original_token=token, token_class=kind, action=action,
                                  reason=reason, position_effect=effect,
                                  query_column=col if action == 'preserve' else None,
                                  insertion_anchor=col if action != 'preserve' else None))

    def counts(self, tokens, *, column=False):
        counts = Counter(tokens)
        valid = sum(counts[x] for x in _AA)
        gap, unknown, n = counts['-'], sum(v for k, v in counts.items() if k not in _AA and k != '-'), sum(counts.values())
        reason = 'no_contributing_rows' if not n else 'all_gap' if gap == n else 'no_valid_amino_acids' if not valid else None
        gap_d = n if self.c['gap_denominator'] == 'all_observations' else n-unknown
        unknown_d = n if self.c['unknown_denominator'] == 'all_observations' else n-gap
        result = dict(observation_count=n, valid_amino_acid_count=valid, gap_count=gap, unknown_count=unknown,
                      amino_acid_counts={x: counts[x] for x in _AA}, unknown_token_counts={x: counts[x] for x in self.c['parsing_profile']['unknown_tokens']},
                      gap_fraction=_metric(gap, gap_d, reason if column or not n else None),
                      unknown_fraction=_metric(unknown, unknown_d, reason if column or not n else None))
        if column:
            freq = None if reason else {x: counts[x]/valid for x in _AA}
            entropy = None if reason else -sum(p*(math.log2(p) if self.c['entropy_log_base'] == 2 else math.log(p))
                                              for p in freq.values() if p)
            result.update(amino_acid_frequencies=dict(value=freq, denominator=valid, reason=reason),
                          shannon_entropy=dict(value=(0.0 if entropy == 0 else entropy), valid_count=valid,
                                               log_base=self.c['entropy_log_base'], reason=reason))
        return result

    def compute(self):
        groups = {}
        for row in self.rows:
            groups.setdefault(row['parsed_sequence'], []).append(row['row_index'])
        if self.c['duplicate_policy'] == 'error' and any(len(x) > 1 for x in groups.values()):
            self.locator = {'row_indices': next(x for x in groups.values() if len(x) > 1)}
            self.fail('duplicate_policy_violation', 'Duplicate parsed rows forbidden by explicit policy')
        contribution = set()
        group_audit = []
        for members in groups.values():
            eligible = [i for i in members if self.c['include_query_in_statistics'] or self.rows[i] is not self.query]
            selected = eligible[:1] if self.c['duplicate_policy'] == 'count_once' else eligible
            contribution.update(selected)
            group_audit.append(dict(group_index=len(group_audit), row_indices=members, eligible_row_indices=eligible,
                                    contributing_row_indices=selected))
            for i in members:
                self.rows[i]['duplicate_group_index'] = len(group_audit)-1
        if any(len(x) > 1 for x in groups.values()):
            self.warn('duplicate_rows', 'Exact parsed duplicate groups retained; see explicit statistical contributions')
        query_cols = [x['query_column'] for x in self.columns if x['sequence_position'] is not None]
        qlen = len(query_cols)
        for row in self.rows:
            row['is_query'] = row is self.query
            row['contributes_to_statistics'] = row['row_index'] in contribution
            row['statistics_exclusion_reason'] = (None if row['contributes_to_statistics'] else
                'query_excluded' if row['is_query'] and not self.c['include_query_in_statistics'] else 'duplicate_counted_once')
            row['query_coverage'] = _metric(sum(row['parsed_sequence'][j] in _AA for j in query_cols), qlen)
        contributing = [r for r in self.rows if r['contributes_to_statistics']]
        covered = sum(any(r['parsed_sequence'][j] in _AA for r in contributing) for j in query_cols)
        summary = dict(alignment_depth=len(self.rows), alignment_width=len(self.columns), unique_row_count=len(groups),
                       duplicate_count=len(self.rows)-len(groups), statistics_row_count=len(contributing),
                       statistics_unique_row_count=len({r['parsed_sequence'] for r in contributing}),
                       query_row_index=self.query['row_index'], query_length=qlen, duplicate_groups=group_audit,
                       query_coverage=_metric(covered, qlen, None if contributing else 'no_contributing_rows'),
                       **self.counts(c for r in contributing for c in r['parsed_sequence']))
        for col in self.columns:
            j, pos = col['query_column'], col['sequence_position']
            entry = self.sequence_entries[pos] if pos is not None else None
            col['residue_index'] = entry['residue_index'] if entry else None
            col['residue_mapping_reason'] = entry['reason'] if entry else 'query_gap'
            col['metrics'] = self.counts((r['parsed_sequence'][j] for r in contributing), column=True)
            reason = col['metrics']['shannon_entropy']['reason']
            if reason:
                self.warn('unavailable_column_metrics', reason, {'query_column': j, 'sequence_position': pos})
        return summary

    def run(self):
        self.prepare()
        self.parse()
        self.phase, self.locator = 'statistics_error', None
        summary = self.compute()
        audit = dict(adapter=_NAME, adapter_version='1.0', category='supplied_receptor_alignment_statistics_only',
                     identity_status='local_alignment_and_supplied_map_consistency_verified',
                     map_verification='supplied_map_consistency_verified', producer_verification='caller_supplied_not_verified',
                     artifact=self.a, binding=self.b, manifest=self.m, configuration=self.c,
                     artifact_sha256=hash_config(self.a), binding_sha256=hash_config(self.b), manifest_sha256=hash_config(self.m),
                     configuration_sha256=hash_config(self.c), file_sha256=self.a['sha256'],
                     parsing_profile_sha256=self.c['parsing_profile_sha256'], query_sequence_sha256=self.b['query_sequence_sha256'],
                     column_map_sha256=self.b['column_map_sha256'], sequence_map_sha256=self.b['sequence_map_sha256'],
                     residue_map_sha256=self.b['residue_map_sha256'], import_run_id=self.m['run_id'],
                     source_run_id=self.a['source_run_id'], position_bases=deepcopy(_BASES), limitations=list(_LIMITATIONS))
        result = ReceptorMSAAuditResult(summary, self.rows, self.columns, self.diagnostics, audit)
        result.to_dict()
        path = self.verify_file()
        if hash_file(path) != self.a['sha256']:
            self.fail('stale_artifact_hash', 'Alignment changed during audit')
        return result


def audit_receptor_msa(*, artifact, binding, manifest, config):
    """Audit one explicit alignment; return no partial result on any fatal error."""
    worker = None
    try:
        for value in (artifact, binding, manifest, config):
            _plain(value)
            if not isinstance(value, dict):
                raise ValueError('Top-level inputs must be plain JSON objects')
        worker = _Audit(artifact, binding, manifest, config)
        return worker.run()
    except ReceptorMSAAuditError:
        raise
    except (ValueError, TypeError, KeyError, IndexError, OSError, AttributeError, RecursionError) as exc:
        raise ReceptorMSAAuditError(worker.phase if worker else 'invalid_contract', str(exc),
                                   artifact_id=worker.a.get('artifact_id') if worker else None,
                                   binding_id=worker.b.get('binding_id') if worker else None,
                                   locator=worker.locator if worker else None) from exc
