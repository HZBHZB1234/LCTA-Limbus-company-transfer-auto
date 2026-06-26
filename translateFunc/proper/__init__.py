"""translateFunc.proper — Proper noun utilities and JP/EN cross-validation."""
from translateFunc.proper.flat import (
    flatten_dict_enhanced,
    update_dict_with_flattened,
    get_value_by_path,
)
from translateFunc.proper.analyze import extract_contexts

__all__ = [
    "flatten_dict_enhanced",
    "update_dict_with_flattened",
    "get_value_by_path",
    "extract_contexts",
]
