"""The shared business object vocabulary: `Entity` and `Config`."""

from __future__ import annotations

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
