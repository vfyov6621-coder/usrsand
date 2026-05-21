"""
Simple script loader for sandusr.
Scans scripts/ directory, finds folders with main.py,
imports and calls register(client).
Supports load/unload/reload of individual scripts.
"""
import os
import sys
import importlib.util
import traceback
import logging

from config import Config

logger = logging.getLogger("sandusr.loader")

# Global registry of loaded scripts: {script_name: module}
_loaded_modules = {}
_loaded_addons = {}  # {script_name: {addon_file: module}}


def get_loaded():
    """Get dict of all loaded modules."""
    return _loaded_modules


def get_loaded_names():
    """Get list of loaded script names."""
    return list(_loaded_modules.keys())


def get_available():
    """Get list of all available script names (folders with main.py)."""
    scripts_dir = Config.SCRIPTS_DIR
    if not os.path.isdir(scripts_dir):
        return []

    available = []
    for name in sorted(os.listdir(scripts_dir)):
        script_dir = os.path.join(scripts_dir, name)
        if not os.path.isdir(script_dir) or name.startswith("_"):
            continue
        main_file = os.path.join(script_dir, "main.py")
        if os.path.exists(main_file):
            available.append(name)
    return available


def _read_autostart():
    """Read autostart config. Returns set of script names, or None if all should load."""
    autostart_file = os.path.join(Config.SCRIPTS_DIR, "autostart.json")
    if not os.path.exists(autostart_file):
        return None  # None = load all (default)
    try:
        import json
        with open(autostart_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        mode = data.get("mode", "all")
        if mode == "all":
            return None
        return set(data.get("scripts", []))
    except Exception:
        return None


def load_all_scripts(client):
    """Load all scripts at startup. Returns list of loaded script names."""
    available = get_available()
    loaded = []

    # Check autostart config
    autostart = _read_autostart()
    if autostart is not None:
        # Only load scripts in the autostart set
        available = [s for s in available if s in autostart]
        if len(available) < len(autostart):
            missing = autostart - set(available)
            for m in missing:
                logger.warning(f"Autostart script not found: {m}")

    # Make sure scripts package is importable
    scripts_parent = os.path.dirname(Config.SCRIPTS_DIR)
    if scripts_parent not in sys.path:
        sys.path.insert(0, scripts_parent)

    for name in available:
        result = load_script(name, client)
        if result["success"]:
            loaded.append(name)

    return loaded


def load_script(script_name, client):
    """Load a single script by name. Returns dict with success/error."""
    if script_name in _loaded_modules:
        return {"success": False, "error": f"'{script_name}' уже загружен"}

    main_file = os.path.join(Config.SCRIPTS_DIR, script_name, "main.py")
    if not os.path.exists(main_file):
        return {"success": False, "error": f"'{script_name}' не найден (нет main.py)"}

    # Ensure import path
    scripts_parent = os.path.dirname(Config.SCRIPTS_DIR)
    if scripts_parent not in sys.path:
        sys.path.insert(0, scripts_parent)

    try:
        module_name = f"sandusr_{script_name}"

        # Clean old module if exists
        if module_name in sys.modules:
            del sys.modules[module_name]

        spec = importlib.util.spec_from_file_location(module_name, main_file)
        if spec is None or spec.loader is None:
            return {"success": False, "error": f"spec error для {script_name}"}

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # Call register(client) to add handlers
        if hasattr(module, "register") and callable(module.register):
            module.register(client)
            logger.info(f"  -> register() вызван для {script_name}")

        if hasattr(module, "on_load") and callable(module.on_load):
            module.on_load()

        _loaded_modules[script_name] = module
        logger.info(f"Loaded: {script_name}")

        # Load addons if they exist
        addons_dir = os.path.join(Config.SCRIPTS_DIR, script_name, "addons")
        addons_loaded = []
        if os.path.isdir(addons_dir):
            for addon_file in sorted(os.listdir(addons_dir)):
                if not addon_file.endswith(".py"):
                    continue
                addon_path = os.path.join(addons_dir, addon_file)
                try:
                    addon_name = f"sandusr_{script_name}_addon_{addon_file[:-3]}"
                    aspec = importlib.util.spec_from_file_location(addon_name, addon_path)
                    if aspec and aspec.loader:
                        amodule = importlib.util.module_from_spec(aspec)
                        sys.modules[addon_name] = amodule
                        aspec.loader.exec_module(amodule)

                        if hasattr(amodule, "register") and callable(amodule.register):
                            amodule.register(client)
                        if hasattr(amodule, "on_load") and callable(amodule.on_load):
                            amodule.on_load()

                        _loaded_addons.setdefault(script_name, {})[addon_file] = amodule
                        addons_loaded.append(addon_file)
                        logger.info(f"  Addon: {script_name}/{addon_file}")
                except Exception as e:
                    logger.error(f"  Addon failed {script_name}/{addon_file}: {e}")

        return {"success": True, "addons": addons_loaded}

    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        logger.error(f"Failed to load {script_name}: {error_msg}")
        traceback.print_exc()
        mod_name = f"sandusr_{script_name}"
        sys.modules.pop(mod_name, None)
        return {"success": False, "error": error_msg}


def unload_script(script_name):
    """Unload a single script by name. Returns dict with success/error."""
    if script_name not in _loaded_modules:
        return {"success": False, "error": f"'{script_name}' не загружен"}

    module = _loaded_modules[script_name]

    try:
        # 1. Unload addons
        addons = _loaded_addons.pop(script_name, {})
        for addon_file, addon_module in addons.items():
            fn = getattr(addon_module, "on_unload", None)
            if fn and callable(fn):
                try:
                    fn()
                except Exception:
                    pass
            addon_name = f"sandusr_{script_name}_addon_{addon_file[:-3]}"
            sys.modules.pop(addon_name, None)

        # 2. on_unload main module
        fn = getattr(module, "on_unload", None)
        if fn and callable(fn):
            try:
                fn()
            except Exception:
                pass

        # 3. Remove from sys.modules
        mod_name = f"sandusr_{script_name}"
        sys.modules.pop(mod_name, None)

        # 4. Remove from registry
        del _loaded_modules[script_name]

        logger.info(f"Unloaded: {script_name}")
        return {"success": True}

    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        logger.error(f"Failed to unload {script_name}: {error_msg}")
        return {"success": False, "error": error_msg}


def reload_script(script_name, client):
    """Reload a single script (unload + load). Returns dict with success/error."""
    unload_result = unload_script(script_name)
    if not unload_result["success"]:
        # If not loaded, just try loading
        pass
    return load_script(script_name, client)


def get_script_info(script_name):
    """Get info about a script (loaded or not)."""
    main_file = os.path.join(Config.SCRIPTS_DIR, script_name, "main.py")
    if not os.path.exists(main_file):
        return None

    from datetime import datetime
    info = {
        "id": script_name,
        "name": script_name,
        "loaded": script_name in _loaded_modules,
        "size": os.path.getsize(main_file),
    }

    try:
        with open(main_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        info["lines"] = len(lines)
        info["modified"] = datetime.fromtimestamp(
            os.path.getmtime(main_file)
        ).strftime("%Y-%m-%d %H:%M:%S")

        # Try to get description from first docstring
        docstring = ""
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                docstring = stripped.lstrip('"\'')
                break
        if docstring:
            info["description"] = docstring[:100]
    except Exception:
        info["lines"] = 0

    # Addons
    addons_dir = os.path.join(Config.SCRIPTS_DIR, script_name, "addons")
    addons = []
    if os.path.isdir(addons_dir):
        for f in sorted(os.listdir(addons_dir)):
            if f.endswith(".py"):
                addons.append(f)
    info["addons"] = addons

    return info
