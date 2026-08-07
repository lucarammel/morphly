"""morph — typed pipelines over a shared set of pydantic business objects."""

from importlib.metadata import version

from morph.entity import Config, Entity
from morph.module import Module, Step, module
from morph.operations import Delete, Patch, view
from morph.pipeline import Pipeline
from morph.store import Store

__version__ = version("morph")

__all__ = [
    "Config",
    "Delete",
    "Entity",
    "Module",
    "Patch",
    "Pipeline",
    "Step",
    "Store",
    "module",
    "view",
]
