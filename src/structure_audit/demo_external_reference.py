"""Pure presentation of supplied output lines and separate external provenance.

No source is accessed or verified here. Runtime observations are carried verbatim;
they confer no admission, eligibility or relationship to the existing outputs.
"""
from dataclasses import dataclass, fields


def _strings(value, name):
    if type(value) not in (list, tuple) or any(type(item) is not str for item in value):
        raise TypeError(f"{name} must be a list or tuple of strings")
    return tuple(value)


@dataclass(frozen=True, slots=True)
class ExternalStructureReference:
    """Immutable snapshot of caller-supplied observations, without status conversion."""

    provider: str
    profile: str
    artifact_id: str
    observed_sha256: str
    source_status: str
    read_completed: bool
    execution_state: str
    validation_status: str
    non_admission_reasons: tuple[str, ...]

    def __post_init__(self):
        for name in ("provider", "profile", "artifact_id", "observed_sha256",
                     "source_status", "execution_state", "validation_status"):
            if type(getattr(self, name)) is not str:
                raise TypeError(f"{name} must be a string")
        if type(self.read_completed) is not bool:
            raise TypeError("read_completed must be a bool")
        object.__setattr__(self, "non_admission_reasons",
                           _strings(self.non_admission_reasons, "non_admission_reasons"))

    def to_dict(self):
        """Return a fresh presentation record; no mutable storage is exposed."""
        return {field.name: (list(self.non_admission_reasons)
                             if field.name == "non_admission_reasons"
                             else getattr(self, field.name)) for field in fields(self)}


@dataclass(frozen=True, slots=True)
class ExternalReferenceReport:
    """Separate presentation snapshot; never a core summary or acceptance record."""

    existing_summary_lines: tuple[str, ...]
    external_structure_reference: ExternalStructureReference | None

    def __post_init__(self):
        object.__setattr__(self, "existing_summary_lines",
                           _strings(self.existing_summary_lines, "existing_summary_lines"))
        if (self.external_structure_reference is not None
                and type(self.external_structure_reference) is not ExternalStructureReference):
            raise TypeError("external_reference must be an ExternalStructureReference or None")

    def to_dict(self):
        reference = self.external_structure_reference
        return {"existing_summary_lines": list(self.existing_summary_lines),
                "external_structure_reference": None if reference is None else reference.to_dict()}

    def render_lines(self):
        """Return fresh lines, preserving the supplied prefix exactly and in order."""
        lines = list(self.existing_summary_lines)
        reference = self.external_structure_reference
        if reference is None:
            return lines + ["External structure reference not supplied/available"]
        lines.append("External structure reference — separate provenance; no admission.")
        for name, value in reference.to_dict().items():
            if name == "non_admission_reasons":
                lines.append("non_admission_reasons:")
                lines.extend("  - " + reason for reason in value)
            else:
                label = "runtime validation status" if name == "validation_status" else name
                text = ("true" if value else "false") if type(value) is bool else value
                lines.append(f"{label}: {text}")
        return lines


def build_demo_report(existing_summary_lines: list[str] | tuple[str, ...],
                      external_reference: ExternalStructureReference | None = None
                      ) -> ExternalReferenceReport:
    """Compose already-produced display lines and optional, separate provenance.

    None covers an absent or unavailable supplied record. No file availability check,
    reader, producer, callback, status promotion or cross-output association occurs.
    """
    return ExternalReferenceReport(existing_summary_lines, external_reference)
