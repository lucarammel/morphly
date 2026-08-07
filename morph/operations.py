"""What a module returns to declare a change: `Patch`, `Delete`, and the `view` helper."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from morph.entity import Entity


class Delete[E: Entity]:
    """Deletion marker returned by a module. Annotate as `Delete[Timesheet]`.

    Returning a `Delete` does not remove anything by itself: it is an intent, applied by
    the pipeline once the whole step has been validated.

    Args:
        target: The entity to remove. Only its type lineage and `name` are used, so an
            enriched copy of a stored object is a valid target.

    Examples:
        ```python
        @module
        def archive(timesheets: list[Timesheet]) -> list[Delete[Timesheet]]:
            return [Delete(t) for t in timesheets if t.processed]
        ```
    """

    __slots__ = ("target",)

    def __init__(self, target: E):
        self.target = target

    def __repr__(self) -> str:
        return f"Delete({self.target!r})"


class Patch[E: Entity]:
    """Partial update returned by a module. Annotate as `Patch[Employee]`.

    A `Patch` writes only the fields it is given and leaves the rest of the object
    untouched — the normal output of a module that computes a few attributes on shared
    objects. Returning a whole `Entity` instead means creation or full replacement.

    Like [`Delete`][morph.Delete], it is an intent: nothing is written until the step
    has produced all of its operations and they have all been validated.

    Args:
        target: The entity to update, resolved by type lineage and `name`.
        **fields: Field names and values to write. At least one is required.

    Raises:
        ValueError: If no field is given.

    Examples:
        ```python
        @module
        def pay(employees: list[Employee]) -> list[Patch[Employee]]:
            return [Patch(e, gross=e.hourly_rate * e.contract_hours) for e in employees]
        ```
    """

    __slots__ = ("fields", "target")

    def __init__(self, target: E, **fields: Any):
        if not fields:
            raise ValueError(f"Patch({target!r}) has no field to write")
        self.target = target
        self.fields = fields

    def __repr__(self) -> str:
        return f"Patch({self.target!r}, {', '.join(self.fields)})"


def check_fields(obj: BaseModel, fields: dict[str, Any]) -> None:
    """Raise if `fields` names something the model does not declare.

    Args:
        obj: The model the fields are meant to be written onto.
        fields: Field names and values to check.

    Raises:
        ValueError: If a name is not a field of `obj`.
    """
    unknown = set(fields) - set(type(obj).model_fields)
    if unknown:
        raise ValueError(f"{type(obj).__name__} has no field {sorted(unknown)}")


def view[T: BaseModel](cls: type[T], source: BaseModel, **extra: Any) -> T:
    """Build an enriched module-local view of a shared object.

    Shallow-copies the source fields, adds `extra`, and validates against `cls`. Use it
    when a module needs to carry its own working fields on a shared entity without
    polluting the shared type with them.

    The view can be handed straight back inside a `Patch`: targets are resolved against
    the type declared in the return annotation, not the view's own class.

    Args:
        cls: Target model class, usually a subclass of the source class.
        source: Object to project.
        **extra: Module-specific fields to add.

    Returns:
        A new `cls` instance holding the source fields plus `extra`.

    Raises:
        pydantic.ValidationError: If the merged fields do not validate against `cls`.

    Examples:
        ```python
        class EmployeeWithHours(Employee):
            worked: float


        @module
        def pay(employees: list[Employee], sheets: list[Timesheet]) -> list[Patch[Employee]]:
            hours = {s.employee: s.hours for s in sheets}
            rich = [view(EmployeeWithHours, e, worked=hours.get(e.name, 0.0)) for e in employees]
            return [Patch(e, gross=e.hourly_rate * e.worked) for e in rich]
        ```
    """
    fields = {name: getattr(source, name) for name in type(source).model_fields}
    return cls.model_validate(fields | extra)
