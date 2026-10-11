"""
Generate a *dressed* GLB: the MPFB2 avatar plus fitted garments, exported with
Blender's glTF/Khronos exporter.

Why garments are built from the body surface
--------------------------------------------
The audit (backend/blender/audit_avatar.py) showed the avatar.mesh is a static,
shape-key-driven MPFB basemesh: the export pipeline bakes the shape keys, so the
GLB has no skeleton and no morph targets. A garment therefore cannot "follow" the
body through skinning. Instead we build each garment *from the current body
surface* at generation time:

  1. classify every skin vertex to the nearest anatomical bone segment, where the
     segment endpoints come from MPFB's own joint-cube landmarks (joint-pelvis,
     joint-l-shoulder, ...). These landmarks live on the basemesh itself.
  2. keep the vertices whose segment belongs to the garment's region,
  3. offset those vertices outward along their normals, and solidify.

Because the garment is re-derived from the *actual generated body*, it fits every
body-shape configuration by construction (no external garment asset, no license
concerns -- the assets are created here).

Run (same contract as generate_avatar.py):

  blender --background "<avatar.blend>" --python generate_dressed_avatar.py -- \
      --params "<params.json>" --outfit "tshirt,trousers,jacket" --output "<out.glb>"
"""

import argparse
import importlib
import json
import os
import sys
import traceback

import bmesh
import bpy
from mathutils import Vector

ALLOWED_PARAMS = {
    "gender", "age", "muscle", "weight",
    "height", "proportions", "cupsize", "firmness",
}

# ---------------------------------------------------------------------------
# Garment catalogue. Colors are linear-ish sRGB approximations; each garment is
# a body-derived shell. `offset` is how far the shell floats off the skin (m).
# ---------------------------------------------------------------------------
GARMENTS = {
    "tshirt": {
        "label": "T-Shirt",
        "color": (0.20, 0.33, 0.55),     # steel blue
        "offset": 0.010,
        "thickness": 0.004,
        "region": lambda z, p: {
            "hips", "spine_low", "spine_mid", "spine_up", "chest",
            "shoulder_L", "shoulder_R", "upperarm_L", "upperarm_R",
        },
        "fill": {"thigh_L", "thigh_R"},   # close the hem ring at hip height
        "hem_z": lambda p: p["pelvis"].z,
        "min_z": lambda p: p["pelvis"].z,
        "roughness": 0.85,
    },
    "trousers": {
        "label": "Trousers",
        "color": (0.16, 0.16, 0.20),     # charcoal
        "offset": 0.012,
        "thickness": 0.005,
        "region": lambda z, p: {
            "hips", "thigh_L", "thigh_R", "shin_L", "shin_R",
        },
        "fill": set(),
        "hem_z": lambda p: p["pelvis"].z,
        "min_z": lambda p: 0.0,
        "roughness": 0.9,
    },
    "jacket": {
        "label": "Jacket",
        "color": (0.55, 0.34, 0.20),     # camel
        "offset": 0.026,
        "thickness": 0.006,
        "region": lambda z, p: {
            "hips", "spine_low", "spine_mid", "spine_up", "chest",
            "shoulder_L", "shoulder_R", "upperarm_L", "upperarm_R",
            "forearm_L", "forearm_R",
        },
        "fill": set(),
        "hem_z": lambda p: p["pelvis"].z,
        "min_z": lambda p: p["pelvis"].z - 0.02,
        "roughness": 0.7,
    },
}


def dynamic_import(absolute_package_str, key):
    for amod in sys.modules:
        if amod.endswith(absolute_package_str):
            mpfb_mod = importlib.import_module(amod)
            if not hasattr(mpfb_mod, key):
                raise AttributeError(f"Module {amod} does not have attribute {key}")
            return getattr(mpfb_mod, key)
    raise ValueError(f"No module found with name ending in {absolute_package_str}")


def emit(result):
    print("AVATAR_RESULT " + json.dumps(result), flush=True)


