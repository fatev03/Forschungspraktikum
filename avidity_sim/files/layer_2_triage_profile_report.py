"""Read-only display adapter for ``layer_2_initial_triage_profile/1``.

Standard library only. This module renders one already-built profile. It mints no
document type, derives no ranking, reorders no candidate, mutates nothing, and runs no
Layer 1, 2A or 2B producer. It opens no file, resolves no locator, invokes no viewer or
tool, generates no artifact, reads no clock or environment, starts no subprocess and
reaches no network.

Every displayed value is copied from the supplied profile. The displayed order is the
profile's own: ``relation.ordered_groups`` for the priority grouping, and the profile's
candidate order for the inventory. A ``GATE_PASSED_SUBSET_ONLY`` relation is labeled as
subset-only wherever it is shown, and ``REVIEW_REQUIRED`` and ``COMPARISON_UNSUPPORTED``
candidates are displayed as declared states, never as losses.
"""
from __future__ import annotations

from .layer_2_initial_triage_profile import (
    Layer2InitialTriageProfile,
    TRIAGE_DOCUMENT_TYPE,
    TRIAGE_NON_CLAIM,
)

REPORT_NON_CLAIM = (
    TRIAGE_NON_CLAIM
    + " This view only restates that profile: it recomputes nothing, reorders nothing, "
    "opens no referenced artifact, and adds no interpretation, recommendation or "
    "experimental expectation. A subset-only relation is not a cohort ranking, and a "
    "reviewed or unsupported state is not a negative result."
)

#: The row keys this adapter emits, in this order.
ROW_FIELDS = (
    "candidate_id",
    "profile_state",
    "relation_scope",
    "group_index",
    "withheld_reason",
    "layer1_disposition",
    "layer1_rank",
    "layer1_geometry_tier",
    "active_dimensions",
    "active_dimension_details",
    "suspended_dimensions",
    "source_references",
)

#: The keys of one active-dimension detail entry, in this order.
ACTIVE_DIMENSION_DETAIL_FIELDS = (
    "dimension",
    "position_role",
    "value",
    "unit_symbol",
    "observable_name",
)

#: The keys of one tidy active-dimension row, in this order.
ACTIVE_DIMENSION_ROW_FIELDS = (
    "candidate_id",
    "profile_state",
    "relation_scope",
    "group_index",
    "dimension",
    "position_role",
    "value",
    "unit_symbol",
    "unit_class",
    "observable_name",
    "descriptor_id",
    "observation_id",
)

#: The keys of one source-reference row, in this order.
SOURCE_ROW_FIELDS = (
    "candidate_id",
    "source_kind",
    "document_type",
    "document_id",
    "revision",
    "position_role",
    "pointer",
)

SUBSET_ONLY_LABEL = "subset-only: gate-passed candidates, not a cohort-wide priority"


class TriageProfileReportError(ValueError):
    """Adapter misuse. Contract faults keep their own profile error type."""


def load_profile(document):
    """Validate and return the profile.

    ``document`` is a ``Layer2InitialTriageProfile``, its serialized mapping or its
    canonical bytes. Mappings and bytes are reconstructed through the profile contract,
    so a modified constant, an unknown key or non-canonical bytes are refused there.
    """
    if isinstance(document, Layer2InitialTriageProfile):
        return document
    if isinstance(document, (bytes, bytearray)):
        return Layer2InitialTriageProfile.from_json_bytes(bytes(document))
    if isinstance(document, dict):
        return Layer2InitialTriageProfile.from_dict(document)
    raise TriageProfileReportError(
        "a profile, its serialized mapping or its canonical bytes is required"
    )


def _group_index(profile, candidate_id):
    for position, group in enumerate(profile.relation.ordered_groups):
        if candidate_id in group:
            return position
    return None


def _dimension_label(state):
    if state.position_role is None:
        return state.dimension
    return "{0}@{1}".format(state.dimension, state.position_role)


def _active_dimensions(entry):
    return tuple(
        _dimension_label(state) for state in entry.dimensions if state.state == "ACTIVE"
    )


def _detail_label(detail):
    if detail["position_role"] is None:
        return detail["dimension"]
    return "{0}@{1}".format(detail["dimension"], detail["position_role"])


def _active_dimension_details(entry):
    """One detail entry per active dimension, in the candidate's own dimension order.

    Every value is copied from the carried comparable record: the decimal string is the
    one the descriptor supplied, never reformatted, converted or combined.
    """
    details = []
    for state in entry.dimensions:
        if state.state != "ACTIVE":
            continue
        record = state.record
        details.append(
            {
                "dimension": state.dimension,
                "position_role": state.position_role,
                "value": record.value,
                "unit_symbol": record.unit_symbol,
                "observable_name": record.observable_name,
            }
        )
    return tuple(details)


