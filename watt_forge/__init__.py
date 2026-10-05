"""Watt Forge: converter physics, loss models and the flagship hybrid GaN buck-boost.

Everything here is a design and simulation reference. It is not a
build-and-energize guide. See SAFETY.md.
"""

__version__ = "0.2.0"

from . import ratios, losses, magnetics, switched_cap, efficiency, devices, topologies, pv  # noqa: F401
