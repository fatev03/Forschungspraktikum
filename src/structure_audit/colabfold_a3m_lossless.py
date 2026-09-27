"""Explicit, read-only ColabFold/MMseqs2-style A3M profile, version 1.0.

Public API (independent of receptor_msa_audit_adapter; no package-level export):
    parse_colabfold_a3m(*, artifact, config, binding=None)
    ColabFoldA3MResult, ColabFoldA3MReaderResult, ColabFoldA3MError

This is not a general A3M/FASTA/A2M/HHM/Stockholm detector. The caller must select
profile_id='colabfold_a3m_lossless_v1', profile_version='1.0', and
profile_selection='explicit_only'. No fallback, writer, clock, inference, search,
manifest allocation, environment mutation, or producer-history verification.

All inputs are plain finite JSON. Unknown fields are rejected. Hashes of JSON
objects use UTF-8 JSON, sorted keys, compact separators, ensure_ascii=False.
Sequence hashes cover exact sequence text without a trailing newline.

artifact (exact fields): artifact_id, path, sha256, format='a3m',
source_kind='caller_declared_colabfold_mmseqs2_style_a3m',
source_kind_status='caller_supplied_not_verified', producer, provenance.
producer: name, version, database, database_version, search_settings,
missing_reasons. Values are nonempty strings (search_settings: nonempty object)
or null; missing_reasons has exactly the null-valued keys, each with a reason.
provenance: details (nonempty JSON object or null), missing_reason (null with
details, nonempty text otherwise). These inert declarations are never opened.

config required fields: profile_id, profile_version, profile_selection,
allowed_input_roots (unique existing canonical absolute directories),
expected_artifact_sha256, query_selector, canonical_query_sequence,
canonical_query_sequence_sha256, query_gap_policy='preserve_and_map_to_null',
lowercase_x_policy (exact fixed fields documented in LOWERCASE_X_POLICY),
unknown_tokens, unknown_policy. Only []/'reject' or ['X']/'retain_as_unknown'.
Optional gates: metrics_enabled=False, metric_policy=None, binding_enabled=False.
Disabled gates reject supplied metric_policy/binding, rather than ignoring them.
Even reader-only mode requires an explicit selected query and canonical AA20
sequence/hash. No selector yields an error, never an implicitly selected query.
query_selector: {record_occurrence_id} OR {header_line, raw_header}; raw_header
includes '>' and excludes the line ending. Null is an unresolved selector, not
an instruction to infer one. Occurrence IDs are scoped by the artifact hash.

metric_policy (all required when enabled): include_query_in_statistics (bool),
sequence_duplicate_key ('raw_sequence_tokens'/'parsed_match_tokens'),
duplicate_policy ('keep'/'count_once'/'error'),
representative_selection='first_eligible_occurrence_in_file_order',
gap_denominator ('all_observations'/'non_unknown'),
unknown_denominator ('all_observations'/'non_gap'),
frequency_denominator='valid_amino_acids', entropy_alphabet=AA20,
entropy_log_base (integer 2 or string 'e'), entropy_gap_policy='exclude',
entropy_unknown_policy='exclude', entropy_pseudocount=0 (integer),
coverage_token_policy='valid_amino_acids',
coverage_denominator='canonical_query_length',
coverage_aggregation='any_contributing_row'. There are no metric defaults.

binding (all required only when enabled): binding_id, artifact_id,
artifact_sha256, record_occurrence_id, canonical_query_sequence_sha256,
target_id, role='receptor', model_id, chain_id, segment, column_map,
column_map_sha256, sequence_map, sequence_map_sha256, residue_map,
residue_map_sha256, map_source. column_map uses ordered
{query_column, sequence_position, reason}, with null/'query_gap' for query gaps.
sequence_map uses {sequence_position, residue_index, reason}; every canonical
position must map to a distinct standard ATOM residue, with reason=null. This
new full-binding contract rejects missing/unmapped residues. residue_map is the
unchanged canonical default-altloc-A table shape. map_source: artifact_id,
sha256, source_run_id, model_id. Structural source bytes are NOT reopened.
The parser never generates maps. Only an enabled binding stage validates the
caller's complete maps, entry by entry, and returns their supplied snapshot.

Reader-only result schema (ColabFoldA3MReaderResult): query is a
ReaderQueryInventory, with selector/identity/canonical sequence/hash only.
There is no observed_column_map or map hash. binding, metrics and the binding
contract hash are null; their execution statuses are disabled. Position bases
contain projection/physical locators only, no sequence/residue position bases.
MatchProjectionToken.parsed_column is the zero-based A3M match projection
index ONLY; it implies no canonical sequence position or structural identity.
Token query_sequence_position stays null for ALL tokens, including query gaps,
even if optional stages run. No token is enriched with derived binding fields.
Enabled metrics label columns by parsed_column only and produce no maps.

LF/CRLF (including mixed endings), wrapping, and missing final newline survive.
One optional leading # line is opaque, never interpreted. Raw bytes and every
fragment survive base64 round trips. Raw ID/header duplicates are nonfatal;
occurrence IDs are record:<zero-based index>@header_line:<one-based line>.
Standard lowercase AA20, '.', and lowercase x in nonquery records have null
parsed columns and an anchor equal to the count of preceding match columns.
They are retained, not erased. x is unknown_lowercase_insertion, not AA20.
Only AA20 and '-' are permitted in the selected query. Other lowercase unknowns,
uppercase B/Z/J/U/O, '*', controls, blank records/lines and whitespace fail closed.

Result.to_dict() returns detached JSON. reconstruct_bytes() returns original
bytes from stored fragments in memory, never writes a file. Errors carry fatal
diagnostics, without partial result/metrics. Duplicate inventories cover ALL
occurrences; duplicate_occurrences means sum(n-1), member_count means sum(n).
Input depth is occurrence count, not a sequence weighting or quality measure.
Lowercase x contributes to insertion inventory only, never to match statistics.
All-gap/no-AA columns have null derived metrics with reasons; pooled fractions
retain all contributing cells. No contributing rows yields null coverage.
Only the explicit alignment file is read, with path/hash checks before/after.
Trusted-root checks do not defend against hostile transient file replacement.
"""

