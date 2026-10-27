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
import math
import os
import re
import sys
import traceback
from functools import partial
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

BLENDER_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if BLENDER_SCRIPT_DIR not in sys.path:
    sys.path.insert(0, BLENDER_SCRIPT_DIR)


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


def read_spec(path):
    """Per-item garment specs: template id + optional RGB colour override."""
    if not path:
        return None
    with open(path, "r", encoding="utf-8-sig") as f:
        spec = json.load(f)
    if not isinstance(spec, list):
        raise ValueError("Garment spec must be a JSON array")
    cleaned = []
    for entry in spec:
        if not isinstance(entry, dict):
            raise ValueError("Each garment spec must be an object")
        template = str(entry.get("template") or "").strip()
        if template not in GARMENTS:
            raise ValueError(f"Unsupported garment template in spec: {template!r}")
        color = entry.get("color")
        if color is not None:
            if not isinstance(color, list) or len(color) != 3:
                raise ValueError(f"Garment {template} colour must be [r, g, b]")
            values = []
            for channel in color:
                if isinstance(channel, bool) or not isinstance(channel, (int, float)):
                    raise ValueError(f"Garment {template} colour channels must be numbers")
                values.append(min(1.0, max(0.0, float(channel))))
            color = tuple(values)
        texture = entry.get("texture_path")
        if texture:
            texture = str(texture)
            if not Path(texture).is_file():
                texture = None
        mesh = entry.get("mesh_path")
        if mesh:
            mesh = str(mesh)
            if not Path(mesh).is_file():
                mesh = None
        cleaned.append(
            {
                "template": template,
                "color": color,
                "label": str(entry.get("label") or template),
                "wardrobe_item_id": str(entry.get("wardrobe_item_id") or ""),
                "texture_path": texture,
                "mesh_path": mesh,
            }
        )
    return cleaned


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
            "shape": garment.get("shape"),
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


def scale_to_height(objects, target_height_m: float):
    """Uniformly scale every mesh in `objects` around the ground so the figure is
    exactly target_height_m tall. Returns (factor, pivot) for landmark scaling."""
    meshes = []
    seen = set()
    for obj in objects:
        if obj is None or obj.type != "MESH" or obj.name in seen:
            continue
        seen.add(obj.name)
        meshes.append(obj)
    if not meshes or target_height_m <= 0:
        return 1.0, None

    points = [(obj.matrix_world @ vertex.co) for obj in meshes for vertex in obj.data.vertices]
    if not points:
        return 1.0, None
    min_z = min(point.z for point in points)
    max_z = max(point.z for point in points)
    current_height = max_z - min_z
    if current_height <= 1e-6:
        return 1.0, None

    factor = target_height_m / current_height
    if abs(factor - 1.0) < 1e-4:
        return 1.0, None

    pivot = Vector((
        (min(point.x for point in points) + max(point.x for point in points)) * 0.5,
        (min(point.y for point in points) + max(point.y for point in points)) * 0.5,
        min_z,
    ))
    for obj in meshes:
        matrix_world = obj.matrix_world
        inverse = matrix_world.inverted()
        for vertex in obj.data.vertices:
            world = matrix_world @ vertex.co
            vertex.co = inverse @ (pivot + (world - pivot) * factor)
        obj.data.update()
    return factor, pivot


def scale_landmarks(landmarks, factor: float, pivot):
    if abs(factor - 1.0) < 1e-4 or pivot is None:
        return landmarks
    return {
        name: pivot + (point - pivot) * factor
        for name, point in landmarks.items()
    }


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


def make_textured_material(name, texture_path, color, roughness=0.8):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = roughness
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = 0.0

    image = bpy.data.images.load(texture_path, check_existing=True)
    image.pack()
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = image
    tex.interpolation = "Linear"
    tex.extension = "CLIP"
    if bsdf is not None:
        links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        if "Alpha" in bsdf.inputs:
            links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    try:
        mat.blend_method = "CLIP"
    except Exception:
        pass
    try:
        mat.surface_render_method = "DITHERED"
    except Exception:
        pass
    mat.use_backface_culling = False
    mat.diffuse_color = (*color, 1.0)
    return mat


