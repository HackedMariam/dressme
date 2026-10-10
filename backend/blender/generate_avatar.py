"""
Generate a body-shaped GLB from the avatar.blend scene using MPFB2.

Run by the FastAPI backend (also runnable by hand):

  blender --background "<avatar.blend>" --python generate_avatar.py -- \
      --params "<params.json>" --output "<output.glb>"

All MPFB APIs used here are verified against the official MPFB2 docs/script
samples (github.com/makehumancommunity/mpfb2):

  - HumanObjectProperties.set_value()          docs/entities/objectproperties.md
  - TargetService.reapply_macro_details()      docs/services/targetservice.md
  - TargetService.bake_targets()               docs/services/targetservice.md
  - ExportService.create_character_copy()      script_samples/10
  - ExportService.bake_modifiers_remove_helpers()
  - ObjectService.find_object_of_type_amongst_nearest_relatives()

The dynamic_import quirk below is mandatory for ALL MPFB scripts (Blender
extensions live at unknown module paths).

Parameters (0.0 - 1.0 each; only whitelisted names are accepted):
  gender age muscle weight height proportions cupsize firmness
"""

import argparse
import importlib
import json
import os
import sys
import traceback

import bpy


def dynamic_import(absolute_package_str, key):
    """Quirk to get around blender's extension format's requirement that all imports must be relative"""
    for amod in sys.modules:
        if amod.endswith(absolute_package_str):
            mpfb_mod = importlib.import_module(amod)
            if not hasattr(mpfb_mod, key):
                raise AttributeError(f"Module {amod} does not have attribute {key}")
            return getattr(mpfb_mod, key)
    raise ValueError(f"No module found with name ending in {absolute_package_str}")


ALLOWED_PARAMS = {
    "gender", "age", "muscle", "weight",
    "height", "proportions", "cupsize", "firmness",
}


def emit(result):
    print("AVATAR_RESULT " + json.dumps(result), flush=True)


def find_basemesh(GeneralObjectProperties):
    obj = bpy.context.active_object
    if obj is not None and GeneralObjectProperties.get_value("object_type", entity_reference=obj) == "Basemesh":
        return obj
    for candidate in bpy.data.objects:
        if GeneralObjectProperties.get_value("object_type", entity_reference=candidate) == "Basemesh":
            return candidate
    return None


def bake_shape_keys_if_any(TargetService, obj):
    if obj is not None and obj.type == "MESH" and obj.data.shape_keys \
            and len(obj.data.shape_keys.key_blocks) > 0:
        TargetService.bake_targets(obj)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--params", required=True)
    parser.add_argument("--output", required=True)
    args, _unknown = parser.parse_known_args(sys.argv[sys.argv.index("--") + 1:])

    with open(args.params, "r", encoding="utf-8") as f:
        params = json.load(f)

    unknown = [k for k in params if k not in ALLOWED_PARAMS]
    if unknown:
        raise ValueError(f"Unsupported parameters: {unknown}. Allowed: {sorted(ALLOWED_PARAMS)}")
    for k, v in params.items():
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not (0.0 <= float(v) <= 1.0):
            raise ValueError(f"Parameter {k} must be a number between 0.0 and 1.0, got {v!r}")

    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    GeneralObjectProperties = dynamic_import("mpfb.entities.objectproperties", "GeneralObjectProperties")
    HumanObjectProperties = dynamic_import("mpfb.entities.objectproperties", "HumanObjectProperties")
    TargetService = dynamic_import("mpfb.services.targetservice", "TargetService")
    ExportService = dynamic_import("mpfb.services.exportservice", "ExportService")
    ObjectService = dynamic_import("mpfb.services.objectservice", "ObjectService")

    basemesh = find_basemesh(GeneralObjectProperties)
    if basemesh is None:
        raise RuntimeError("No MPFB basemesh found in the loaded scene")

    applied = {}
    for key, value in params.items():
        HumanObjectProperties.set_value(key, float(value), entity_reference=basemesh)
        applied[key] = float(value)
    TargetService.reapply_macro_details(basemesh)

    export_root = ExportService.create_character_copy(basemesh, name_suffix="_gen")
    export_basemesh = ObjectService.find_object_of_type_amongst_nearest_relatives(export_root, "Basemesh")
    ExportService.bake_modifiers_remove_helpers(
        export_basemesh,
        bake_masks=True,
        bake_subdiv=True,
        remove_helpers=True,
        also_proxy=True)

    bake_shape_keys_if_any(TargetService, export_basemesh)
    for child in ObjectService.get_list_of_children(export_root):
        bake_shape_keys_if_any(TargetService, child)

    bpy.ops.object.select_all(action="DESELECT")
    export_root.select_set(True)
    for child in ObjectService.get_list_of_children(export_root):
        child.select_set(True)
    bpy.context.view_layer.objects.active = export_root

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    bpy.ops.export_scene.gltf(
        filepath=args.output,
        export_format="GLB",
        use_selection=True)

    size = os.path.getsize(args.output)
    if size <= 0:
        raise RuntimeError("Export produced an empty file")

    emit({"ok": True, "params_applied": applied, "output": args.output, "bytes": size})


try:
    main()
except Exception as e:
    traceback.print_exc()
    emit({"ok": False, "error": f"{type(e).__name__}: {e}"})
    sys.exit(1)