import base64
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import stat
from typing import TypedDict

from .mapping import AA

__all__ = ['parse_colabfold_a3m', 'ColabFoldA3MResult', 'ColabFoldA3MReaderResult',
           'ColabFoldA3MError']

_AA = 'ACDEFGHIKLMNPQRSTVWY'
_PROFILE = 'colabfold_a3m_lossless_v1'
_SOURCE = 'caller_declared_colabfold_mmseqs2_style_a3m'
LOWERCASE_X_POLICY = dict(handling='retain_with_locator_and_anchor',
    match_column_contribution='none', coverage_contribution='none',
    match_denominator_contribution='none', frequency_entropy_contribution='none')
_BASES = dict(record_index=0, raw_token_index=0, parsed_column=0,
              artifact_byte_offset=0, source_line=1, source_character=1)
_LIMITATIONS = [
    'Caller-declared ColabFold/MMseqs2-style A3M only; not a general format detector',
    'Descriptive syntax and supplied-map consistency only; no alignment-quality certificate',
    'No homology, conservation, N_eff, phylogenetic weighting, coevolution, affinity, binding or biological suitability claim',
    'Producer history and structural source identity are caller-supplied, not independently verified',
    'In-memory parsing; trusted-root before/after checks do not prevent hostile transient replacement',
    'parsed_column is a match-projection index only; token query_sequence_position is always null; no maps are generated',
]


class MatchProjectionToken(TypedDict):
    """Lossless token/physical locator schema; never a sequence or residue map."""

    record_index: int
    record_occurrence_id: str
    raw_record_id: str
    header_line: int
    sequence_line_range: list[int]
    source_line: int
    source_character: int
    raw_token_index: int
    artifact_byte_offset: int
    raw_token: str
    token_class: str
    parsed_column: int | None
    query_sequence_position: None
    insertion_anchor: int | None
    transformation_type: str
    reason: str | None


class ReaderQueryInventory(TypedDict):
    """Selector and exact canonical identity schema, with no derived maps."""

    requested_selector: dict
    status: str
    selected_occurrence: str
    candidates: list[dict]
    canonical_sequence: str
    canonical_sequence_sha256: str


def _plain(value, active=None):
    active = set() if active is None else active
    if type(value) in (dict, list):
        if id(value) in active:
            raise ValueError('Cyclic JSON data')
        active.add(id(value))
        if type(value) is dict:
            if any(type(k) is not str for k in value):
                raise ValueError('Plain string JSON keys required')
            children = value.values()
        else:
            children = value
        for child in children:
            _plain(child, active)
        active.remove(id(value))
    elif type(value) not in (str, int, float, bool, type(None)):
        raise ValueError('Plain JSON values required')
    elif type(value) is float and not math.isfinite(value):
        raise ValueError('Finite JSON numbers required')


def _canonical(value):
    _plain(value)
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _hash(value):
    return _sha(_canonical(value))


def _keys(value, required, optional=''):
    if (type(value) is not dict or not set(required.split()) <= set(value)
            or set(value) - set((required+' '+optional).split())):
        raise ValueError('Expected fields: '+required+'; optional: '+optional)


def _text(value):
    if type(value) is not str or not value.strip():
        raise ValueError('Nonempty string required')


def _integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError('Integer >= '+str(minimum)+' required')


def _digest(value):
    if type(value) is not str or not re.fullmatch(r'[a-f0-9]{64}', value):
        raise ValueError('Lowercase SHA-256 required')


def _path(value):
    _text(value)
    p = Path(value)
    if (not p.is_absolute() or str(p) != value or '..' in p.parts
            or any(c in value for c in '*?[]') or p.resolve() != p):
        raise ValueError('Exact canonical absolute local path required')
    return p


def _fraction(n, d, reason=None):
    reason = reason or ('zero_denominator' if d == 0 else None)
    return dict(value=None if reason else n/d, numerator=n, denominator=d, reason=reason)


def _groups(rows, key, headers=False):
    groups = {}
    for row in rows:
        groups.setdefault(row[key], []).append(row)
    repeated = []
    for value, members in groups.items():
        if len(members) < 2:
            continue
        item = dict(key=value, count=len(members),
                    record_occurrence_ids=[r['record_occurrence_id'] for r in members],
                    header_lines=[r['header_line'] for r in members])
        if headers:
            distinct = len({r['raw_header'] for r in members})
            item.update(distinct_header_text_count=distinct,
                header_relationship='same_full_header' if distinct == 1 else
                'record_id_only' if distinct == len(members) else 'mixed_full_header_and_id')
        repeated.append(item)
    return dict(unique_count=len(groups), duplicate_groups=len(repeated),
                duplicate_occurrences=sum(g['count']-1 for g in repeated),
                duplicate_member_count=sum(g['count'] for g in repeated), groups=repeated)


