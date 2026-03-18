"""
NLM Backend Adapters
====================
Pluggable adapters for BCM, MAAS, Kubernetes, and Bare Metal backends.
All implement the common NodeBackend interface.
"""

from __future__ import annotations

from nlm.adapters.base import NodeBackend
from nlm.adapters.bcm import BCMAdapter
from nlm.adapters.maas import MAASAdapter
from nlm.adapters.kubernetes import KubernetesAdapter
from nlm.adapters.bare_metal import BareMetalAdapter

__all__ = [
    "NodeBackend",
    "BCMAdapter",
    "MAASAdapter",
    "KubernetesAdapter",
    "BareMetalAdapter",
    "get_adapter",
]


def get_adapter(backend_type: str, config: dict) -> NodeBackend:
    """Factory: return the appropriate adapter for the backend type."""
    adapters = {
        "bcm": BCMAdapter,
        "maas": MAASAdapter,
        "kubernetes": KubernetesAdapter,
        "bare_metal": BareMetalAdapter,
    }
    cls = adapters.get(backend_type)
    if cls is None:
        raise ValueError(f"Unknown backend type: {backend_type}")
    return cls(config)