def _suspended_dimensions(entry):
    return tuple(
        "{0}: {1}".format(_dimension_label(state), state.suspension_reason)
        for state in entry.dimensions
        if state.state == "SUSPENDED"
    )


def _source_references(entry):
    references = []
    if entry.layer1.source_pointer is not None:
        references.append(
            "cassette_candidate_priority/1{0}".format(entry.layer1.source_pointer)
        )
    for source in entry.sources:
        label = source.document_type
        if source.position_role is not None:
            label += "@" + source.position_role
        if source.document_id is not None:
            label += " " + source.document_id
        if source.revision is not None:
            label += " " + source.revision
        references.append(label)
    return tuple(references)


def _row(profile, entry):
    """One plain row. Every value is copied from the profile."""
    return {
        "candidate_id": entry.candidate_id,
        "profile_state": entry.profile_state,
        "relation_scope": profile.relation.scope,
        "group_index": _group_index(profile, entry.candidate_id),
        "withheld_reason": profile.relation.withheld_reason,
        "layer1_disposition": entry.layer1.disposition,
        "layer1_rank": entry.layer1.rank,
        "layer1_geometry_tier": entry.layer1.geometry_tier,
        "active_dimensions": _active_dimensions(entry),
        "active_dimension_details": _active_dimension_details(entry),
        "suspended_dimensions": _suspended_dimensions(entry),
        "source_references": _source_references(entry),
    }


def candidate_inventory_rows(document):
    """Every candidate, in the profile's own candidate order. Nothing is reordered."""
    profile = load_profile(document)
    return tuple(_row(profile, entry) for entry in profile.candidates)


def top_candidate_combinations_rows(document, *, group_index=0):
    """The members of one relation group, in the group's own serialized order.

    ``group_index`` selects a group of ``relation.ordered_groups``; 0 is the leading
    group. An empty relation yields no rows: no candidate is promoted to fill it.
    """
    profile = load_profile(document)
    if type(group_index) is not int or isinstance(group_index, bool) or group_index < 0:
        raise TriageProfileReportError("group_index must be a non-negative integer")
    groups = profile.relation.ordered_groups
    if not groups:
        return ()
    if group_index >= len(groups):
        raise TriageProfileReportError(
            "the relation declares {0} group(s); {1} is outside it".format(
                len(groups), group_index
            )
        )
    by_id = {entry.candidate_id: entry for entry in profile.candidates}
    return tuple(_row(profile, by_id[member]) for member in groups[group_index])


def active_dimension_rows(document):
    """One tidy row per candidate and active dimension, in the profile's own order."""
    profile = load_profile(document)
    rows = []
    for entry in profile.candidates:
        for state in entry.dimensions:
            if state.state != "ACTIVE":
                continue
            record = state.record
            rows.append(
                {
                    "candidate_id": entry.candidate_id,
                    "profile_state": entry.profile_state,
                    "relation_scope": profile.relation.scope,
                    "group_index": _group_index(profile, entry.candidate_id),
                    "dimension": state.dimension,
                    "position_role": state.position_role,
                    "value": record.value,
                    "unit_symbol": record.unit_symbol,
                    "unit_class": record.unit_class,
                    "observable_name": record.observable_name,
                    "descriptor_id": record.descriptor_id,
                    "observation_id": record.observation_id,
                }
            )
    return tuple(rows)


def source_reference_rows(document):
    """The declared source references as display rows. No locator is resolved."""
    profile = load_profile(document)
    rows = []
    for entry in profile.candidates:
        if entry.layer1.source_pointer is not None:
            rows.append(
                {
                    "candidate_id": entry.candidate_id,
                    "source_kind": "LAYER1",
                    "document_type": profile.layer1_source.document_type,
                    "document_id": profile.layer1_source.document_id,
                    "revision": profile.layer1_source.revision,
                    "position_role": None,
                    "pointer": entry.layer1.source_pointer,
                }
            )
        for source in entry.sources:
            rows.append(
                {
                    "candidate_id": entry.candidate_id,
                    "source_kind": "LOCAL" if source.position_role else "COLLECTIVE",
                    "document_type": source.document_type,
                    "document_id": source.document_id,
                    "revision": source.revision,
                    "position_role": source.position_role,
                    "pointer": None,
                }
            )
    return tuple(rows)


