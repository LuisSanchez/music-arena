# Intentionally empty of generate imports — loading generate.py pulls NumPy
# into the API process. Healthchecks and idle reclaim must stay cheap.
__all__ = ["generate_track", "generate_match", "generate_radio_track"]


def __getattr__(name: str):
    if name in __all__:
        from . import generate as _generate

        return getattr(_generate, name)
    raise AttributeError(name)