# ---------------------------------------------------------------------------
# Landmarks: MPFB joint cubes. We read them from an evaluated copy with the
# "Hide helpers" mask disabled (the mask otherwise removes the joint vertices).
# ---------------------------------------------------------------------------
def read_landmarks(basemesh):
    saved = [(m, m.show_viewport, m.show_render) for m in basemesh.modifiers]
    for m, _vp, _rn in saved:
        m.show_viewport = False
        m.show_render = False

    idx_to_name = {vg.index: vg.name for vg in basemesh.vertex_groups}
    depsgraph = bpy.context.evaluated_depsgraph_get()
    ev = basemesh.evaluated_get(depsgraph)
    ev_mesh = ev.to_mesh()

    acc = {}
    for v in ev_mesh.vertices:
        for g in basemesh.data.vertices[v.index].groups:
            name = idx_to_name.get(g.group)
            if name and name.startswith("joint-") and g.weight > 0.3:
                acc.setdefault(name, []).append(ev.matrix_world @ v.co)
    ev.to_mesh_clear()

    for m, vp, rn in saved:
        m.show_viewport = vp
        m.show_render = rn

    landmarks = {}
    for name, pts in acc.items():
        s = Vector((0.0, 0.0, 0.0))
        for p in pts:
            s += p
        landmarks[name] = s / len(pts)
    return landmarks


def _lm(landmarks, name):
    if name not in landmarks:
        raise RuntimeError(f"Missing landmark '{name}' on the avatar rig")
    return landmarks[name]


def build_segments(landmarks):
    """Anatomical bone segments as (label, a, b) using rig landmarks."""
    segs = [
        ("hips", _lm(landmarks, "pelvis"), _lm(landmarks, "spine-4")),
        ("spine_low", _lm(landmarks, "spine-4"), _lm(landmarks, "spine-3")),
        ("spine_mid", _lm(landmarks, "spine-3"), _lm(landmarks, "spine-2")),
        ("spine_up", _lm(landmarks, "spine-2"), _lm(landmarks, "spine-1")),
        ("chest", _lm(landmarks, "spine-1"), _lm(landmarks, "neck")),
        ("neck", _lm(landmarks, "neck"), _lm(landmarks, "head")),
    ]
    for side, sfx in (("l", "_L"), ("r", "_R")):
        segs += [
            (f"shoulder{sfx}", _lm(landmarks, f"{side}-clavicle"), _lm(landmarks, f"{side}-shoulder")),
            (f"upperarm{sfx}", _lm(landmarks, f"{side}-shoulder"), _lm(landmarks, f"{side}-elbow")),
            (f"forearm{sfx}", _lm(landmarks, f"{side}-elbow"), _lm(landmarks, f"{side}-hand")),
            (f"hand{sfx}", _lm(landmarks, f"{side}-hand"), _lm(landmarks, f"{side}-hand-2")),
            (f"thigh{sfx}", _lm(landmarks, f"{side}-upper-leg"), _lm(landmarks, f"{side}-knee")),
            (f"shin{sfx}", _lm(landmarks, f"{side}-knee"), _lm(landmarks, f"{side}-ankle")),
            (f"foot{sfx}", _lm(landmarks, f"{side}-ankle"), _lm(landmarks, f"{side}-foot-2")),
        ]
    return segs


def point_segment_distance(p, a, b):
    ab = b - a
    denom = ab.dot(ab)
    if denom < 1e-12:
        return (p - a).length
    t = max(0.0, min(1.0, (p - a).dot(ab) / denom))
    return (p - (a + ab * t)).length


def classify_vertices(points, segments):
    labels = []
    for p in points:
        best_label = None
        best_d = 1e18
        for label, a, b in segments:
            d = point_segment_distance(p, a, b)
            if d < best_d:
                best_d = d
                best_label = label
        labels.append(best_label)
    return labels


# ---------------------------------------------------------------------------
# Material + object helpers
# ---------------------------------------------------------------------------
def make_material(name, color, roughness=0.8):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = roughness
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = 0.0
    mat.diffuse_color = (*color, 1.0)
    return mat