def _world_bounds(obj):
    points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    if not points:
        raise RuntimeError(f"Mesh {obj.name!r} has no vertices")
    return (
        min(point.x for point in points), max(point.x for point in points),
        min(point.y for point in points), max(point.y for point in points),
        min(point.z for point in points), max(point.z for point in points),
    )


def _fit_mesh_to_envelope(obj, body_obj, landmarks, garment_id):
    """Fit a normalized provider mesh to the current body before surface wrapping."""
    slot = GARMENTS[garment_id]["slot"]
    shoulder_l = _lm(landmarks, "l-shoulder")
    shoulder_r = _lm(landmarks, "r-shoulder")
    hip_l = _lm(landmarks, "l-upper-leg")
    hip_r = _lm(landmarks, "r-upper-leg")
    ankle_l = _lm(landmarks, "l-ankle")
    ankle_r = _lm(landmarks, "r-ankle")
    shoulder_mid = (shoulder_l + shoulder_r) * 0.5
    hip_mid = (hip_l + hip_r) * 0.5
    shoulder_width = max((shoulder_l - shoulder_r).length, 0.12)
    hip_width = max((hip_l - hip_r).length, 0.10)
    ankle_width = max((ankle_l - ankle_r).length, 0.08)
    body_bounds = _world_bounds(body_obj)
    body_depth = max(body_bounds[3] - body_bounds[2], 0.12)

    if slot in {"top", "outerwear"}:
        min_z = hip_mid.z - (0.10 if slot == "top" else 0.14)
        max_z = shoulder_mid.z + (0.06 if slot == "top" else 0.10)
        target_width = shoulder_width * (1.10 if slot == "top" else 1.16)
        target_center = shoulder_mid
    elif slot == "bottom":
        min_z = min(ankle_l.z, ankle_r.z)
        max_z = hip_mid.z + 0.05
        target_width = hip_width * 1.14
        target_center = hip_mid
    elif slot == "dress":
        min_z = min(ankle_l.z, ankle_r.z)
        max_z = shoulder_mid.z + 0.06
        target_width = max(shoulder_width, hip_width) * 1.12
        target_center = (shoulder_mid + hip_mid) * 0.5
    elif slot == "shoes":
        min_z = min(ankle_l.z, ankle_r.z)
        max_z = min_z + 0.12
        target_width = ankle_width * 0.72
        target_center = (ankle_l + ankle_r) * 0.5
    else:
        min_z = hip_mid.z - 0.12
        max_z = shoulder_mid.z + 0.04
        target_width = shoulder_width * 0.55
        target_center = shoulder_mid

    bounds = _world_bounds(obj)
    current_width = max(bounds[1] - bounds[0], 1e-5)
    current_depth = max(bounds[3] - bounds[2], 1e-5)
    current_height = max(bounds[5] - bounds[4], 1e-5)
    target_height = max(max_z - min_z, 0.08)
    target_depth = body_depth * (1.12 if slot in {"top", "outerwear", "dress"} else 1.08)
    sx = target_width / current_width
    sy = target_depth / current_depth
    sz = target_height / current_height
    inverse = obj.matrix_world.inverted()
    for vertex in obj.data.vertices:
        world = obj.matrix_world @ vertex.co
        world.x = target_center.x + (world.x - (bounds[0] + bounds[1]) * 0.5) * sx
        world.y = (body_bounds[2] + body_bounds[3]) * 0.5 + (
            world.y - (bounds[2] + bounds[3]) * 0.5
        ) * sy
        world.z = min_z + (world.z - bounds[4]) * sz
        vertex.co = inverse @ world
    obj.data.update()