class ColabFoldA3MError(ValueError):
    """Fatal diagnostic only; no partial result, rows, metrics or binding."""

    def __init__(self, code, message, *, artifact_id=None, locator=None, details=None):
        self.diagnostics = [dict(severity='fatal', code=code, message=message,
            artifact_id=artifact_id, locator=deepcopy(locator), details=deepcopy(details))]
        super().__init__(code+': '+message)


@dataclass
class ColabFoldA3MResult:
    """Projection snapshot with optional explicit stages; reconstruction in memory."""

    data: dict

    def to_dict(self):
        _canonical(self.data)
        return deepcopy(self.data)

    def reconstruct_bytes(self):
        fragments = []
        if self.data['raw_preamble'] is not None:
            fragments.append(self.data['raw_preamble']['raw_fragment_bytes_base64'])
        for row in self.data['records']:
            fragments.append(row['raw_header_fragment_bytes_base64'])
            fragments.extend(f['raw_fragment_bytes_base64'] for f in row['sequence_fragments'])
        return b''.join(base64.b64decode(f, validate=True) for f in fragments)


class ColabFoldA3MReaderResult(ColabFoldA3MResult):
    """Reader-only schema: projection tokens, no metrics or binding output.

    Query and token schemas are closed at serialization, preventing accidental
    future enrichment with binding fields in this result type.
    """

    def to_dict(self):
        data = super().to_dict()
        if data['metrics'] is not None or data['binding'] is not None:
            raise ValueError('Reader-only result cannot contain optional stage output')
        _keys(data['query'], ' '.join(ReaderQueryInventory.__annotations__))
        _keys(data['position_bases'], ' '.join(_BASES))
        for row in data['records']:
            for token in row['tokens']:
                _keys(token, ' '.join(MatchProjectionToken.__annotations__))
                if token['query_sequence_position'] is not None:
                    raise ValueError('Projection tokens cannot imply canonical positions')
        return data


