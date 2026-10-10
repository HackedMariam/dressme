"""
Change ONE macro body-shape parameter on an existing MPFB2 avatar and export GLB.

Verified against MPFB2 (github.com/makehumancommunity/mpfb2) official docs, source
and script_samples -- no invented APIs:

  - HumanObjectProperties.set_value()        docs/entities/objectproperties.md
  - TargetService.reapply_macro_details()    docs/services/targetservice.md
  - ExportService.create_character_copy()    script_samples/10_complete_character_export_fbx.py
  - ExportService.bake_modifiers_remove_helpers()
  - TargetService.bake_targets()             docs/services/targetservice.md
  - ObjectService.find_object_of_type_amongst_nearest_relatives() / get_list_of_children()
  - dynamic_import() quirk                   script_samples/ (required for ALL MPFB scripts)

HOW TO RUN: inside Blender 4.2+ with the MPFB2 extension enabled:
  1. Open the .blend file containing your avatar.
  2. Open the "Scripting" workspace, click "+ New", paste this whole file, press
     the "Run Script" (play) button. Or use File > Run Python Script...
  3. Watch the System Console (Window > Toggle System Console) for the print output.
The original character in the scene is NOT modified in a destructive way except
that its macro parameter is changed; the exported geometry is a separate copy.
"""

# ------------------------------------------------------------------------------------------
# dynamic_import: copy/pasted quirk from the official MPFB script samples. Blender
# extensions end up at unknown places in the module hierarchy, so normal imports fail.
# ------------------------------------------------------------------------------------------
import importlib
import sys


def dynamic_import(absolute_package_str, key):
    """Quirk to get around blender's extension format's requirement that all imports must be relative"""
    for amod in sys.modules:
        if amod.endswith(absolute_package_str):
            mpfb_mod = importlib.import_module(amod)
            if not hasattr(mpfb_mod, key):
                raise AttributeError(f"Module {amod} does not have attribute {key}")
            return getattr(mpfb_mod, key)
    raise ValueError(f"No module found with name ending in {absolute_package_str}")


# ------------------------------------------------------------------------------------------
# Verified MPFB imports
# ------------------------------------------------------------------------------------------
GeneralObjectProperties = dynamic_import("mpfb.entities.objectproperties", "GeneralObjectProperties")
HumanObjectProperties = dynamic_import("mpfb.entities.objectproperties", "HumanObjectProperties")
TargetService = dynamic_import("mpfb.services.targetservice", "TargetService")
ExportService = dynamic_import("mpfb.services.exportservice", "ExportService")
ObjectService = dynamic_import("mpfb.services.objectservice", "ObjectService")

import bpy  # noqa: E402
import os  # noqa: E402

# ------------------------------------------------------------------------------------------
# CONFIGURE HERE
# Valid PARAM names (all floats, 0.0 - 1.0, verified in docs/entities/objectproperties.md):
#   "gender" (0=female, 1=male), "age", "muscle", "weight", "height",
#   "proportions", "cupsize", "firmness"
# ------------------------------------------------------------------------------------------
PARAM = "weight"       # <-- the ONE body-shape parameter to change
NEW_VALUE = 0.8        # <-- new value (0.0 - 1.0); 0.5 is MPFB's neutral default
OUTPUT_PATH = r"C:\Users\maria\Desktop\5eme esprit\Dressme\public\models\avatar.glb"
# ------------------------------------------------------------------------------------------


def find_basemesh():
    """Return the first MPFB basemesh in the scene (active object preferred)."""
    obj = bpy.context.active_object
    if obj is not None and GeneralObjectProperties.get_value("object_type", entity_reference=obj) == "Basemesh":
        return obj
    for candidate in bpy.data.objects:
        if GeneralObjectProperties.get_value("object_type", entity_reference=candidate) == "Basemesh":
            return candidate
    return None


def bake_shape_keys_if_any(obj):
    """Collapse all shape keys (morph targets) on a mesh into static geometry."""
    if obj is not None and obj.type == "MESH" and obj.data.shape_keys \
            and len(obj.data.shape_keys.key_blocks) > 0:
        TargetService.bake_targets(obj)


def main():
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    basemesh = find_basemesh()
    if basemesh is None:
        raise RuntimeError(
            "No MPFB basemesh found in this scene. "
            "Open the .blend file that contains your avatar and run the script again.")

    if not HumanObjectProperties.has_key(PARAM):
        raise ValueError(
            f"'{PARAM}' is not a valid MPFB human property. "
            "Valid names: gender, age, muscle, weight, height, proportions, cupsize, firmness")

    old_value = HumanObjectProperties.get_value(PARAM, default_value=None, entity_reference=basemesh)
    print(f"[MPFB script] Changing {PARAM} on '{basemesh.name}': {old_value} -> {NEW_VALUE}")

    # 1. Set the macro parameter on the basemesh, then recompute all morph targets
    HumanObjectProperties.set_value(PARAM, NEW_VALUE, entity_reference=basemesh)
    TargetService.reapply_macro_details(basemesh)

    # 2. Stage a deep copy for export so the on-screen character stays editable
    export_root = ExportService.create_character_copy(basemesh, name_suffix="_export")
    export_basemesh = ObjectService.find_object_of_type_amongst_nearest_relatives(export_root, "Basemesh")
    ExportService.bake_modifiers_remove_helpers(
        export_basemesh,
        bake_masks=True,
        bake_subdiv=True,
        remove_helpers=True,
        also_proxy=True)

    # 3. Bake ALL shape keys into static geometry (basemesh + any children such as
    #    the body proxy) so the GLB contains a single static mesh, no morph targets.
    bake_shape_keys_if_any(export_basemesh)
    for child in ObjectService.get_list_of_children(export_root):
        bake_shape_keys_if_any(child)

    # 4. Select only the export hierarchy and write the GLB with Blender's own
    #    Khronos glTF exporter (bundled with Blender, no addon needed).
    bpy.ops.object.select_all(action="DESELECT")
    export_root.select_set(True)
    for child in ObjectService.get_list_of_children(export_root):
        child.select_set(True)
    bpy.context.view_layer.objects.active = export_root

    out_dir = os.path.dirname(OUTPUT_PATH)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    bpy.ops.export_scene.gltf(
        filepath=OUTPUT_PATH,
        export_format="GLB",
        use_selection=True)

    print(f"[MPFB script] SUCCESS: wrote {OUTPUT_PATH}")
    print("[MPFB script] Restart/refresh the DressMe dev server page to see the new model.")


main()
