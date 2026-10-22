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
import re
import sys
import traceback
from functools import partial
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

ALLOWED_PARAMS = {
    "gender", "age", "muscle", "weight",
    "height", "proportions", "cupsize", "firmness",
    "legLength",
}

CATALOG_PATH = Path(__file__).resolve().parents[2] / "DressMe UI Blueprint" / "src" / "lib" / "garments.json"


DETAIL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*$")


def clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def read_details(path):
    if not path:
        return {}
    with open(path, "r", encoding="utf-8-sig") as f:
        details = json.load(f)
    if not isinstance(details, dict):
        raise ValueError("Details must be a JSON object")
    return details


def apply_detail_targets(TargetService, basemesh, details):
    applied = {}
    missing = []
    for name, raw_value in details.items():
        if not DETAIL_NAME_RE.match(name):
            raise ValueError(f"Invalid detail target name: {name!r}")
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            raise ValueError(f"Detail target {name} must be a number")
        value = float(raw_value)
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"Detail target {name} must be between 0.0 and 1.0")
        if value < 1e-4:
            continue
        full_path = TargetService.target_full_path(name)
        if not full_path:
            missing.append(name)
            continue
        if TargetService.has_target(basemesh, name):
            TargetService.set_target_value(basemesh, name, value)
        else:
            TargetService.load_target(basemesh, full_path, weight=value, name=name)
        applied[name] = value
    return applied, missing


def _anchor_z(landmarks, anchor: str) -> float:
    if anchor == "ground":
        return 0.0
    if anchor == "pelvis":
        return _lm(landmarks, "pelvis").z
    if anchor == "knee":
        return min(_lm(landmarks, "l-knee").z, _lm(landmarks, "r-knee").z)
    if anchor == "ankle":
        return min(_lm(landmarks, "l-ankle").z, _lm(landmarks, "r-ankle").z)
    raise RuntimeError(f"Unsupported garment anchor: {anchor}")


def _anchor_offset(landmarks, anchor: str, offset: float) -> float:
    return _anchor_z(landmarks, anchor) + offset


