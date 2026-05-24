"""
In-memory state for cloud demo (when database is omitted).
"""
from typing import Dict, Any

class DemoState:
    def __getitem__(self, key):
        import modal
        try:
            d = modal.Dict.from_name("lenai-demo-state", create_if_missing=True)
            return d.get(key)
        except Exception:
            return None
            
    def __setitem__(self, key, value):
        import modal
        try:
            d = modal.Dict.from_name("lenai-demo-state", create_if_missing=True)
            d[key] = value
        except Exception:
            pass

    def __contains__(self, key):
        return self[key] is not None

FAKE_JOBS = DemoState()
