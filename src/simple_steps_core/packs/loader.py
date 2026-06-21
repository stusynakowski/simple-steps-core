import importlib


def load_pack_module(module_path: str):
    """Import a pack module so decorated operations can self-register."""
    return importlib.import_module(module_path)