def load_garment_configs() -> dict:
    """The frontend catalogue is the single source of truth for garment ids and geometry hints."""
    with open(CATALOG_PATH, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    configs = {}
    for garment in data["garments"]:
        hem = garment.get("hem", {"anchor": "pelvis", "offset": 0.0})
        minimum = garment.get("min", {"anchor": "pelvis", "offset": 0.0})
        maximum = garment.get("max")
        configs[garment["id"]] = {
            "label": garment["label"],
            "color": tuple(garment["color"]),
            "offset": float(garment["offset"]),
            "thickness": float(garment["thickness"]),
            "region": set(garment["region"]),
            "fill": set(garment.get("fill", [])),
            "hem_z": partial(_anchor_offset, anchor=hem["anchor"], offset=float(hem["offset"])),
            "min_z": partial(
                _anchor_offset, anchor=minimum["anchor"], offset=float(minimum["offset"])
            ),
            "max_z": (
                partial(_anchor_offset, anchor=maximum["anchor"], offset=float(maximum["offset"]))
                if maximum
                else None
            ),
            "enclose": float(garment.get("enclose", 1.0)),
            "hull": bool(garment.get("hull", False)),
            "roughness": float(garment.get("roughness", 0.8)),
        }
    return configs


GARMENTS = load_garment_configs()


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


def apply_leg_length(body_obj, leg_length: float, hip_z: float) -> float:
    """Scale the body below the hip joint to change the torso-to-leg ratio."""
    factor = 0.85 + 0.30 * clamp01(leg_length)
    if abs(factor - 1.0) < 1e-4:
        return factor

    matrix_world = body_obj.matrix_world
    inverse = matrix_world.inverted()
    for vertex in body_obj.data.vertices:
        world = matrix_world @ vertex.co
        if world.z >= hip_z:
            continue
        blend = min(1.0, max(0.0, (hip_z - world.z) / 0.12))
        world.z = world.z + (hip_z - world.z) * (1.0 - factor) * blend
        vertex.co = inverse @ world
    body_obj.data.update()
    return factor


def scale_landmarks_for_legs(landmarks, hip_z: float, factor: float) -> dict:
    """Mirror apply_leg_length on the landmarks used to classify garment vertices."""
    if abs(factor - 1.0) < 1e-4:
        return landmarks
    scaled = {}
    for name, point in landmarks.items():
        result = point.copy()
        if result.z < hip_z:
            blend = min(1.0, max(0.0, (hip_z - result.z) / 0.12))
            result.z = result.z + (hip_z - result.z) * (1.0 - factor) * blend
        scaled[name] = result
    return scaled


def compute_metrics(landmarks, leg_factor: float = 1.0) -> dict:
    l_shoulder = _lm(landmarks, "l-shoulder")
    r_shoulder = _lm(landmarks, "r-shoulder")
    l_hip = _lm(landmarks, "l-upper-leg")
    r_hip = _lm(landmarks, "r-upper-leg")
    l_ankle = _lm(landmarks, "l-ankle")
    r_ankle = _lm(landmarks, "r-ankle")

    shoulder_width = (l_shoulder - r_shoulder).length
    hip_width = (l_hip - r_hip).length
    shoulder_mid = (l_shoulder + r_shoulder) * 0.5
    hip_mid = (l_hip + r_hip) * 0.5
    ankle_mid = (l_ankle + r_ankle) * 0.5
    torso_length = (shoulder_mid - hip_mid).length
    leg_length = (hip_mid - ankle_mid).length * leg_factor

    return {
        "shoulderToHip": shoulder_width / hip_width if hip_width > 1e-6 else 0.0,
        "torsoToLeg": torso_length / leg_length if leg_length > 1e-6 else 0.0,
        "shoulderWidth": shoulder_width,
        "hipWidth": hip_width,
        "torsoLength": torso_length,
        "legLength": leg_length,
    }


def mesh_height(body_obj) -> float:
    matrix_world = body_obj.matrix_world
    zs = [(matrix_world @ vertex.co).z for vertex in body_obj.data.vertices]
    return max(zs) - min(zs) if zs else 0.0


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

    region = cfg["region"]
    fill = cfg["fill"]
    hem_z = cfg["hem_z"](landmarks)
    min_z = cfg["min_z"](landmarks)
    max_z = cfg["max_z"](landmarks) if cfg["max_z"] else None

    keep = []
    for i, v in enumerate(bm.verts):
        label = labels[i]
        world_z = points[i].z
        include = (label in region or (label in fill and world_z > hem_z)) and world_z >= min_z
        if include and max_z is not None:
            include = world_z <= max_z
        keep.append(include)
        v.select = include

    bm.verts.ensure_lookup_table()
    to_delete = [v for v, k in zip(bm.verts, keep) if not k]
    bmesh.ops.delete(bm, geom=to_delete, context="VERTS")

    if len(bm.verts) == 0:
        raise RuntimeError(f"Garment '{garment_id}' selected no vertices")

    if cfg.get("hull"):
        # Hull each side separately, otherwise the hull spans between both feet.
        groups = [
            [v for v in bm.verts if v.co.x < 0.0],
            [v for v in bm.verts if v.co.x >= 0.0],
        ]
        for group in groups:
            if len(group) < 4:
                continue
            hull = bmesh.ops.convex_hull(bm, input=group)
            for key, context in (
                ("geom_interior", "VERTS"),
                ("geom_unused", "VERTS"),
                ("geom_holes", "FACES"),
            ):
                geom = hull.get(key, [])
                if geom:
                    bmesh.ops.delete(bm, geom=geom, context=context)
        bm.verts.ensure_lookup_table()

    bm.normal_update()
    offset = cfg["offset"]
    for v in bm.verts:
        v.co = v.co + v.normal * offset

    # Some shells (boots) are hard to cover by normal offset alone because the
    # toes are a tight, highly curved surface. Scaling the shell away from its
    # own centre guarantees the body is enclosed.
    enclose = cfg.get("enclose", 1.0)
    if enclose != 1.0:
        centre = Vector((0.0, 0.0, 0.0))
        for v in bm.verts:
            centre += v.co
        centre /= len(bm.verts)
        for v in bm.verts:
            v.co = centre + (v.co - centre) * enclose

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
    parser.add_argument("--details", default=None)
    parser.add_argument("--outfit", default="tshirt")
    parser.add_argument("--output", required=True)
    args, _unknown = parser.parse_known_args(sys.argv[sys.argv.index("--") + 1:])

    with open(args.params, "r", encoding="utf-8-sig") as f:
        params = json.load(f)
    details = read_details(args.details)

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

    applied = {}
    for key, value in params.items():
        if key == "legLength":
            continue
        HumanObjectProperties.set_value(key, float(value), entity_reference=basemesh)
        applied[key] = float(value)
    TargetService.reapply_macro_details(basemesh)
    applied_details, missing_details = apply_detail_targets(TargetService, basemesh, details)
    bpy.context.view_layer.update()

    landmarks = read_landmarks(basemesh)
    landmarks = {name.replace("joint-", ""): p for name, p in landmarks.items()}
    if "pelvis" not in landmarks:
        raise RuntimeError("Missing pelvis landmark on the avatar rig")

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

    leg_factor = apply_leg_length(export_basemesh, float(params.get("legLength", 0.5)), landmarks["pelvis"].z)
    metrics = compute_metrics(landmarks, leg_factor)
    metrics["heightMeters"] = round(mesh_height(export_basemesh), 4)

    skin_mat = make_material("mat_skin", (0.82, 0.66, 0.54), 0.75)
    export_basemesh.data.materials.clear()
    export_basemesh.data.materials.append(skin_mat)

    garment_landmarks = scale_landmarks_for_legs(landmarks, landmarks["pelvis"].z, leg_factor)
    garments = [build_garment(export_basemesh, garment_landmarks, g) for g in outfit]

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
        "params_applied": applied,
        "details_applied": applied_details,
        "details_missing": missing_details,
        "outfit": outfit,
        "output": args.output,
        "bytes": size,
        "metrics": metrics,
    })


try:
    main()
except Exception as e:
    traceback.print_exc()
    emit({"ok": False, "error": f"{type(e).__name__}: {e}"})
    sys.exit(1)
