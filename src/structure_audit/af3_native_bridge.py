"""Read-only AF3 native atom-site profile; standalone Python 3.10+ notebook cell.

Not a strict Structure reader or a CIF converter. Returns only present atom-site
fields, with explicit CIF namespaces and raw values. Does not infer author atom
names, author component names, segments, sequences or receptor correspondence.
Profile selection asserts a format contract, not proof of the producing software.
"""
from dataclasses import asdict, dataclass
import hashlib
import math
from pathlib import Path
import re
import stat

AF3_NATIVE_PROFILE = "af3_native_v1"
AF3_NATIVE_READER_VERSION = "0.1"


class AF3NativeFormatError(ValueError):
    """Unsupported/ambiguous native input; never yields a partial result."""


@dataclass(frozen=True)
class AF3NativeAtomRow:
    # Keys are actual, present CIF tags (case-normalized), never generic aliases.
    fields: dict
    source_lines: tuple
    quoted_fields: tuple


@dataclass(frozen=True)
class AF3NativeCIF:
    source_path: str
    source_sha256: str
    selected_model: str
    available_models: tuple
    columns: tuple               # Original header spelling/order.
    rows: tuple                  # Selected-model rows, including HETATM.

    def provenance(self):
        return {"profile": AF3_NATIVE_PROFILE, "reader": "read_af3_native_cif",
                "reader_version": AF3_NATIVE_READER_VERSION,
                "source_path": self.source_path, "source_sha256": self.source_sha256,
                "selected_model": self.selected_model,
                "available_models": list(self.available_models),
                "columns": list(self.columns),
                "absent_fields": ["_atom_site.auth_atom_id", "_atom_site.auth_comp_id"],
                "field_policy": "present_cif_fields_only; no_namespace_substitution",
                "producer_verified": False}

    def to_dict(self):
        return {**asdict(self), "provenance": self.provenance()}


def _native_tokens(text):
    """Small CIF 1.1 lexer, independent of the unchanged strict reader."""
    lines = text.splitlines()
    if lines and lines[0].startswith("#\\#CIF_2.0"):
        raise AF3NativeFormatError("CIF 2.0 unsupported")
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith(";"):
            start, parts = i + 1, [line[1:]]
            i += 1
            while i < len(lines) and not lines[i].startswith(";"):
                parts.append(lines[i])
                i += 1
            if i == len(lines) or lines[i][1:].strip():
                raise AF3NativeFormatError("Unterminated/ambiguous CIF text field")
            yield ("\n".join(parts), start, True)
        else:
            j = 0
            while j < len(line):
                if line[j].isspace():
                    j += 1
                    continue
                if line[j] == "#":
                    break
                if line[j] in "\"'":
                    quote, start = line[j], j + 1
                    j += 1
                    while j < len(line) and not (line[j] == quote and
                                                (j + 1 == len(line) or line[j+1].isspace())):
                        j += 1
                    if j == len(line):
                        raise AF3NativeFormatError(f"Unterminated quote at line {i+1}")
                    yield (line[start:j], i + 1, True)
                    j += 1
                else:
                    start = j
                    while j < len(line) and not line[j].isspace():
                        j += 1
                    value = line[start:j]
                    if value.startswith(("[", "]", "{", "}", "$")):
                        raise AF3NativeFormatError("Unsupported CIF token")
                    yield (value, i + 1, False)
        i += 1


def _native_control(token):
    value, _, quoted = token
    low = value.lower()
    return not quoted and (low.startswith(("_", "data_", "save_")) or
                           low in ("loop_", "stop_", "global_"))


def _native_table(text):
    tokens = list(_native_tokens(text))
    i, blocks, tables, seen_tags = 0, 0, [], set()
    while i < len(tokens):
        value, _, quoted = tokens[i]
        low = value.lower()
        if not quoted and low.startswith("data_"):
            blocks += 1
            if blocks != 1 or len(value) == 5:
                raise AF3NativeFormatError("Exactly one named data block required")
            i += 1
        elif blocks == 0:
            raise AF3NativeFormatError("CIF must start with a data block")
        elif not quoted and low == "loop_":
            i += 1
            columns = []
            while i < len(tokens) and not tokens[i][2] and tokens[i][0].startswith("_"):
                columns.append(tokens[i][0])
                i += 1
            keys = [c.lower() for c in columns]
            if not keys or len(set(keys)) != len(keys) or seen_tags.intersection(keys):
                raise AF3NativeFormatError("Empty/duplicate CIF headers")
            seen_tags.update(keys)
            values = []
            while i < len(tokens) and not _native_control(tokens[i]):
                values.append(tokens[i])
                i += 1
            if not values or len(values) % len(keys):
                raise AF3NativeFormatError("Empty loop or CIF row width mismatch")
            if any(k.startswith("_atom_site.") for k in keys):
                if not all(k.startswith("_atom_site.") for k in keys):
                    raise AF3NativeFormatError("Mixed atom-site category")
                tables.append((columns, keys, values))
        elif not quoted and low.startswith("_"):
            if low.startswith("_atom_site.") or low in seen_tags:
                raise AF3NativeFormatError("Scalar atom-site or duplicate tag unsupported")
            if i + 1 == len(tokens) or _native_control(tokens[i+1]):
                raise AF3NativeFormatError("Missing scalar value")
            seen_tags.add(low)
            i += 2
        else:
            raise AF3NativeFormatError(f"Unsupported CIF syntax: {value!r}")
    if len(tables) != 1:
        raise AF3NativeFormatError("Exactly one atom-site loop required")
    return tables[0]