def render_profile_lines(document):
    """The profile restated as deterministic display lines."""
    profile = load_profile(document)
    relation = profile.relation
    lines = [
        "Layer 2 initial triage profile — display view of a finished profile",
        "",
        "document_type: " + TRIAGE_DOCUMENT_TYPE,
        "profile: {0} revision {1}; declared by {2} at {3}".format(
            profile.profile_id, profile.revision, profile.declared_by, profile.declared_at
        ),
        "convention: " + profile.cohort.triage_convention_version,
        "target system: " + profile.cohort.target_system_identity,
        "layer 1 basis: " + profile.cohort.layer1_comparison_basis,
        "collective task scope: " + profile.cohort.collective_task_scope_type,
        "ordered local positions: "
        + ", ".join(profile.cohort.ordered_local_position_roles),
        "",
        "relation scope: " + relation.scope,
    ]
    if relation.scope == "GATE_PASSED_SUBSET_ONLY":
        lines.append(SUBSET_ONLY_LABEL)
    if relation.withheld_reason is not None:
        lines.append("full-cohort issuance withheld: " + relation.withheld_reason)
    lines.append(
        "comparison basis dimensions: "
        + (", ".join(relation.basis_dimensions) or "none active")
    )

    lines.append("")
    lines.append("Declared directions")
    for declared in profile.cohort.dimension_directions:
        lines.append("  {0}: {1}".format(declared.dimension, declared.direction))

    lines.append("")
    lines.append("Cohort dimensions")
    for state in profile.cohort_dimensions:
        lines.append(
            "  {0}: {1}{2}".format(
                state.dimension,
                state.state,
                ""
                if state.suspension_reason is None
                else " (" + state.suspension_reason + ")",
            )
        )

    lines.append("")
    if relation.ordered_groups:
        lines.append(
            "Priority grouping (profile order; equal group means equal position)"
        )
        for position, group in enumerate(relation.ordered_groups):
            lines.append("  group {0}: {1}".format(position, ", ".join(group)))
    else:
        lines.append("Priority grouping: no comparison was issued")

    lines.append("")
    lines.append("Candidates (profile order)")
    for entry in profile.candidates:
        lines.append(
            "  {0}  {1}".format(entry.candidate_id, entry.profile_state)
        )
        lines.append(
            "    layer 1: {0}{1}{2}".format(
                entry.layer1.disposition,
                "" if entry.layer1.rank is None else " rank " + str(entry.layer1.rank),
                ""
                if entry.layer1.geometry_tier is None
                else " " + entry.layer1.geometry_tier,
            )
        )
        if entry.layer1.ineligibility_reason is not None:
            lines.append(
                "    layer 1 ineligibility: " + entry.layer1.ineligibility_reason
            )
        for gate in entry.gates:
            if gate.disposition != "PASSED":
                lines.append(
                    "    gate {0}: {1}{2}".format(
                        gate.gate,
                        gate.disposition,
                        "" if gate.reason is None else " (" + gate.reason + ")",
                    )
                )
        details = _active_dimension_details(entry)
        if details:
            for detail in details:
                lines.append(
                    "    active {0}: {1}{2}".format(
                        _detail_label(detail),
                        detail["value"],
                        "" if detail["unit_symbol"] is None else " " + detail["unit_symbol"],
                    )
                )
        else:
            lines.append("    active: none")
        for suspended in _suspended_dimensions(entry):
            lines.append("    suspended " + suspended)
        for reference in _source_references(entry):
            lines.append("    source: " + reference)

    lines.append("")
    lines.append(REPORT_NON_CLAIM)
    return tuple(lines)


# ================================================================================
# Notebook surface
# ================================================================================

_SECTION = """## Layer 2 initial triage profile — read-only display

Display surface over one finished `layer_2_initial_triage_profile/1` document
(`layer_2_triage_profile_report`). It loads the profile through its own contract and
restates it: the candidate inventory in the profile's own order, the priority grouping
the profile already derived, the active dimensions with their carried values, the
suspended dimensions with their reasons, and the declared source references as text.

Nothing here recomputes, reorders, aggregates or ranks. No Layer 1, 2A or 2B producer
runs, no artifact is generated, no reference is opened and no tool is invoked. A
`GATE_PASSED_SUBSET_ONLY` relation is labeled as such and is not a cohort-wide priority;
`REVIEW_REQUIRED` and `COMPARISON_UNSUPPORTED` are declared states, not losses, and
missing evidence is not negative evidence.
"""

