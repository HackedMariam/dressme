"""
Audit the MPFB2 avatar scene so we have a known, stable format for garment fitting.

Run by hand:

  blender --background "<avatar.blend>" --python audit_avatar.py

Prints a single AUDIT_RESULT JSON line plus a human-readable report.
"""

import json
import sys
import traceback

import bpy


def dynamic_import(absolute_package_str, key):
    import importlib
    for amod in sys.modules:
        if amod.endswith(absolute_package_str):
            return getattr(importlib.import_module(amod), key)
    raise ValueError(f"No module found with name ending in {absolute_package_str}")


def emit(result):
    print("AUDIT_RESULT " + json.dumps(result), flush=True)


def obj_summary(obj):
    data = {
        "name": obj.name,
        "type": obj.type,
        "parent": obj.parent.name if obj.parent else None,
    }
    if obj.type == "MESH":
        me = obj.data
        data["verts"] = len(me.vertices)
        data["edges"] = len(me.edges)
        data["polys"] = len(me.polygons)
        data["tris"] = sum(len(p.vertices) - 2 for p in me.polygons)
        data["uv_layers"] = [uv.name for uv in me.uv_layers]
        data["materials"] = [m.name if m else None for m in obj.data.materials]
        data["shape_keys"] = (
            [kb.name for kb in me.shape_keys.key_blocks]
            if me.shape_keys and me.shape_keys.key_blocks
            else []
        )
        data["shape_key_values"] = (
            {kb.name: round(kb.value, 4) for kb in me.shape_keys.key_blocks}
            if me.shape_keys and me.shape_keys.key_blocks
            else {}
        )
        data["vertex_groups"] = [vg.name for vg in obj.vertex_groups]
        data["modifiers"] = [(m.type, m.name) for m in obj.modifiers]
        data["mesh_users"] = me.users
    if obj.type == "ARMATURE":
        data["bones"] = len(obj.data.bones)
        data["bone_names"] = [b.name for b in obj.data.bones]
    data["location"] = [round(v, 4) for v in obj.location]
    data["rotation_euler"] = [round(v, 4) for v in obj.rotation_euler]
    data["scale"] = [round(v, 4) for v in obj.scale]
    data["dimensions"] = [round(v, 4) for v in obj.dimensions]
    data["matrix_world"] = [round(v, 4) for row in obj.matrix_world for v in row]
    bb = [obj.matrix_world @ __import__("mathutils").Vector(c) for c in obj.bound_box]
    data["world_bbox_min"] = [round(min(v[i] for v in bb), 4) for i in range(3)]
    data["world_bbox_max"] = [round(max(v[i] for v in bb), 4) for i in range(3)]
    return data


def main():
    GeneralObjectProperties = dynamic_import(
        "mpfb.entities.objectproperties", "GeneralObjectProperties"
    )
    HumanObjectProperties = dynamic_import(
        "mpfb.entities.objectproperties", "HumanObjectProperties"
    )

    report = {
        "blender_version": bpy.app.version_string,
        "scene_objects": [obj_summary(o) for o in bpy.data.objects],
        "armatures": [o.name for o in bpy.data.objects if o.type == "ARMATURE"],
    }

    basemesh = None
    for candidate in bpy.data.objects:
        try:
            if GeneralObjectProperties.get_value(
                "object_type", entity_reference=candidate
            ) == "Basemesh":
                basemesh = candidate
                break
        except Exception:
            continue

    if basemesh is not None:
        report["basemesh_name"] = basemesh.name
        report["basemesh_macro_params"] = {}
        for p in [
            "gender", "age", "muscle", "weight", "height",
            "proportions", "cupsize", "firmness",
        ]:
            try:
                if HumanObjectProperties.has_key(p):
                    report["basemesh_macro_params"][p] = HumanObjectProperties.get_value(
                        p, default_value=None, entity_reference=basemesh
                    )
            except Exception as e:
                report["basemesh_macro_params"][p] = f"ERR {e}"

    emit(report)


try:
    main()
except Exception as e:
    traceback.print_exc()
    emit({"ok": False, "error": f"{type(e).__name__}: {e}"})
    sys.exit(1)
