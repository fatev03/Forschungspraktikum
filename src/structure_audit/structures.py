"""Conservative PDB / PDBx-mmCIF atom-table reader.

Preserves raw atom rows. No coordinate repair, sequence generation, alignment,
model inference, network access, or silent parser fallback.
"""
from dataclasses import dataclass, field
from pathlib import Path
import re

from .provenance import hash_file


class StructureFormatError(ValueError):
    pass


class UnsupportedFormat(StructureFormatError):
    def __init__(self, message):
        super().__init__("unsupported / needs external dependency: " + message)


@dataclass(frozen=True)
class Atom:
    model_id: str
    chain_id: str
    residue_id: int
    insertion_code: str
    residue_name: str
    atom_name: str
    altloc: str
    element: str
    xyz: tuple
    occupancy: float | None
    group: str
    segment: int
    line: int
    label_chain_id: str | None = None
    label_seq_id: int | None = None

    @property
    def residue_key(self):
        return (self.model_id, self.chain_id, self.segment, self.group,
                self.residue_id, self.insertion_code)


@dataclass
class Residue:
    key: tuple
    name: str
    index: int
    atoms: list = field(default_factory=list)


@dataclass
class Structure:
    source: str
    source_hash: str
    format: str
    model_id: str
    atoms: list
    residues: list
    warnings: list


def _number(text, context, cast=float):
    try:
        return cast(text)
    except (ValueError, TypeError) as exc:
        raise StructureFormatError(f"{context}: invalid numeric value {text!r}") from exc


def _pdb(text):
    atoms, warnings = [], []
    model, segment, explicit, in_model = "1", 0, False, False
    seen_models = set()
    for line_no, line in enumerate(text.splitlines(), 1):
        rec = line[:6].strip()
        if rec == "MODEL":
            if in_model or (atoms and not explicit):
                raise UnsupportedFormat("mixed or nested PDB MODEL records")
            explicit, in_model = True, True
            model = str(_number(line[10:14].strip(), f"line {line_no} MODEL", int))
            if model in seen_models:
                raise UnsupportedFormat("duplicate PDB MODEL identifiers")
            seen_models.add(model)
            segment = 0
        elif rec == "ENDMDL":
            if not in_model:
                raise StructureFormatError("ENDMDL without MODEL")
            in_model = False
        elif rec == "TER":
            segment += 1
        elif rec in ("ATOM", "HETATM"):
            if explicit and not in_model:
                raise UnsupportedFormat("PDB atoms outside explicit MODEL block")
            if len(line) < 54:
                raise StructureFormatError(f"line {line_no}: truncated coordinate record")
            if not line[12:16].strip() or not line[17:20].strip():
                raise StructureFormatError(f"line {line_no}: missing atom/residue name")
            res_id = _number(line[22:26].strip(), f"line {line_no} residue ID", int)
            xyz = tuple(_number(line[start:start+8], f"line {line_no} coordinate")
                        for start in (30, 38, 46))
            occ = line[54:60].strip()
            element = line[76:78].strip().upper()
            atoms.append(Atom(model, line[21:22].strip(), res_id, line[26:27].strip(),
                              line[17:20].strip(), line[12:16].strip(), line[16:17].strip(),
                              element, xyz, _number(occ, f"line {line_no} occupancy") if occ else None,
                              rec, segment, line_no))
        elif rec == "REMARK" and line[7:10] in ("465", "470"):
            warnings.append({"code": "unparsed_missing_annotation", "line": line_no,
                             "message": "REMARK 465/470 retained as warning; supply explicit expected residue mapping."})
    if in_model:
        raise StructureFormatError("Unclosed MODEL block")
    return atoms, warnings


def _tokens(text):
    """CIF 1.1 tokens with quoted/control distinction and source line numbers."""
    lines = text.splitlines()
    if lines and lines[0].startswith("#\\#CIF_2.0"):
        raise UnsupportedFormat("CIF 2.0")
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith(";"):
            start, parts = i + 1, [line[1:]]
            i += 1
            while i < len(lines) and not lines[i].startswith(";"):
                parts.append(lines[i]); i += 1
            if i == len(lines) or lines[i][1:].strip():
                raise UnsupportedFormat("unterminated or ambiguous CIF text field")
            yield ("\n".join(parts), start, True)
        else:
            j = 0
            while j < len(line):
                if line[j].isspace():
                    j += 1; continue
                if line[j] == "#":
                    break
                if line[j] in "\"'":
                    quote, start = line[j], j + 1
                    j += 1
                    while j < len(line):
                        if line[j] == quote and (j + 1 == len(line) or line[j+1].isspace()):
                            break
                        j += 1
                    if j == len(line):
                        raise UnsupportedFormat(f"line {i+1}: unterminated CIF quote")
                    yield (line[start:j], i + 1, True)
                    j += 1
                else:
                    start = j
                    while j < len(line) and not line[j].isspace():
                        j += 1
                    value = line[start:j]
                    if value.startswith(("[", "]", "{", "}")):
                        raise UnsupportedFormat("CIF 2.0 collection syntax")
                    yield (value, i + 1, False)
        i += 1


