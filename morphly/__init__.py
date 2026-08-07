"""morphly — typed workflows over a shared set of pydantic business objects."""

from importlib.metadata import version

from morphly.entity import Config, Entity
from morphly.module import Module, Step, module
from morphly.operations import Delete, Patch, view
from morphly.store import Store
from morphly.workflow import Workflow

__version__ = version("morphly")

__all__ = [
    "Config",
    "Delete",
    "Entity",
    "Module",
    "Patch",
    "Step",
    "Store",
    "Workflow",
    "module",
    "view",
]
