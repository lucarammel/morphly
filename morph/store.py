"""Shared business objects and the store that holds them.

The type is the key: no enum, no name-to-class mapping, no registry. A module asks for
`list[Employee]` and receives every `Employee` held by the store, subclasses included.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_CONFIG = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)


class Entity(BaseModel):
    """A shared business object, identified by `name` within its type lineage.

    Subclass it to declare a business object. Identity is the `(type, name)` pair, and
    `name` is frozen: an entity keeps its identity for its whole life, only its other
    fields change.

    Two pydantic settings are enabled: `validate_assignment`, so every field write is
    validated — including the ones a [`Patch`][morph.Patch] applies — and
    `arbitrary_types_allowed`, so a field may carry a non-pydantic object such as a
    dataframe, a matrix or a solver handle.

    Subclasses are a first-class case: a module reading `list[Employee]` also receives
    every `Manager` in the store.

    Attributes:
        name: Stable identifier, unique within the type lineage. Frozen.

    Examples:
        ```python
        class Employee(Entity):
            hourly_rate: float
            gross: float = 0.0


        class Manager(Employee):
            bonus_target: float
        ```
    """

    name: str = Field(frozen=True)

    model_config = _CONFIG

    def __repr__(self) -> str:
        return f"{type(self).__name__}(name={self.name!r})"


class Config(BaseModel):
    """A singleton input: module parameters, global settings, context.

    A `Config` has no `name` because there is only ever one of each type in play. It is
    resolved by type, either from the [`Step`][morph.Step] it is bound to or from the
    [`Store`][morph.Store].

    Examples:
        ```python
        class PayrollPolicy(Config):
            overtime_after: float = 35.0
            overtime_rate: float = 1.25
            social_rate: float = 0.22
        ```
    """

    model_config = _CONFIG


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


def _same_lineage(a: type, b: type) -> bool:
    return issubclass(a, b) or issubclass(b, a)


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


class Store:
    """The shared state. Buckets by concrete type, read by type (subclasses included).

    Entities are keyed by `(concrete type, name)` and configs by type. Reading is done
    by type and walks the lineage, so `all(Employee)` returns the `Manager` instances
    too.

    The store is a plain Python object: `copy.deepcopy(store)` is a snapshot and
    `pickle` persists it.

    Args:
        *items: Entities and configs to load.

    Examples:
        ```python
        store = Store(
            Employee(name="ada", hourly_rate=50.0, contract_hours=35.0),
            Manager(name="bob", hourly_rate=60.0, contract_hours=35.0, bonus_target=0.1),
            PayrollPolicy(social_rate=0.22),
        )
        store.all(Employee)  # [Employee(name='ada'), Manager(name='bob')]
        store.one(PayrollPolicy).social_rate  # 0.22
        ```
    """

    def __init__(self, *items: Entity | Config):
        self._buckets: dict[type, dict[str, Entity]] = {}
        self._configs: dict[type, Config] = {}
        self.put(*items)

    def put(self, *items: Entity | Config) -> None:
        """Upsert entities (keyed by type and name) and configs (keyed by type).

        An entity replaces any object already stored under the same `(type, name)`. For
        a partial update, use [`patch`][morph.Store.patch] instead.

        Args:
            *items: Entities and configs to store.

        Raises:
            TypeError: If an item is neither an `Entity` nor a `Config`.
        """
        for item in items:
            if isinstance(item, Config):
                self._configs[type(item)] = item
            elif isinstance(item, Entity):
                self._buckets.setdefault(type(item), {})[item.name] = item
            else:
                raise TypeError(f"{item!r} is neither an Entity nor a Config")

    def all[E: Entity](self, cls: type[E]) -> list[E]:
        """Every instance of `cls` and of its subclasses.

        Args:
            cls: The entity type to read.

        Returns:
            The matching entities, in insertion order per bucket. Empty if none.
        """
        return [obj for t, b in self._buckets.items() if issubclass(t, cls) for obj in b.values()]  # ty: ignore[invalid-return-type]

    def one[C: Config](self, cls: type[C]) -> C:
        """The single instance of config `cls`.

        Args:
            cls: The config type to read.

        Returns:
            The stored config.

        Raises:
            LookupError: If the store holds zero or several configs of that lineage.
        """
        hits = [c for t, c in self._configs.items() if issubclass(t, cls)]
        if len(hits) != 1:
            raise LookupError(f"expected exactly 1 {cls.__name__} in the store, found {len(hits)}")
        return hits[0]  # ty: ignore[invalid-return-type]

    def find[E: Entity](self, cls: type[E], name: str) -> E:
        """The object named `name`: exact type first, then the lineage of `cls`.

        Args:
            cls: The declared type of the object.
            name: Its identifier.

        Returns:
            The stored entity.

        Raises:
            KeyError: If no object matches, or if several sibling types hold that name.
        """
        return self._locate(cls, name)[1]  # ty: ignore[invalid-return-type]

    def drop(self, target: Entity | type[Entity], name: str | None = None) -> None:
        """Remove the stored object matching `target`.

        Args:
            target: An entity with the type lineage and `name` to remove — it does not
                have to be the stored instance itself — or the entity type, paired
                with `name`.
            name: The object's name, when `target` is a type.

        Raises:
            TypeError: If `target` is a type and `name` is not given.
            KeyError: If no object matches, or if the name is ambiguous.
        """
        cls, name = self._target(target, name)
        bucket, obj = self._locate(cls, name)
        del bucket[obj.name]
        if not bucket:
            del self._buckets[type(obj)]

    def patch(
        self,
        target: Entity | type[Entity],
        name_or_fields: str | dict[str, Any],
        fields: dict[str, Any] | None = None,
    ) -> None:
        """Write `fields` onto the stored object matching `target`.

        Args:
            target: An entity with the type lineage and `name` to update, or the
                entity type, paired with a name and fields.
            name_or_fields: Field names and values to write, when `target` is an
                entity, else the object's name.
            fields: Field names and values to write, when `target` is a type.

        Raises:
            TypeError: If `target` is a type and `fields` is not given.
            KeyError: If no object matches, or if the name is ambiguous.
            ValueError: If a name is not a field of the stored object.
            pydantic.ValidationError: If a value does not validate.
        """
        if isinstance(target, Entity):
            cls, name, fields = type(target), target.name, name_or_fields  # ty: ignore[invalid-assignment]
        else:
            cls, name = target, name_or_fields
        if fields is None:
            raise TypeError(f"patch({cls.__name__}, {name!r}, ...) requires fields")
        obj = self.find(cls, name)  # ty: ignore[invalid-argument-type]
        check_fields(obj, fields)
        for key, value in fields.items():
            setattr(obj, key, value)

    def _target(self, target: Entity | type[Entity], name: str | None) -> tuple[type[Entity], str]:
        if isinstance(target, Entity):
            return type(target), target.name
        if name is None:
            raise TypeError(f"{target.__name__} requires a name")
        return target, name

    def types(self) -> set[type]:
        """Types currently present, entities and configs.

        Returns:
            The concrete types held by the store. This is the starting point of
            [`Pipeline.check`][morph.Pipeline.check].
        """
        return set(self._buckets) | set(self._configs)

    def _locate(self, cls: type, name: str) -> tuple[dict[str, Entity], Entity]:
        exact = self._buckets.get(cls)
        if exact is not None and name in exact:
            return exact, exact[name]
        hits = [(b, b[name]) for t, b in self._buckets.items() if _same_lineage(t, cls) and name in b]
        if not hits:
            raise KeyError(f"no {cls.__name__} named {name!r} in the store")
        if len(hits) > 1:
            found = ", ".join(sorted(type(obj).__name__ for _, obj in hits))
            raise KeyError(f"{name!r} is ambiguous in the lineage of {cls.__name__}: {found}")
        return hits[0]

    def __repr__(self) -> str:
        content = ", ".join(f"{t.__name__}={len(b)}" for t, b in sorted(self._buckets.items(), key=_type_name))
        configs = ", ".join(sorted(t.__name__ for t in self._configs))
        return f"Store({content}{'; ' + configs if configs else ''})"


def _type_name(item: tuple[type, Any]) -> str:
    return item[0].__name__