def read_af3_native_cif(path, *, model_id):
    """Explicit model required; no default model or implicit strict-reader fallback.

    v1 requires BOTH auth_atom_id and auth_comp_id to be absent. All input rows
    are validated before selecting a model. Nontrivial altlocs, chain aliases,
    conflicting observed residue identities and duplicate atoms fail closed.
    HETATM label_seq_id may be ./?; no label residue identity is invented for it.
    """
    if not isinstance(model_id, str) or not re.fullmatch(r"[1-9][0-9]*", model_id):
        raise AF3NativeFormatError("Explicit positive integer model ID string required")
    path = Path(path).absolute()
    if path.resolve() != path or path.suffix.lower() not in (".cif", ".mmcif"):
        raise AF3NativeFormatError("Canonical uncompressed CIF path required; no symlink aliases")
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise AF3NativeFormatError("Regular file required")
    data = path.read_bytes()
    columns, keys, values = _native_table(data.decode("utf-8"))
    required = ("id group_pdb type_symbol label_atom_id label_comp_id label_asym_id "
                "label_seq_id auth_asym_id auth_seq_id label_alt_id pdbx_pdb_ins_code "
                "pdbx_pdb_model_num cartn_x cartn_y cartn_z").split()
    missing = [k for k in required if "_atom_site." + k not in keys]
    if missing:
        raise AF3NativeFormatError("Missing explicit atom-site fields: " + ", ".join(missing))
    if any("_atom_site." + k in keys for k in ("auth_atom_id", "auth_comp_id")):
        raise AF3NativeFormatError("Native v1 requires absent author atom/component fields; select strict explicitly")
    rows, models, atom_ids, atom_keys = [], set(), set(), set()
    chain_forward, chain_reverse, residue_forward, residue_reverse, residues = {}, {}, {}, {}, {}

    def one_to_one(mapping, key, value, message):
        if key in mapping and mapping[key] != value:
            raise AF3NativeFormatError(message)
        mapping[key] = value

    for start in range(0, len(values), len(keys)):
        row = dict(zip(keys, values[start:start+len(keys)]))

        def get(key, nullable=False):
            value, _, quoted = row["_atom_site." + key]
            if not value or "\n" in value:
                raise AF3NativeFormatError(f"Empty/multiline identity: {key}")
            if value in (".", "?"):
                if quoted or not nullable:
                    raise AF3NativeFormatError(f"Unknown/quoted-placeholder field: {key}")
                return None
            return value

        model, group = get("pdbx_pdb_model_num"), get("group_pdb")
        if not re.fullmatch(r"[1-9][0-9]*", model) or group not in ("ATOM", "HETATM"):
            raise AF3NativeFormatError("Unsupported model ID or record group")
        models.add(model)
        atom_id = get("id")
        if atom_id in atom_ids:
            raise AF3NativeFormatError("Duplicate atom-site ID")
        atom_ids.add(atom_id)
        for axis in ("cartn_x", "cartn_y", "cartn_z"):
            try:
                finite = math.isfinite(float(get(axis)))
            except ValueError as exc:
                raise AF3NativeFormatError("Invalid coordinate token") from exc
            if not finite:
                raise AF3NativeFormatError("Nonfinite coordinate token")
        if get("label_alt_id", nullable=True) is not None:
            raise AF3NativeFormatError("Alternate locations require an explicit later policy")
        auth_chain, label_chain = get("auth_asym_id"), get("label_asym_id")
        auth_seq, label_seq = get("auth_seq_id"), get("label_seq_id", nullable=group == "HETATM")
        if not re.fullmatch(r"[+-]?[0-9]+", auth_seq):
            raise AF3NativeFormatError("Noninteger author residue ID")
        if label_seq is not None and not re.fullmatch(r"[1-9][0-9]*", label_seq):
            raise AF3NativeFormatError("Invalid label residue ID")
        ins = get("pdbx_pdb_ins_code", nullable=True)
        comp, atom = get("label_comp_id"), get("label_atom_id")
        get("type_symbol")
        one_to_one(chain_forward, (model, auth_chain), label_chain, "Author chain aliases multiple label chains")
        one_to_one(chain_reverse, (model, label_chain), auth_chain, "Label chain aliases multiple author chains")
        # Relationships already present within CIF rows, NOT sequence correspondence.
        auth_residue = (model, auth_chain, int(auth_seq), ins)
        descriptor = (group, label_chain, label_seq, comp, auth_seq)
        one_to_one(residues, auth_residue, descriptor, "Conflicting author residue identity")
        if label_seq is not None:
            label_residue = (model, label_chain, label_seq)
            one_to_one(residue_forward, auth_residue, label_residue, "Ambiguous author/label residue relation")
            one_to_one(residue_reverse, label_residue, auth_residue, "Ambiguous label/author residue relation")
        atom_key = (auth_residue, atom)
        if atom_key in atom_keys:
            raise AF3NativeFormatError("Duplicate atom identity")
        atom_keys.add(atom_key)
        if model == model_id:
            rows.append(AF3NativeAtomRow(
                {key: token[0] for key, token in row.items()},
                tuple(sorted({token[1] for token in row.values()})),
                tuple(key for key, token in row.items() if token[2])))
    if model_id not in models:
        raise AF3NativeFormatError(f"Selected model absent: {model_id}")
    after = path.stat()
    if (path.resolve() != path or any(getattr(before, k) != getattr(after, k) for k in
            ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")) or path.read_bytes() != data):
        raise AF3NativeFormatError("File changed while reading")
    return AF3NativeCIF(str(path), hashlib.sha256(data).hexdigest(), model_id,
                        tuple(sorted(models, key=int)), tuple(columns), tuple(rows))


# Explicit marker to prevent using this distinct API as a strict callback.
read_af3_native_cif.reader_profile = AF3_NATIVE_PROFILE
read_af3_native_cif.reader_version = AF3_NATIVE_READER_VERSION