_LOAD = """#@title Triage profile 1/5 — load and validate one finished profile
from gotne.layer_2_triage_profile_report import (
    load_profile, render_profile_lines,
)

# Run the Section 8 kernel-bootstrap cell first; it binds the local package as gotne.
# TRIAGE_PROFILE_DOCUMENT is a finished layer_2_initial_triage_profile/1 document, as a
# mapping or its canonical bytes, produced earlier by its own layer. Nothing is computed
# here and no producer is imported; loading validates it through the profile contract.
triage_profile = load_profile(TRIAGE_PROFILE_DOCUMENT)
print("\\n".join(render_profile_lines(triage_profile)))
"""

_INVENTORY = """#@title Triage profile 2/5 — candidate inventory, in the profile's own order
import pandas as pd
from gotne.layer_2_triage_profile_report import ROW_FIELDS, candidate_inventory_rows

# Row order is the profile's candidate order. Nothing is sorted, filtered or dropped:
# REVIEW_REQUIRED and COMPARISON_UNSUPPORTED candidates are listed as declared states.
triage_inventory_rows = candidate_inventory_rows(triage_profile)
triage_inventory = pd.DataFrame(triage_inventory_rows, columns=list(ROW_FIELDS))
print(triage_inventory[[
    "candidate_id", "profile_state", "relation_scope", "group_index",
    "layer1_disposition", "layer1_rank", "layer1_geometry_tier",
]].to_string(index=False))
"""

_TOP = """#@title Triage profile 3/5 — top candidate combinations, from the derived groups
from gotne.layer_2_triage_profile_report import top_candidate_combinations_rows

# The members of relation group 0, in the group's own order. An equal group means an
# equal position, never an internal ranking, and an empty relation promotes nobody.
triage_top_rows = top_candidate_combinations_rows(triage_profile)
if triage_profile.relation.scope == "GATE_PASSED_SUBSET_ONLY":
    print("subset-only: gate-passed candidates, not a cohort-wide priority")
    print("full-cohort issuance withheld:", triage_profile.relation.withheld_reason)
for triage_row in triage_top_rows:
    print(triage_row["candidate_id"], triage_row["profile_state"],
          "group", triage_row["group_index"])
    for triage_suspended in triage_row["suspended_dimensions"]:
        print("   suspended", triage_suspended)
if not triage_top_rows:
    print("no comparison was issued; no candidate is promoted")
"""

_DIMENSIONS = """#@title Triage profile 4/5 — active dimension values, units and observables
import pandas as pd
from gotne.layer_2_triage_profile_report import (
    ACTIVE_DIMENSION_ROW_FIELDS, active_dimension_rows,
)

# One row per candidate and active dimension. Values are the decimal strings the
# descriptors supplied, carried verbatim with their declared unit; nothing is converted,
# combined or scored, and a suspended dimension contributes no row.
triage_dimension_rows = active_dimension_rows(triage_profile)
triage_dimensions = pd.DataFrame(
    triage_dimension_rows, columns=list(ACTIVE_DIMENSION_ROW_FIELDS)
)
print(triage_dimensions[[
    "candidate_id", "dimension", "position_role", "value", "unit_symbol",
    "observable_name",
]].to_string(index=False))
"""

_SOURCES = """#@title Triage profile 5/5 — source references for external inspection
import pandas as pd
from gotne.layer_2_triage_profile_report import SOURCE_ROW_FIELDS, source_reference_rows

# Reference text only, carried verbatim from the profile. Decide by hand what, if
# anything, to open: nothing here resolves a locator, reads a document or starts a tool.
triage_source_rows = source_reference_rows(triage_profile)
triage_sources = pd.DataFrame(triage_source_rows, columns=list(SOURCE_ROW_FIELDS))
print(triage_sources.to_string(index=False))
"""

_CELLS = (
    ("triage-profile-00-section", "markdown", _SECTION),
    ("triage-profile-01-load", "code", _LOAD),
    ("triage-profile-02-inventory", "code", _INVENTORY),
    ("triage-profile-03-top-candidates", "code", _TOP),
    ("triage-profile-04-dimensions", "code", _DIMENSIONS),
    ("triage-profile-05-sources", "code", _SOURCES),
)


def notebook_cell_sources():
    """Return the paste-ready (cell_id, cell_type, source) triples, fresh on every call.

    This is the notebook surface: text a reader pastes, never an edit this module
    performs. No notebook is opened, parsed or written.
    """
    return tuple((cell_id, cell_type, source) for cell_id, cell_type, source in _CELLS)
