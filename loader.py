"""
Simple script loader for sandusr.
Scans scripts/ directory, finds folders with meta.json,
imports their main.py and calls register(client).
"""
import os
import sys
import importlib.util
import traceback
import logging

from config import Config

logger = logging.getLogger("sandusr.loader")


def load_all_scripts(client):
    """Load all scripts. Returns list of loaded script names."""
    scripts_dir = Config.SCRIPTS_DIR
    if not os.path.isdir(scripts_dir):
        return []

    loaded = []

    # First load _utils.py so all scripts can import it
    utils_path = os.path.join(scripts_dir, "_utils.py")
    if os.path.exists(utils_path):
        # Just make sure the scripts package is importable
        scripts_parent = os.path.dirname(scripts_dir)
        if scripts_parent not in sys.path:
            sys.path.insert(0, scripts_parent)

    for name in sorted(os.listdir(scripts_dir)):
        script_dir = os.path.join(scripts_dir, name)

        # Skip non-directories and special dirs
        if not os.path.isdir(script_dir) or name.startswith("_"):
            continue

        main_file = os.path.join(script_dir, "main.py")
        if not os.path.exists(main_file):
            continue

        try:
            module_name = f"sandusr_{name}"
            spec = importlib.util.spec_from_file_location(module_name, main_file)
            if spec is None or spec.loader is None:
                logger.error(f"Failed to create spec for {name}")
                continue

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Call register(client) to add handlers
            if hasattr(module, "register") and callable(module.register):
                module.register(client)
                logger.info(f"Loaded: {name}")

            if hasattr(module, "on_load") and callable(module.on_load):
                module.on_load()

            loaded.append(name)

            # Load addons if they exist
            addons_dir = os.path.join(script_dir, "addons")
            if os.path.isdir(addons_dir):
                for addon_file in sorted(os.listdir(addons_dir)):
                    if not addon_file.endswith(".py"):
                        continue
                    addon_path = os.path.join(addons_dir, addon_file)
                    try:
                        addon_name = f"sandusr_{name}_addon_{addon_file[:-3]}"
                        aspec = importlib.util.spec_from_file_location(addon_name, addon_path)
                        if aspec and aspec.loader:
                            amodule = importlib.util.module_from_spec(aspec)
                            sys.modules[addon_name] = amodule
                            aspec.loader.exec_module(amodule)

                            if hasattr(amodule, "register") and callable(amodule.register):
                                amodule.register(client)
                            if hasattr(amodule, "on_load") and callable(amodule.on_load):
                                amodule.on_load()

                            logger.info(f"  Addon: {name}/{addon_file}")
                    except Exception as e:
                        logger.error(f"  Addon failed {name}/{addon_file}: {e}")
                        traceback.print_exc()

        except Exception as e:
            logger.error(f"Failed to load {name}: {e}")
            traceback.print_exc()
            sys.modules.pop(f"sandusr_{name}", None)

    return loaded