def _control(token):
    value, _, quoted = token
    return not quoted and (value.startswith("_") or value.lower() in ("loop_", "stop_", "global_")
                           or value.lower().startswith(("data_", "save_")))


def _cif(text):
    tokens, tables, scalars = list(_tokens(text)), [], {}
    i, blocks = 0, 0
    while i < len(tokens):
        value, line, quoted = tokens[i]
        low = value.lower()
        if not quoted and low.startswith("data_"):
            blocks += 1; i += 1
            if blocks > 1:
                raise UnsupportedFormat("multiple CIF data blocks require explicit external parsing")
        elif blocks == 0:
            raise StructureFormatError("mmCIF must start with a data_ block")
        elif not quoted and low == "loop_":
            i += 1
            headers = []
            while i < len(tokens) and not tokens[i][2] and tokens[i][0].startswith("_"):
                headers.append(tokens[i][0].lower()); i += 1
            if not headers or len(headers) != len(set(headers)):
                raise StructureFormatError("Empty or duplicate CIF loop headers")
            values = []
            while i < len(tokens) and not _control(tokens[i]):
                values.append(tokens[i]); i += 1
            if len(values) % len(headers):
                raise StructureFormatError("CIF loop row width mismatch")
            if any(h.startswith("_atom_site.") for h in headers):
                if not all(h.startswith("_atom_site.") for h in headers):
                    raise UnsupportedFormat("mixed-category atom_site loop")
                tables.append((headers, values))
        elif not quoted and value.startswith("_"):
            if i+1 >= len(tokens) or _control(tokens[i+1]):
                raise StructureFormatError("Missing scalar CIF value")
            if low in scalars:
                raise StructureFormatError("Duplicate scalar CIF tag")
            scalars[low] = tokens[i+1]; i += 2
        else:
            raise UnsupportedFormat(f"line {line}: unexpected CIF syntax {value!r}")
    if len(tables) != 1 or any(k.startswith("_atom_site.") for k in scalars):
        raise UnsupportedFormat("exactly one atom_site loop is required")
    headers, values = tables[0]
    required = ["group_pdb", "auth_asym_id", "auth_seq_id", "auth_comp_id", "auth_atom_id",
                "label_asym_id", "label_seq_id", "label_comp_id", "label_atom_id", "label_alt_id",
                "pdbx_pdb_ins_code", "cartn_x", "cartn_y", "cartn_z", "type_symbol"]
    missing = [k for k in required if "_atom_site."+k not in headers]
    if missing:
        raise UnsupportedFormat("missing explicit atom_site fields: " + ", ".join(missing))
    atoms = []
    for start in range(0, len(values), len(headers)):
        row = dict(zip(headers, values[start:start+len(headers)]))
        line = values[start][1]
        def get(key, *, nullable=False, optional=False):
            token = row.get("_atom_site."+key)
            if token is None:
                if optional:
                    return None
                raise UnsupportedFormat(f"missing atom_site.{key}")
            val, _, quoted = token
            if val in (".", "?"):
                if quoted:
                    raise UnsupportedFormat(f"quoted placeholder in atom_site.{key}")
                if nullable:
                    return None
                raise UnsupportedFormat(f"unknown atom_site.{key}")
            if not val or "\n" in val:
                raise UnsupportedFormat(f"empty/multiline atom_site.{key}")
            return val
        group = get("group_pdb").upper()
        if group not in ("ATOM", "HETATM"):
            raise UnsupportedFormat(f"atom_site.group_PDB={group}")
        if get("auth_comp_id") != get("label_comp_id") or get("auth_atom_id") != get("label_atom_id"):
            raise UnsupportedFormat("different auth/label atom or component names")
        auth_id = get("auth_seq_id")
        if not re.fullmatch(r"[+-]?\d+", auth_id):
            raise UnsupportedFormat("non-integer auth_seq_id")
        label_id = get("label_seq_id", nullable=group == "HETATM")
        occ = get("occupancy", nullable=True, optional=True)
        model = get("pdbx_pdb_model_num", optional=True) or "1"  # absent field means one model
        atoms.append(Atom(model, get("auth_asym_id"), int(auth_id),
                          get("pdbx_pdb_ins_code", nullable=True) or "", get("auth_comp_id"),
                          get("auth_atom_id"), get("label_alt_id", nullable=True) or "",
                          get("type_symbol").upper(),
                          tuple(_number(get(k), f"line {line} {k}") for k in ("cartn_x", "cartn_y", "cartn_z")),
                          _number(occ, f"line {line} occupancy") if occ is not None else None,
                          group, 0, line, get("label_asym_id"),
                          _number(label_id, f"line {line} label_seq_id", int) if label_id is not None else None))
    # An author chain mapping to several label chains cannot be silently flattened.
    aliases, reverse_aliases = {}, {}
    for atom in atoms:
        aliases.setdefault((atom.model_id, atom.chain_id), set()).add(atom.label_chain_id)
        reverse_aliases.setdefault((atom.model_id, atom.label_chain_id), set()).add(atom.chain_id)
    if any(len(v) != 1 for v in aliases.values()):
        raise UnsupportedFormat("one author chain maps to multiple label chains")
    if any(len(v) != 1 for v in reverse_aliases.values()):
        raise UnsupportedFormat("one label chain maps to multiple author chains")
    return atoms, []