def fit_provider_mesh(body_obj, landmarks, garment_id, mesh_path, color):
    """Import, fit, and surface-wrap a provider mesh around the generated avatar."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=mesh_path)
    imported = [obj for obj in bpy.data.objects if obj not in before and obj.type == "MESH"]
    if not imported:
        raise RuntimeError(f"Provider mesh for {garment_id!r} contains no mesh objects")

    bpy.ops.object.select_all(action="DESELECT")
    for obj in imported:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = imported[0]
    bpy.ops.object.join()
    garment = imported[0]
    garment.name = f"provider_garment_{garment_id}"
    _fit_mesh_to_envelope(garment, body_obj, landmarks, garment_id)

    shrinkwrap = garment.modifiers.new("FitToAvatar", "SHRINKWRAP")
    shrinkwrap.target = body_obj
    shrinkwrap.wrap_method = "NEAREST_SURFACEPOINT"
    shrinkwrap.wrap_mode = "OUTSIDE"
    shrinkwrap.offset = max(float(GARMENTS[garment_id]["offset"]), 0.006)
    bpy.context.view_layer.objects.active = garment
    bpy.ops.object.modifier_apply(modifier=shrinkwrap.name)
    garment.data.validate(verbose=False)
    if not garment.data.polygons:
        raise RuntimeError(f"Provider mesh for {garment_id!r} became empty after fitting")
    if not garment.data.materials:
        garment.data.materials.append(
            make_material(
                f"provider_mat_{garment_id}",
                color or GARMENTS[garment_id]["color"],
                GARMENTS[garment_id]["roughness"],
            )
        )
    for polygon in garment.data.polygons:
        polygon.use_smooth = True
    return garment


def build_skirt(body_obj, landmarks, garment_id, color=None, texture_path=None):
    """A skirt cannot be made from the two leg tubes, so build a simple flared ring."""
    cfg = GARMENTS[garment_id]
    l_hip = _lm(landmarks, "l-upper-leg")
    r_hip = _lm(landmarks, "r-upper-leg")
    hip_center = (l_hip + r_hip) * 0.5
    hip_width = (l_hip - r_hip).length
    waist_z = cfg["min_z"](landmarks)
    hem_z = cfg["hem_z"](landmarks)
    if hem_z >= waist_z:
        raise RuntimeError("Skirt hem must be below the waist")

    offset = cfg["offset"]
    waist_rx = hip_width * 1.02 + offset
    waist_ry = hip_width * 0.68 + offset
    hem_rx = hip_width * 1.35 + offset
    hem_ry = hip_width * 0.92 + offset
    segments = 48

    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    rings = []
    for z, rx, ry in ((waist_z, waist_rx, waist_ry), (hem_z, hem_rx, hem_ry)):
        ring = []
        for i in range(segments):
            angle = 2.0 * 3.141592653589793 * i / segments
            x = hip_center.x + math.cos(angle) * rx
            y = hip_center.y + math.sin(angle) * ry
            ring.append(bm.verts.new((x, y, z)))
        rings.append(ring)

    for i in range(segments):
        nxt = (i + 1) % segments
        face = bm.faces.new((rings[0][i], rings[0][nxt], rings[1][nxt], rings[1][i]))
        for loop, uv in zip(
            face.loops,
            ((i / segments, 0.0), ((i + 1) / segments, 0.0),
             ((i + 1) / segments, 1.0), (i / segments, 1.0)),
        ):
            loop[uv_layer].uv = uv

    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    new_mesh = bpy.data.meshes.new(f"garment_{garment_id}")
    bm.to_mesh(new_mesh)
    bm.free()

    if texture_path:
        material = make_textured_material(
            f"mat_{garment_id}", texture_path, color or cfg["color"], cfg["roughness"]
        )
    else:
        material = make_material(f"mat_{garment_id}", color or cfg["color"], cfg["roughness"])
    new_mesh.materials.append(material)
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
    obj.data.validate(verbose=False)
    return obj


def build_garment(body_obj, landmarks, garment_id, color=None, texture_path=None):
    cfg = GARMENTS[garment_id]
    if cfg.get("shape") == "skirt":
        return build_skirt(body_obj, landmarks, garment_id, color, texture_path)
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

    if bm.verts:
        xs = [v.co.x for v in bm.verts]
        zs = [v.co.z for v in bm.verts]
        min_x, max_x = min(xs), max(xs)
        min_z, max_z = min(zs), max(zs)
        span_x = max(1e-6, max_x - min_x)
        span_z = max(1e-6, max_z - min_z)
        uv_layer = bm.loops.layers.uv.verify()
        for face in bm.faces:
            for loop in face.loops:
                co = loop.vert.co
                loop[uv_layer].uv = ((co.x - min_x) / span_x, (co.z - min_z) / span_z)

    new_mesh = bpy.data.meshes.new(f"garment_{garment_id}")
    bm.to_mesh(new_mesh)
    bm.free()

    if texture_path:
        material = make_textured_material(
            f"mat_{garment_id}",
            texture_path,
            color or cfg["color"],
            cfg["roughness"],
        )
    else:
        material = make_material(f"mat_{garment_id}", color or cfg["color"], cfg["roughness"])
    new_mesh.materials.append(material)
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
    obj.data.validate(verbose=False)
    return obj


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--params", required=True)
    parser.add_argument("--details", default=None)
    parser.add_argument("--spec", default=None, help="Per-item template/colour JSON")
    parser.add_argument("--outfit", default="tshirt")
    parser.add_argument("--output", required=True)
    parser.add_argument("--height-cm", type=float, default=None)
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

    spec = read_spec(args.spec)
    if spec is not None:
        outfit_specs = [
            (
                entry["template"],
                entry["color"],
                entry.get("texture_path"),
                entry.get("mesh_path"),
            )
            for entry in spec
        ]
        outfit = [entry["template"] for entry in spec]
    else:
        outfit = [g.strip() for g in args.outfit.split(",") if g.strip()]
        outfit_specs = [(g, None, None, None) for g in outfit]
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
    garment_landmarks = scale_landmarks_for_legs(landmarks, landmarks["pelvis"].z, leg_factor)
    if args.height_cm is not None:
        height_factor, height_pivot = scale_to_height(
            [export_basemesh] + list(ObjectService.get_list_of_children(export_root)),
            args.height_cm / 100.0,
        )
        garment_landmarks = scale_landmarks(garment_landmarks, height_factor, height_pivot)
    metrics = compute_metrics(garment_landmarks, 1.0)
    metrics["heightMeters"] = round(mesh_height(export_basemesh), 4)

    skin_mat = make_material("mat_skin", (0.82, 0.66, 0.54), 0.75)
    export_basemesh.data.materials.clear()
    export_basemesh.data.materials.append(skin_mat)

    garments = []
    fitted_items = []
    for g, color, texture_path, mesh_path in outfit_specs:
        if mesh_path:
            try:
                garments.append(
                    fit_provider_mesh(export_basemesh, garment_landmarks, g, mesh_path, color)
                )
                fitted_items.append({"template": g, "mode": "provider-mesh"})
                continue
            except Exception as exc:
                print(f"[avatar] provider mesh fitting failed for {g}: {exc}", flush=True)
        garments.append(build_garment(export_basemesh, garment_landmarks, g, color, texture_path))
        fitted_items.append({"template": g, "mode": "procedural-fallback"})

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
        "items": [
            {
                "template": entry["template"],
                "color": list(entry["color"]) if entry.get("color") else None,
                "label": entry.get("label"),
                "wardrobe_item_id": entry.get("wardrobe_item_id"),
            }
            for entry in (spec or [])
        ],
        "fitted_items": fitted_items,
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
