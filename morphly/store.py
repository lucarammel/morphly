"""The shared state that holds `Entity` and `Config` instances.

The type is the key: no enum, no name-to-class mapping, no registry. A module asks for
`list[Employee]` and receives every `Employee` held by the store, subclasses included.
"""

from __future__ import annotations

from typing import Any

from morph.entity import Config, Entity
from morph.operations import check_fields


def _same_lineage(a: type, b: type) -> bool:
    return issubclass(a, b) or issubclass(b, a)


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