def read_structure(path, *, model_id=None):
    path = Path(path)
    fmt = path.suffix.lower()
    if fmt not in (".pdb", ".cif", ".mmcif"):
        raise UnsupportedFormat("expected uncompressed .pdb, .cif, or .mmcif")
    before = hash_file(path)
    text = path.read_text(encoding="utf-8")
    atoms, warnings = _pdb(text) if fmt == ".pdb" else _cif(text)
    if hash_file(path) != before:
        raise StructureFormatError("Input changed while being read")
    models = sorted({a.model_id for a in atoms})
    if not models:
        raise StructureFormatError("Structure has no atom records")
    if model_id is None:
        if len(models) > 1:
            raise UnsupportedFormat("multiple models: supply model_id explicitly")
        model_id = models[0]
    model_id = str(model_id)
    if model_id not in models:
        raise ValueError(f"Unknown model_id {model_id!r}; available: {models}")
    atoms = [a for a in atoms if a.model_id == model_id]
    if len(models) > 1:
        warnings.append({"code": "model_selection", "message": f"Selected {model_id} from {models}"})
    residues, seen, author_seen = [], set(), set()
    for atom in atoms:
        if not residues or residues[-1].key != atom.residue_key:
            key = atom.residue_key
            author_key = (atom.model_id, atom.chain_id, atom.group, atom.residue_id, atom.insertion_code)
            if key in seen or author_key in author_seen:
                warnings.append({"code": "duplicate_residue_id", "line": atom.line,
                                 "message": f"Repeated residue identity {author_key}; retained as separate occurrence"})
            seen.add(key); author_seen.add(author_key)
            residues.append(Residue(key, atom.residue_name, len(residues), []))
        residue = residues[-1]
        if residue.name != atom.residue_name:
            raise UnsupportedFormat("microheterogeneity: multiple residue names at one identity")
        if residue.atoms and (residue.atoms[0].label_chain_id, residue.atoms[0].label_seq_id) != (atom.label_chain_id, atom.label_seq_id):
            raise UnsupportedFormat("inconsistent label identity within author residue")
        if any((a.atom_name, a.altloc) == (atom.atom_name, atom.altloc) for a in residue.atoms):
            warnings.append({"code": "duplicate_atom_id", "line": atom.line,
                             "message": f"Duplicate atom {atom.atom_name}/{atom.altloc} in residue {residue.index}"})
        residue.atoms.append(atom)
    return Structure(str(path.resolve()), before, "pdb" if fmt == ".pdb" else "mmcif",
                     model_id, atoms, residues, warnings)


def selected_atoms(residue, altloc="A"):
    """One explicit conformer plus shared atoms; do not fall back to another altloc."""
    if not isinstance(altloc, str) or not altloc:
        raise ValueError("altloc must be an explicit nonempty identifier")
    all_names = {a.atom_name for a in residue.atoms}
    selected, messages = {}, []
    for name in sorted(all_names):
        candidates = [a for a in residue.atoms if a.atom_name == name and a.altloc in ("", altloc)]
        if len(candidates) != 1:
            messages.append(f"atom {name}: {len(candidates)} records for shared/altloc {altloc}; not selected")
        else:
            selected[name] = candidates[0]
    return selected, messages