class _Reader:
    def __init__(self, artifact, config, binding):
        self.a, self.c, self.b = deepcopy((artifact, config, binding))
        self.phase, self.locator = 'invalid_contract', None
        self.diagnostics = []

    def fail(self, code, message, details=None):
        raise ColabFoldA3MError(code, message, artifact_id=self.a.get('artifact_id'),
                               locator=self.locator, details=details)

    def note(self, code, message, severity='warning', locator=None, details=None):
        self.diagnostics.append(dict(severity=severity, code=code, message=message,
            artifact_id=self.a['artifact_id'], locator=deepcopy(locator), details=details))

    def check_hash(self, value, digest):
        _digest(digest)
        if _hash(value) != digest:
            self.fail(self.phase, 'Canonical JSON hash differs from supplied content')

    def prepare(self):
        self.phase = 'unsupported_config'
        _keys(self.c, 'profile_id profile_version profile_selection allowed_input_roots '
              'expected_artifact_sha256 query_selector canonical_query_sequence '
              'canonical_query_sequence_sha256 query_gap_policy lowercase_x_policy '
              'unknown_tokens unknown_policy', 'metrics_enabled metric_policy binding_enabled')
        for k, v in dict(profile_id=_PROFILE, profile_version='1.0',
                         profile_selection='explicit_only',
                         query_gap_policy='preserve_and_map_to_null').items():
            if self.c[k] != v:
                self.fail('profile_mismatch', 'Explicit named version-1 profile required')
        if _hash(self.c['lowercase_x_policy']) != _hash(LOWERCASE_X_POLICY):
            raise ValueError('Explicit fixed lowercase_x_policy required')
        if (self.c['unknown_tokens'], self.c['unknown_policy']) not in (
                ([], 'reject'), (['X'], 'retain_as_unknown')):
            raise ValueError('Only []/reject or [X]/retain_as_unknown is supported')
        self.metrics_enabled = self.c.get('metrics_enabled', False)
        self.binding_enabled = self.c.get('binding_enabled', False)
        if type(self.metrics_enabled) is not bool or type(self.binding_enabled) is not bool:
            raise ValueError('Execution gates must be booleans')
        self.policy = self.c.get('metric_policy')
        if self.metrics_enabled:
            self.prepare_metrics()
        elif self.policy is not None:
            raise ValueError('metric_policy supplied while metrics are disabled')
        if not self.binding_enabled and self.b is not None:
            raise ValueError('binding supplied while binding is disabled')
        if self.binding_enabled and self.b is None:
            self.fail('query_binding_unresolved', 'Complete explicit binding required')
        self.phase = 'invalid_contract'
        _keys(self.a, 'artifact_id path sha256 format source_kind source_kind_status producer provenance')
        _text(self.a['artifact_id'])
        _digest(self.a['sha256']); _digest(self.c['expected_artifact_sha256'])
        if self.a['sha256'] != self.c['expected_artifact_sha256']:
            self.fail('artifact_hash_mismatch', 'Artifact and config hashes disagree')
        if (self.a['format'] != 'a3m' or self.a['source_kind'] != _SOURCE
                or self.a['source_kind_status'] != 'caller_supplied_not_verified'):
            self.fail('unsupported_format', 'Explicit A3M source-kind declaration required')
        producer = self.a['producer']
        fields = 'name version database database_version search_settings'
        _keys(producer, fields+' missing_reasons')
        missing = [k for k in fields.split() if producer[k] is None]
        _keys(producer['missing_reasons'], ' '.join(missing))
        for k in fields.split():
            if k in missing:
                _text(producer['missing_reasons'][k])
            elif k == 'search_settings':
                if type(producer[k]) is not dict or not producer[k]:
                    raise ValueError('Nonempty search_settings object or null required')
            else:
                _text(producer[k])
        if missing:
            self.note('incomplete_provenance', 'Unknown producer fields retained', details={'fields': missing})
        prov = self.a['provenance']
        _keys(prov, 'details missing_reason')
        if prov['details'] is None:
            _text(prov['missing_reason'])
            self.note('incomplete_provenance', prov['missing_reason'], locator={'field': 'provenance'})
        elif type(prov['details']) is not dict or not prov['details'] or prov['missing_reason'] is not None:
            raise ValueError('Provenance requires details or null with reason')
        self.phase = 'query_mismatch'
        self.qseq = self.c['canonical_query_sequence']
        if type(self.qseq) is not str or not self.qseq or any(t not in _AA for t in self.qseq):
            raise ValueError('Canonical query must be nonempty uppercase AA20')
        _digest(self.c['canonical_query_sequence_sha256'])
        if _sha(self.qseq.encode('ascii')) != self.c['canonical_query_sequence_sha256']:
            raise ValueError('Canonical query sequence hash mismatch')
        self.phase = 'unsafe_artifact_path'
        roots = self.c['allowed_input_roots']
        if type(roots) is not list or not roots:
            raise ValueError('Nonempty allowed_input_roots required')
        self.roots = [_path(x) for x in roots]
        if len(set(self.roots)) != len(roots) or any(not r.is_dir() for r in self.roots):
            raise ValueError('Unique existing canonical directories required')
        self.path = self.verify_path()

    def prepare_metrics(self):
        p = self.policy
        _keys(p, 'include_query_in_statistics sequence_duplicate_key duplicate_policy representative_selection '
              'gap_denominator unknown_denominator frequency_denominator entropy_alphabet entropy_log_base '
              'entropy_gap_policy entropy_unknown_policy entropy_pseudocount coverage_token_policy '
              'coverage_denominator coverage_aggregation')
        fixed = dict(representative_selection='first_eligible_occurrence_in_file_order',
            frequency_denominator='valid_amino_acids', entropy_alphabet=_AA,
            entropy_gap_policy='exclude', entropy_unknown_policy='exclude', entropy_pseudocount=0,
            coverage_token_policy='valid_amino_acids', coverage_denominator='canonical_query_length',
            coverage_aggregation='any_contributing_row')
        if _hash({k: p[k] for k in fixed}) != _hash(fixed):
            raise ValueError('Unsupported fixed metric policy')
        if type(p['include_query_in_statistics']) is not bool:
            raise ValueError('Explicit boolean query inclusion required')
        for k, values in [('sequence_duplicate_key', ('raw_sequence_tokens', 'parsed_match_tokens')),
                          ('duplicate_policy', ('keep', 'count_once', 'error')),
                          ('gap_denominator', ('all_observations', 'non_unknown')),
                          ('unknown_denominator', ('all_observations', 'non_gap'))]:
            if p[k] not in values:
                raise ValueError('Unsupported '+k)
        if not (type(p['entropy_log_base']) is int and p['entropy_log_base'] == 2
                or p['entropy_log_base'] == 'e'):
            raise ValueError('Entropy log base must be integer 2 or string e')

    def verify_path(self):
        self.phase, self.locator = 'unsafe_artifact_path', None
        p = _path(self.a['path'])
        if not any(p.is_relative_to(r) for r in self.roots):
            raise ValueError('Artifact outside allowed roots')
        if p.suffix != '.a3m':
            self.fail('unsupported_format', 'Only the explicit uncompressed .a3m suffix is supported')
        self.phase = 'artifact_read_error'
        if not stat.S_ISREG(p.stat().st_mode):
            raise ValueError('Regular artifact file required')
        return p

    def read(self):
        raw = self.path.read_bytes()
        if _sha(raw) != self.a['sha256']:
            self.fail('artifact_hash_mismatch', 'Raw bytes do not match expected SHA-256')
        self.phase = 'alignment_parse_error'
        raw.decode('utf-8')  # Fail before interpreting any invalid UTF-8.
        if raw.startswith(b'\xef\xbb\xbf'):
            raise ValueError('BOM is unsupported')
        self.raw, self.rows, self.preamble = raw, [], None
        parts = raw.split(b'\n')
        fragments = [p+b'\n' for p in parts[:-1]] + ([parts[-1]] if parts[-1] else [])
        offset = 0
        for line_no, fragment in enumerate(fragments, 1):
            ending = 'CRLF' if fragment.endswith(b'\r\n') else 'LF' if fragment.endswith(b'\n') else 'none'
            body = fragment[:-2] if ending == 'CRLF' else fragment[:-1] if ending == 'LF' else fragment
            text = body.decode('utf-8')
            self.locator = dict(source_line=line_no, artifact_byte_offset=offset)
            if not text or any(not c.isprintable() and c != '\t' for c in text):
                raise ValueError('Blank lines and unsupported controls are forbidden')
            info = dict(source_line=line_no, artifact_byte_offset=offset, line_ending=ending,
                        text=fragment.decode('utf-8'), raw_fragment_bytes_base64=base64.b64encode(fragment).decode('ascii'))
            if text.startswith('#'):
                if line_no != 1:
                    self.fail('preamble_profile_mismatch', 'Only one leading opaque preamble is supported')
                self.preamble = dict(info, kind='opaque_producer_metadata',
                    escaped_fragment=json.dumps(info['text'], ensure_ascii=True)[1:-1],
                    text_without_line_ending=text,
                    parse_result=dict(recognized_as='single_leading_hash_preamble', semantic_fields=None))
                self.note('opaque_preamble_retained', 'Preamble preserved without interpretation',
                          'info', self.locator)
            elif text.startswith('>'):
                if not re.fullmatch(r'>[^\s>]+(?:[ \t][^\r\n]*)?', text):
                    raise ValueError('Header requires > immediately followed by a record ID')
                index = len(self.rows)
                self.rows.append(dict(record_index=index, header_line=line_no,
                    record_occurrence_id=f'record:{index}@header_line:{line_no}',
                    raw_record_id=re.split('[ \t]', text[1:], maxsplit=1)[0], raw_header=text,
                    raw_header_bytes_base64=base64.b64encode(body).decode('ascii'),
                    raw_header_fragment_bytes_base64=info['raw_fragment_bytes_base64'],
                    header_fragment=info, sequence_fragments=[], raw_sequence_tokens='',
                    parsed_match_tokens='', tokens=[]))
            else:
                if not self.rows:
                    raise ValueError('Sequence content before any header')
                self.rows[-1]['sequence_fragments'].append(info)
                self.rows[-1]['raw_sequence_tokens'] += text
            offset += len(fragment)
        if not self.rows:
            raise ValueError('No records')
        for row in self.rows:
            self.locator = self.row_locator(row)
            if not row['raw_sequence_tokens']:
                raise ValueError('Empty sequence record')

    @staticmethod
    def row_locator(row):
        return dict(record_index=row['record_index'], record_occurrence_id=row['record_occurrence_id'],
                    raw_record_id=row['raw_record_id'], header_line=row['header_line'],
                    sequence_line_range=[row['sequence_fragments'][0]['source_line'],
                        row['sequence_fragments'][-1]['source_line']] if row['sequence_fragments'] else None)

    def select_query(self):
        self.phase, self.locator = 'invalid_query_selector', None
        selector = self.c['query_selector']
        candidates = [self.row_locator(r) for r in self.rows
            if all(t in _AA+'-' for t in r['raw_sequence_tokens'])
            and r['raw_sequence_tokens'].replace('-', '') == self.qseq]
        self.candidates = candidates
        if selector is None:
            code = 'ambiguous_query_occurrence' if len(candidates) > 1 else 'invalid_query_selector'
            self.fail(code, 'Explicit query occurrence selector required; no automatic selection',
                      dict(candidates=candidates, reason='selector_required',
                           binding_status='unresolved_ambiguous_query_occurrence' if len(candidates) > 1
                           else 'unresolved_query_selector'))
        if type(selector) is not dict:
            raise ValueError('Selector must be an explicit object')
        if set(selector) == {'record_occurrence_id'}:
            oid = selector['record_occurrence_id']
            if type(oid) is not str:
                self.fail('malformed_occurrence_identity', 'Occurrence identity must be a string')
            match = re.fullmatch(r'record:(0|[1-9][0-9]*)@header_line:([1-9][0-9]*)', oid)
            if not match:
                self.fail('malformed_occurrence_identity', 'Malformed occurrence identity')
            index, line = map(int, match.groups())
            self.locator = dict(record_index=index, header_line=line, record_occurrence_id=oid)
            if index >= len(self.rows) or self.rows[index]['header_line'] != line:
                self.fail('malformed_occurrence_identity', 'Occurrence index/header line do not match')
            query = self.rows[index]
        elif set(selector) == {'header_line', 'raw_header'}:
            _integer(selector['header_line'], 1); _text(selector['raw_header'])
            self.locator = dict(header_line=selector['header_line'])
            matches = [r for r in self.rows if r['header_line'] == selector['header_line']]
            if len(matches) != 1:
                raise ValueError('Selector does not address a header')
            query = matches[0]
            self.locator = self.row_locator(query)
            if query['raw_header'] != selector['raw_header']:
                raise ValueError('Exact raw header mismatch')
        else:
            raise ValueError('Choose occurrence ID OR header_line plus exact raw_header')
        self.query = query

    def tokenize(self):
        self.phase = 'unsupported_token'
        lower_x, upper_x = [], []
        transform_counts = Counter()
        for row in self.rows:
            row['is_query'] = row is self.query
            parsed = []
            raw_index = 0
            for fragment in row['sequence_fragments']:
                text = fragment['text']
                body = text[:-2] if fragment['line_ending'] == 'CRLF' else text[:-1] if fragment['line_ending'] == 'LF' else text
                byte_offset = fragment['artifact_byte_offset']
                for char_no, token in enumerate(body, 1):
                    self.locator = dict(self.row_locator(row), source_line=fragment['source_line'],
                        source_character=char_no, raw_token_index=raw_index, artifact_byte_offset=byte_offset)
                    if row['is_query'] and token not in _AA+'-':
                        self.fail('invalid_query_token', 'Selected query permits only uppercase AA20 and gaps')
                    if token in _AA:
                        kind, action, reason = 'amino_acid', 'preserve_match_token', None
                    elif token == '-':
                        kind, action, reason = 'gap', 'preserve_match_token', None
                    elif token == 'X':
                        if self.c['unknown_policy'] != 'retain_as_unknown':
                            self.fail('uppercase_unknown_without_policy', 'Uppercase X requires explicit retain policy')
                        kind, action, reason = 'uppercase_unknown', 'preserve_unknown_match_token', None
                        upper_x.append(dict(self.locator))
                    elif token in _AA.lower():
                        kind, action, reason = 'standard_insertion', 'retain_outside_match_projection', 'standard_AA_insertion'
                    elif token == '.':
                        kind, action, reason = 'insertion_padding', 'retain_outside_match_projection', 'insertion_padding'
                    elif token == 'x':
                        kind, action, reason = 'unknown_lowercase_insertion', 'retain_unknown_insertion_outside_match_projection', 'outside_standard_AA_insertion_alphabet'
                        lower_x.append(dict(self.locator, insertion_anchor=len(parsed)))
                    else:
                        self.fail('unsupported_token', 'Token outside explicit profile alphabet', {'token': token})
                    column_token = token in _AA+'-X'
                    row['tokens'].append(MatchProjectionToken(**self.locator, raw_token=token, token_class=kind,
                        parsed_column=len(parsed) if column_token else None,
                        query_sequence_position=None, insertion_anchor=None if column_token else len(parsed),
                        transformation_type=action, reason=reason))
                    if column_token:
                        parsed.append(token)
                    else:
                        transform_counts[kind] += 1
                    raw_index += 1
                    byte_offset += len(token.encode('utf-8'))
            row['parsed_match_tokens'] = ''.join(parsed)
            row['raw_sequence_sha256'] = _sha(row['raw_sequence_tokens'].encode('utf-8'))
            row['parsed_sequence_sha256'] = _sha(row['parsed_match_tokens'].encode('ascii'))
        self.phase, self.locator = 'query_mismatch', self.row_locator(self.query)
        if self.query['parsed_match_tokens'].replace('-', '') != self.qseq:
            raise ValueError('Selected query does not exactly match canonical sequence')
        width = len(self.query['parsed_match_tokens'])
        for row in self.rows:
            self.locator = self.row_locator(row)
            if len(row['parsed_match_tokens']) != width:
                self.fail('ragged_rows', 'All parsed match-column widths must equal selected query width',
                          dict(expected_width=width, observed_width=len(row['parsed_match_tokens'])))
        self.alignment_width = width
        self.note('match_projection_only',
                  'parsed_column is an A3M projection index, not a canonical sequence or residue position; '
                  'query_sequence_position remains null and no maps are generated', 'info')
        self.unknown = dict(lowercase_x=dict(count=len(lower_x),
            affected_occurrences=len({x['record_occurrence_id'] for x in lower_x}), locators=lower_x),
            uppercase_X=dict(count=len(upper_x),
            affected_occurrences=len({x['record_occurrence_id'] for x in upper_x}), locators=upper_x))
        self.transforms = {k: transform_counts[k] for k in ('standard_insertion', 'insertion_padding', 'unknown_lowercase_insertion')}
        if lower_x:
            self.note('unknown_lowercase_insertion', 'Lowercase x retained outside match statistics',
                      details=self.unknown['lowercase_x'])
        if upper_x:
            self.note('uppercase_unknown_retained', 'Uppercase X retained under explicit policy',
                      'info', details=self.unknown['uppercase_X'])

    def bind(self):
        if not self.binding_enabled:
            return None
        self.phase, self.locator = 'query_binding_unresolved', self.row_locator(self.query)
        b = self.b
        _keys(b, 'binding_id artifact_id artifact_sha256 record_occurrence_id canonical_query_sequence_sha256 '
              'target_id role model_id chain_id segment column_map column_map_sha256 sequence_map '
              'sequence_map_sha256 residue_map residue_map_sha256 map_source')
        for k in ('binding_id', 'target_id', 'model_id'):
            _text(b[k])
        if (b['artifact_id'] != self.a['artifact_id'] or b['artifact_sha256'] != self.a['sha256']
                or b['record_occurrence_id'] != self.query['record_occurrence_id']
                or b['canonical_query_sequence_sha256'] != self.c['canonical_query_sequence_sha256']):
            raise ValueError('Binding must attest artifact, selected occurrence and canonical sequence hash')
        if b['role'] != 'receptor' or type(b['chain_id']) is not str:
            raise ValueError('Explicit receptor chain required')
        _integer(b['segment'])
        for name in ('column_map', 'sequence_map', 'residue_map'):
            self.check_hash(b[name], b[name+'_sha256'])
        columns = b['column_map']
        if type(columns) is not list or len(columns) != self.alignment_width:
            raise ValueError('Complete caller-supplied column map required')
        # Validate supplied entries against query tokens without constructing a map.
        pos = 0
        for j, (token, entry) in enumerate(zip(self.query['parsed_match_tokens'], columns)):
            _keys(entry, 'query_column sequence_position reason')
            _integer(entry['query_column'])
            if entry['query_column'] != j:
                raise ValueError('Caller column map must be ordered and complete')
            if token == '-':
                if entry['sequence_position'] is not None or entry['reason'] != 'query_gap':
                    raise ValueError('Query gap requires null caller sequence position')
            else:
                pos += 1
                _integer(entry['sequence_position'], 1)
                if entry['sequence_position'] != pos or entry['reason'] is not None:
                    raise ValueError('Caller column map must match canonical query positions')
        source = b['map_source']
        _keys(source, 'artifact_id sha256 source_run_id model_id')
        for k in ('artifact_id', 'source_run_id', 'model_id'):
            _text(source[k])
        _digest(source['sha256'])
        if source['model_id'] != b['model_id']:
            raise ValueError('Map source model mismatch')
        rows = b['residue_map']
        if type(rows) is not list or not rows:
            raise ValueError('Nonempty canonical residue map required')
        identities = set()
        for i, row in enumerate(rows):
            self.locator = dict(self.row_locator(self.query), residue_index=i)
            _keys(row, 'residue_index model_id chain_id segment record_group residue_id insertion_code '
                  'residue_name label_chain_id label_seq_id source_lines atom_names selected_altloc '
                  'missing_backbone_atoms warnings')
            _integer(row['residue_index']); _integer(row['segment'])
            if row['residue_index'] != i or row['model_id'] != b['model_id'] or type(row['residue_id']) is not int:
                raise ValueError('Canonical index/model/author identity mismatch')
            for k in ('chain_id', 'insertion_code', 'residue_name'):
                if type(row[k]) is not str:
                    raise ValueError('Canonical string identity required')
            _text(row['residue_name'])
            if row['record_group'] not in ('ATOM', 'HETATM') or row['selected_altloc'] != 'A':
                raise ValueError('Canonical default-altloc-A map required')
            if row['label_chain_id'] is not None and type(row['label_chain_id']) is not str:
                raise ValueError('Invalid label chain ID')
            if row['label_seq_id'] is not None and type(row['label_seq_id']) is not int:
                raise ValueError('Invalid label sequence ID')
            if type(row['source_lines']) is not list or not row['source_lines']:
                raise ValueError('Canonical physical source lines required')
            for line in row['source_lines']:
                _integer(line, 1)
            for k in ('atom_names', 'missing_backbone_atoms', 'warnings'):
                if type(row[k]) is not list or any(type(x) is not str or not x for x in row[k]):
                    raise ValueError('Canonical '+k+' list required')
            identity = tuple(row[k] for k in ('model_id', 'chain_id', 'segment', 'record_group', 'residue_id', 'insertion_code'))
            if identity in identities:
                raise ValueError('Duplicate canonical residue identity')
            identities.add(identity)
        entries = b['sequence_map']
        if type(entries) is not list or len(entries) != len(self.qseq):
            raise ValueError('Complete sequence map required')
        positions, used = set(), set()
        for e in entries:
            _keys(e, 'sequence_position residue_index reason')
            pos, idx = e['sequence_position'], e['residue_index']
            self.locator = dict(self.row_locator(self.query), sequence_position=pos, residue_index=idx)
            _integer(pos, 1); _integer(idx)
            if pos > len(self.qseq) or pos in positions or idx >= len(rows) or idx in used or e['reason'] is not None:
                raise ValueError('Every position requires a distinct mapped residue without missing reason')
            positions.add(pos); used.add(idx)
            r = rows[idx]
            if ((r['chain_id'], r['segment']) != (b['chain_id'], b['segment'])
                    or r['record_group'] != 'ATOM' or AA.get(r['residue_name']) != self.qseq[pos-1]):
                raise ValueError('Mapped residue must match chain/segment and canonical AA20 sequence')
        return dict(status='supplied_map_consistency_verified', verified=True,
                    structural_source_bytes_verified=False, mapped_positions=len(entries),
                    position_bases=dict(query_column=0, sequence_position=1, residue_index=0), snapshot=b)

    def counts(self, tokens, column=False):
        c = Counter(tokens)
        n, gap, unknown = sum(c.values()), c['-'], c['X']
        valid = sum(c[x] for x in _AA)
        reason = ('no_contributing_rows' if not n else 'all_gap' if gap == n else
                  'no_valid_amino_acids' if not valid else None) if column else None
        p = self.policy
        result = dict(observation_count=n, valid_amino_acid_count=valid, gap_count=gap,
            unknown_count=unknown, unknown_token_counts={'X': unknown},
            gap_fraction=_fraction(gap, n if p['gap_denominator'] == 'all_observations' else n-unknown, reason),
            unknown_fraction=_fraction(unknown, n if p['unknown_denominator'] == 'all_observations' else n-gap, reason))
        if column:
            frequencies = {x: c[x]/valid for x in _AA} if valid else None
            entropy = None
            if frequencies is not None:
                log = math.log2 if p['entropy_log_base'] == 2 else math.log
                entropy = -sum(f*log(f) for f in frequencies.values() if f)
                if entropy == 0:
                    entropy = 0.0
            result.update(amino_acid_counts={x: c[x] for x in _AA},
                amino_acid_frequencies=dict(value=frequencies, reason=reason, denominator=valid),
                shannon_entropy=dict(value=entropy, reason=reason, log_base=p['entropy_log_base']))
        return result

    def metrics(self):
        if not self.metrics_enabled:
            return None
        self.phase, self.locator = 'statistics_error', None
        key = self.policy['sequence_duplicate_key']
        groups = {}
        for row in self.rows:
            groups.setdefault(row[key], []).append(row)
        if self.policy['duplicate_policy'] == 'error' and any(len(g) > 1 for g in groups.values()):
            self.fail('sequence_duplicate_policy_violation', 'Input duplicates under the explicit sequence key')
        contributing, contributions = [], []
        representatives = {}
        for row in self.rows:
            reason = None
            representative = None
            if row['is_query'] and not self.policy['include_query_in_statistics']:
                reason = 'query_excluded'
            elif self.policy['duplicate_policy'] == 'count_once' and row[key] in representatives:
                reason = 'duplicate_counted_once'
                representative = representatives[row[key]]
            else:
                contributing.append(row)
                representatives.setdefault(row[key], row['record_occurrence_id'])
                representative = row['record_occurrence_id']
            contributions.append(dict(record_occurrence_id=row['record_occurrence_id'],
                contributes=reason is None, reason=reason, representative_occurrence_id=representative))
        qcols = [j for j, token in enumerate(self.query['parsed_match_tokens']) if token != '-']
        coverage = sum(any(r['parsed_match_tokens'][j] in _AA for r in contributing) for j in qcols)
        columns = []
        for j in range(self.alignment_width):
            m = self.counts((r['parsed_match_tokens'][j] for r in contributing), column=True)
            columns.append(dict(parsed_column=j, metrics=m))
            if m['shannon_entropy']['reason']:
                self.note('unavailable_column_metrics', m['shannon_entropy']['reason'], locator=dict(parsed_column=j))
        return dict(policy=deepcopy(self.policy), statistical_contributions=contributions,
            summary=dict(input_depth=len(self.rows), statistics_occurrence_count=len(contributing),
                query_coverage=_fraction(coverage, len(self.qseq), None if contributing else 'no_contributing_rows'),
                **self.counts(t for r in contributing for t in r['parsed_match_tokens'])),
            row_coverage=[dict(record_occurrence_id=r['record_occurrence_id'],
                query_coverage=_fraction(sum(r['parsed_match_tokens'][j] in _AA for j in qcols), len(self.qseq)))
                for r in self.rows], columns=columns)

    def run(self):
        self.prepare()
        self.read()
        self.select_query()
        self.tokenize()
        ids = _groups(self.rows, 'raw_record_id', headers=True)
        parsed = _groups(self.rows, 'parsed_match_tokens')
        rawseq = _groups(self.rows, 'raw_sequence_tokens')
        if ids['duplicate_groups']:
            self.note('raw_id_duplicate', 'Raw ID duplicates retained as separate occurrences', details=ids)
        binding_result = self.bind() if self.binding_enabled else None
        metric_result = self.metrics() if self.metrics_enabled else None
        self.phase, self.locator = 'result_validation_error', None
        result_type = ColabFoldA3MResult if self.binding_enabled or self.metrics_enabled else ColabFoldA3MReaderResult
        result = result_type(dict(status='parsed',
            artifact=dict(snapshot=self.a, raw_sha256=self.a['sha256'], size_bytes=len(self.raw),
                          raw_bytes_base64=base64.b64encode(self.raw).decode('ascii')),
            profile=dict(profile_id=_PROFILE, profile_version='1.0', profile_selection='explicit_only'),
            position_bases=dict(_BASES), raw_preamble=self.preamble, records=self.rows,
            occurrence_mapping=[self.row_locator(r) for r in self.rows],
            query=ReaderQueryInventory(requested_selector=self.c['query_selector'], status='explicit_occurrence_verified',
                selected_occurrence=self.query['record_occurrence_id'], candidates=self.candidates,
                canonical_sequence=self.qseq, canonical_sequence_sha256=self.c['canonical_query_sequence_sha256']),
            inventory=dict(input_depth=len(self.rows), alignment_width=self.alignment_width,
                raw_id_duplicate_groups=ids['duplicate_groups'],
                raw_id_duplicate_occurrences=ids['duplicate_occurrences'],
                raw_id_duplicate_member_count=ids['duplicate_member_count'],
                exact_parsed_sequence_duplicate_groups=parsed['duplicate_groups'],
                exact_parsed_sequence_duplicate_occurrences=parsed['duplicate_occurrences'],
                exact_parsed_sequence_duplicate_member_count=parsed['duplicate_member_count']),
            raw_id_duplicate_summary=ids, sequence_duplicate_summary=dict(raw=rawseq, parsed=parsed),
            unknown_token_summary=self.unknown, insertion_transform_summary=self.transforms,
            metric_policy_snapshot=deepcopy(self.policy), metrics=metric_result,
            metrics_status='completed' if self.metrics_enabled else 'disabled', binding=binding_result,
            binding_status='completed' if self.binding_enabled else 'disabled',
            provenance_snapshot=dict(producer=self.a['producer'], provenance=self.a['provenance'],
                source_kind=self.a['source_kind'], source_kind_status=self.a['source_kind_status']),
            configuration=deepcopy(self.c),
            effective_execution_gates=dict(metrics_enabled=self.metrics_enabled, binding_enabled=self.binding_enabled),
            contract_hashes=dict(artifact=_hash(self.a), config=_hash(self.c),
                                 binding=_hash(self.b) if self.binding_enabled else None),
            diagnostics=self.diagnostics, limitations=list(_LIMITATIONS)))
        rebuilt = result.reconstruct_bytes()
        if rebuilt != self.raw:
            self.fail('lossless_reconstruction_failure', 'Fragments do not reconstruct input bytes')
        result.data['reconstructed_sha256'] = _sha(rebuilt)
        result.to_dict()
        path = self.verify_path()
        if _sha(path.read_bytes()) != self.a['sha256']:
            self.fail('artifact_hash_mismatch', 'Artifact changed before returning result')
        return result


def parse_colabfold_a3m(*, artifact, config, binding=None):
    """Parse only the explicitly selected new profile; gates default to disabled.

    No files are written. Expected failures carry diagnostics and no partial result.
    No legacy adapter is called, registered, patched, aliased or used as fallback.
    """
    worker = None
    try:
        for value in (artifact, config, binding):
            _plain(value)
        if type(artifact) is not dict or type(config) is not dict or binding is not None and type(binding) is not dict:
            raise ValueError('Artifact/config/binding must be plain objects (binding may be null)')
        worker = _Reader(artifact, config, binding)
        return worker.run()
    except ColabFoldA3MError:
        raise
    except (ValueError, TypeError, KeyError, IndexError, OSError, AttributeError, RecursionError, OverflowError) as exc:
        raise ColabFoldA3MError(worker.phase if worker else 'invalid_contract', str(exc),
            artifact_id=worker.a.get('artifact_id') if worker else None,
            locator=worker.locator if worker else None) from exc