def build_garment(body_obj, landmarks, garment_id):
    cfg = GARMENTS[garment_id]
    segments = build_segments(landmarks)

    src = body_obj.data
    bm = bmesh.new()
    bm.from_mesh(src)
    bm.verts.ensure_lookup_table()

    points = [(body_obj.matrix_world @ v.co) for v in bm.verts]
    labels = classify_vertices(points, segments)

    region = cfg["region"](0.0, landmarks)
    fill = cfg["fill"]
    hem_z = cfg["hem_z"](landmarks)
    min_z = cfg["min_z"](landmarks)

    keep = []
    for i, v in enumerate(bm.verts):
        label = labels[i]
        world_z = points[i].z
        include = (label in region or (label in fill and world_z > hem_z)) and world_z >= min_z
        keep.append(include)
        v.select = include

    bm.verts.ensure_lookup_table()
    to_delete = [v for v, k in zip(bm.verts, keep) if not k]
    bmesh.ops.delete(bm, geom=to_delete, context="VERTS")

    if len(bm.verts) == 0:
        raise RuntimeError(f"Garment '{garment_id}' selected no vertices")

    bm.normal_update()
    offset = cfg["offset"]
    for v in bm.verts:
        v.co = v.co + v.normal * offset

    new_mesh = bpy.data.meshes.new(f"garment_{garment_id}")
    bm.to_mesh(new_mesh)
    bm.free()

    new_mesh.materials.append(
        make_material(f"mat_{garment_id}", cfg["color"], cfg["roughness"])
    )
    for poly in new_mesh.polygons:
        poly.use_smooth = True

    obj = bpy.data.objects.new(f"garment_{garment_id}", new_mesh)
    obj.matrix_world = body_obj.matrix_world.copy()
    bpy.context.scene.collection.objects.link(obj)

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    solid = obj.modifiers.new("Solidify", "SOLIDIFY")
    solid.thickness = cfg["thickness"]
    solid.offset = 1.0
    bpy.ops.object.modifier_apply(modifier=solid.name)
    return obj


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--params", required=True)
    parser.add_argument("--outfit", default="tshirt")
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

    outfit = [g.strip() for g in args.outfit.split(",") if g.strip()]
    unknown_g = [g for g in outfit if g not in GARMENTS]
    if unknown_g:
        raise ValueError(f"Unsupported garments: {unknown_g}. Allowed: {sorted(GARMENTS)}")

    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    GeneralObjectProperties = dynamic_import("mpfb.entities.objectproperties", "GeneralObjectProperties")
    HumanObjectProperties = dynamic_import("mpfb.entities.objectproperties", "HumanObjectProperties")
    TargetService = dynamic_import("mpfb.services.targetservice", "TargetService")
    ExportService = dynamic_import("mpfb.services.exportservice", "ExportService")
    ObjectService = dynamic_import("mpfb.services.objectservice", "ObjectService")

    basemesh = None
    for candidate in bpy.data.objects:
        try:
            if GeneralObjectProperties.get_value("object_type", entity_reference=candidate) == "Basemesh":
                basemesh = candidate
                break
        except Exception:
            continue
    if basemesh is None:
        raise RuntimeError("No MPFB basemesh found in the loaded scene")

    for key, value in params.items():
        HumanObjectProperties.set_value(key, float(value), entity_reference=basemesh)
    TargetService.reapply_macro_details(basemesh)
    bpy.context.view_layer.update()

    landmarks = read_landmarks(basemesh)
    landmarks = {name.replace("joint-", ""): p for name, p in landmarks.items()}

    export_root = ExportService.create_character_copy(basemesh, name_suffix="_gen")
    export_basemesh = ObjectService.find_object_of_type_amongst_nearest_relatives(export_root, "Basemesh")
    ExportService.bake_modifiers_remove_helpers(
        export_basemesh,
        bake_masks=True,
        bake_subdiv=True,
        remove_helpers=True,
        also_proxy=True)

    def bake_keys(obj):
        if obj is not None and obj.type == "MESH" and obj.data.shape_keys \
                and len(obj.data.shape_keys.key_blocks) > 0:
            TargetService.bake_targets(obj)

    bake_keys(export_basemesh)
    for child in ObjectService.get_list_of_children(export_root):
        bake_keys(child)

    skin_mat = make_material("mat_skin", (0.82, 0.66, 0.54), 0.75)
    export_basemesh.data.materials.clear()
    export_basemesh.data.materials.append(skin_mat)

    garments = [build_garment(export_basemesh, landmarks, g) for g in outfit]

    bpy.ops.object.select_all(action="DESELECT")
    export_root.select_set(True)
    for child in ObjectService.get_list_of_children(export_root):
        child.select_set(True)
    for g in garments:
        g.select_set(True)
    bpy.context.view_layer.objects.active = export_root

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    bpy.ops.export_scene.gltf(
        filepath=args.output,
        export_format="GLB",
        use_selection=True,
        export_materials="EXPORT",
        export_apply=True,
    )

    size = os.path.getsize(args.output)
    if size <= 0:
        raise RuntimeError("Export produced an empty file")

    emit({
        "ok": True,
        "params_applied": {k: float(v) for k, v in params.items()},
        "outfit": outfit,
        "output": args.output,
        "bytes": size,
    })


try:
    main()
except Exception as e:
    traceback.print_exc()
    emit({"ok": False, "error": f"{type(e).__name__}: {e}"})
    sys.exit(1)
