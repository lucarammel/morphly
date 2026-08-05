"""Shared business objects and the store that holds them.

The type is the key: no enum, no name-to-class mapping, no registry.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_CONFIG = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)


class Entity(BaseModel):
    """A shared business object, identified by ``name`` within its type lineage."""

    name: str = Field(frozen=True)

    model_config = _CONFIG

    def __repr__(self) -> str:
        return f"{type(self).__name__}(name={self.name!r})"


class Config(BaseModel):
    """A singleton input: module parameters, global settings, context."""

    model_config = _CONFIG


class Delete[E: Entity]:
    """Deletion marker returned by a module. Annotate as ``Delete[Order]``."""

    __slots__ = ("target",)

    def __init__(self, target: E):
        self.target = target

    def __repr__(self) -> str:
        return f"Delete({self.target!r})"


class Patch[E: Entity]:
    """Partial update returned by a module. Annotate as ``Patch[Order]``."""

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
    """Raise if ``fields`` names something the model does not declare."""
    unknown = set(fields) - set(type(obj).model_fields)
    if unknown:
        raise ValueError(f"{type(obj).__name__} has no field {sorted(unknown)}")


def view[T: BaseModel](cls: type[T], source: BaseModel, **extra: Any) -> T:
    """Build an enriched module-local view of a shared object.

    Shallow-copies the source fields, adds ``extra``, and validates against ``cls``.

    :param cls: target model class, usually a subclass of the source class
    :param source: object to project
    :param extra: module-specific fields to add
    """
    fields = {name: getattr(source, name) for name in type(source).model_fields}
    return cls.model_validate(fields | extra)


class Store:
    """The shared state. Buckets by concrete type, read by type (subclasses included)."""

    def __init__(self, *items: Entity | Config):
        self._buckets: dict[type, dict[str, Entity]] = {}
        self._configs: dict[type, Config] = {}
        self.put(*items)

    def put(self, *items: Entity | Config) -> None:
        """Upsert entities (keyed by type and name) and configs (keyed by type)."""
        for item in items:
            if isinstance(item, Config):
                self._configs[type(item)] = item
            elif isinstance(item, Entity):
                self._buckets.setdefault(type(item), {})[item.name] = item
            else:
                raise TypeError(f"{item!r} is neither an Entity nor a Config")

    def all[E: Entity](self, cls: type[E]) -> list[E]:
        """Every instance of ``cls`` and of its subclasses."""
        return [obj for t, b in self._buckets.items() if issubclass(t, cls) for obj in b.values()]  # ty: ignore[invalid-return-type]

    def one[C: Config](self, cls: type[C]) -> C:
        """The single instance of config ``cls``."""
        hits = [c for t, c in self._configs.items() if issubclass(t, cls)]
        if len(hits) != 1:
            raise LookupError(f"expected exactly 1 {cls.__name__} in the store, found {len(hits)}")
        return hits[0]  # ty: ignore[invalid-return-type]

    def find[E: Entity](self, cls: type[E], name: str) -> E:
        """The object named ``name``: exact type first, then the lineage of ``cls``."""
        return self._locate(cls, name)[1]  # ty: ignore[invalid-return-type]

    def drop(self, target: Entity) -> None:
        """Remove the stored object matching ``target``."""
        bucket, obj = self._locate(type(target), target.name)
        del bucket[obj.name]

    def patch(self, target: Entity, fields: dict[str, Any]) -> None:
        """Write ``fields`` onto the stored object matching ``target``."""
        obj = self.find(type(target), target.name)
        check_fields(obj, fields)
        for key, value in fields.items():
            setattr(obj, key, value)

    def types(self) -> set[type]:
        """Types currently present, entities and configs."""
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
