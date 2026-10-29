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
            "slot": garment["slot"],
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


GARMENT_FIT_PROFILES = {
    "top": {"clearance": 1.08, "wrap_offset": 0.008, "relax_factor": 0.28},
    "outerwear": {"clearance": 1.15, "wrap_offset": 0.012, "relax_factor": 0.22},
    "bottom": {"clearance": 1.08, "wrap_offset": 0.009, "relax_factor": 0.25},
    "dress": {"clearance": 1.18, "wrap_offset": 0.010, "relax_factor": 0.24},
    "shoes": {"clearance": 1.06, "wrap_offset": 0.008, "relax_factor": 0.12},
}


def garment_fit_profile(garment_id):
    slot = GARMENTS[garment_id]["slot"]
    return GARMENT_FIT_PROFILES.get(
        slot,
        {"clearance": 1.10, "wrap_offset": 0.009, "relax_factor": 0.24},
    )


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


# The avatar faces -Y (see render_preview.py / generate_avatar.py), so the
# flat front-view cutout must only be printed on faces pointing that way.
# Everything else (back, sides, shoulders, inner shell, rim) gets a plain
# material so the photo is never mirrored onto the back of the avatar.
FRONT_FACING_NORMAL_Y = -0.25


def _bounds_center_y(matrix, verts):
    ys = [(matrix @ vert.co).y for vert in verts]
    return (min(ys) + max(ys)) * 0.5 if ys else 0.0


def _world_face_geometry(matrix, verts, normal):
    if not verts:
        return Vector((0.0, 0.0, 0.0)), Vector((0.0, 0.0, -1.0))
    center = Vector((0.0, 0.0, 0.0))
    for vert in verts:
        center += matrix @ vert.co
    center /= len(verts)
    world_normal = matrix.to_3x3() @ normal
    if world_normal.length_squared > 1e-12:
        world_normal.normalize()
    else:
        world_normal = Vector((0.0, 0.0, -1.0))
    return center, world_normal


def _is_front_face(center, normal, bounds_center_y):
    return center.y < bounds_center_y and normal.y < FRONT_FACING_NORMAL_Y


def _split_bmesh_front_back(bm, matrix, textured_idx=0, solid_idx=1):
    """Tag bmesh faces: front keeps the print, everything else goes solid."""
    bounds_y = _bounds_center_y(matrix, bm.verts)
    bm.normal_update()
    for face in bm.faces:
        center, normal = _world_face_geometry(matrix, face.verts, face.normal)
        face.material_index = (
            textured_idx if _is_front_face(center, normal, bounds_y) else solid_idx
        )


def _textured_slot(materials):
    """Index of the first material that carries an image texture, if any."""
    for index, mat in enumerate(materials):
        if mat is None or not mat.node_tree:
            continue
        if any(node.type == "TEX_IMAGE" for node in mat.node_tree.nodes):
            return index
    return None


def split_mesh_front_back(obj, solid_color, roughness, name_suffix, back_texture_path=None):
    """Re-tag an already-built mesh so only front faces keep their texture."""
    textured_idx = _textured_slot(obj.data.materials)
    if textured_idx is None:
        return
    solid_idx = None
    for index, mat in enumerate(obj.data.materials):
        if index == textured_idx or mat is None or not mat.node_tree:
            continue
        if not any(node.type == "TEX_IMAGE" for node in mat.node_tree.nodes):
            solid_idx = index
            break
    if back_texture_path:
        obj.data.materials.append(
            make_textured_material(
                f"{name_suffix}_back_texture", back_texture_path, solid_color, roughness
            )
        )
        solid_idx = len(obj.data.materials) - 1
    elif solid_idx is None:
        obj.data.materials.append(make_material(f"{name_suffix}_back", solid_color, roughness))
        solid_idx = len(obj.data.materials) - 1

    matrix = obj.matrix_world
    mesh = obj.data
    bounds_y = _bounds_center_y(matrix, mesh.vertices)
    for poly in mesh.polygons:
        verts = [mesh.vertices[i] for i in poly.vertices]
        center, normal = _world_face_geometry(matrix, verts, poly.normal)
        poly.material_index = (
            textured_idx if _is_front_face(center, normal, bounds_y) else solid_idx
        )
    mesh.update()


def _world_bounds(obj):
    points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    if not points:
        raise RuntimeError(f"Mesh {obj.name!r} has no vertices")
    return (
        min(point.x for point in points), max(point.x for point in points),
        min(point.y for point in points), max(point.y for point in points),
        min(point.z for point in points), max(point.z for point in points),
    )


ARM_LABELS = {
    "shoulder_L", "shoulder_R",
    "upperarm_L", "upperarm_R",
    "forearm_L", "forearm_R",
    "hand_L", "hand_R",
}


def _body_width_at(body_obj, segments, z_center, tolerance=0.06):
    """Actual torso/leg breadth (flesh included) in a horizontal slice.

    Arms (and especially hands in A-pose) reach far outside the torso, so
    including them would blow the measured width up to arm span.
    """
    matrix = body_obj.matrix_world
    xs = []
    for vertex in body_obj.data.vertices:
        world = matrix @ vertex.co
        if abs(world.z - z_center) > tolerance:
            continue
        if classify_vertices([world], segments)[0] in ARM_LABELS:
            continue
        xs.append(world.x)
    if len(xs) < 8:
        return None
    return max(xs) - min(xs)


def _body_y_span(body_obj, segments):
    """Front-to-back span (centre, depth) of the torso, ignoring outstretched arms.

    The full-body bounds are centred on the hands, so they must not be used to
    recentre the garment: the back sheet would start inside the torso, and a
    shrinkwrap raycast from inside the body misses (backface culling).
    """
    matrix = body_obj.matrix_world
    ys = []
    for vertex in body_obj.data.vertices:
        world = matrix @ vertex.co
        if classify_vertices([world], segments)[0] in ARM_LABELS:
            continue
        ys.append(world.y)
    if len(ys) < 8:
        return None
    return (min(ys) + max(ys)) * 0.5, max(ys) - min(ys)


def _mesh_band_width(obj, bounds, band, from_bottom=True):
    """Photo silhouette width inside a horizontal band of its own height."""
    z_min, z_max = bounds[4], bounds[5]
    height = max(z_max - z_min, 1e-5)
    if from_bottom:
        low, high = z_min, z_min + band * height
    else:
        low, high = z_max - band * height, z_max
    xs = []
    matrix = obj.matrix_world
    for vertex in obj.data.vertices:
        world = matrix @ vertex.co
        if low <= world.z <= high:
            xs.append(world.x)
    if len(xs) < 6:
        return None
    return max(xs) - min(xs)


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
    segments = build_segments(landmarks)
    torso_span = _body_y_span(body_obj, segments)
    if torso_span:
        body_center_y, body_depth = torso_span
    else:
        body_center_y = (body_bounds[2] + body_bounds[3]) * 0.5
        body_depth = max(body_bounds[3] - body_bounds[2], 0.12)

    # `width_band` describes which part of the *photo* corresponds to the body
    # slice measured at `body_z` (tops: the hem band across the hips, bottoms:
    # the waist band across the pelvis, shoes: the soles across the feet).
    # Joint distances alone are far too narrow to cover a real torso.
    width_band = None
    body_z = None
    profile = garment_fit_profile(garment_id)
    clearance = profile["clearance"]

    if slot in {"top", "outerwear"}:
        min_z = hip_mid.z - (0.10 if slot == "top" else 0.14)
        max_z = shoulder_mid.z + (0.06 if slot == "top" else 0.10)
        target_width = shoulder_width * (1.55 if slot == "top" else 1.65)
        target_center = shoulder_mid
        width_band = (0.22, True)
        body_z = min_z + 0.08
        clearance = profile["clearance"]
    elif slot == "bottom":
        min_z = min(ankle_l.z, ankle_r.z)
        max_z = hip_mid.z + 0.05
        target_width = hip_width * 1.6
        target_center = hip_mid
        width_band = (0.18, False)
        body_z = max_z - 0.05
        clearance = profile["clearance"]
    elif slot == "dress":
        min_z = min(ankle_l.z, ankle_r.z)
        max_z = shoulder_mid.z + 0.06
        target_width = max(shoulder_width, hip_width) * 1.5
        target_center = (shoulder_mid + hip_mid) * 0.5
        width_band = (0.22, True)
        body_z = min_z + 0.10
        clearance = profile["clearance"]
    elif slot == "shoes":
        min_z = min(ankle_l.z, ankle_r.z)
        max_z = min_z + 0.12
        target_width = ankle_width * 0.72
        target_center = (ankle_l + ankle_r) * 0.5
        width_band = (0.15, True)
        body_z = 0.06
        clearance = profile["clearance"]
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
    # Only push the flat sheet a little past the skin on each side; the
    # shrinkwrap does the real conforming, and less stretch keeps the
    # triangles from elongating into slivers.
    target_depth = body_depth * (1.05 if slot in {"top", "outerwear", "dress"} else 1.03)

    if width_band is not None and body_z is not None:
        band, from_bottom = width_band
        band_width = _mesh_band_width(obj, bounds, band, from_bottom)
        body_width = _body_width_at(body_obj, segments, body_z)
        if band_width and body_width:
            target_width = body_width * clearance * (current_width / band_width)
            target_width = min(target_width, current_width * 2.5)

    sx = target_width / current_width
    sy = target_depth / current_depth
    sz = target_height / current_height
    inverse = obj.matrix_world.inverted()
    for vertex in obj.data.vertices:
        world = obj.matrix_world @ vertex.co
        world.x = target_center.x + (world.x - (bounds[0] + bounds[1]) * 0.5) * sx
        world.y = body_center_y + (
            world.y - (bounds[2] + bounds[3]) * 0.5
        ) * sy
        world.z = min_z + (world.z - bounds[4]) * sz
        vertex.co = inverse @ world
    obj.data.update()


def _far_vertices(obj, body_obj, limit):
    """Indices of vertices further than `limit` from the body surface."""
    to_body = body_obj.matrix_world.inverted()
    world_matrix = obj.matrix_world
    far = []
    for index, vertex in enumerate(obj.data.vertices):
        local = to_body @ (world_matrix @ vertex.co)
        hit, location, _normal, _face = body_obj.closest_point_on_mesh(local)
        if not hit or (local - location).length > limit:
            far.append(index)
    return far


def _outline_vertices(obj):
    """Vertices on the photo slab's rim (the boundary between the sheets).

    Faces whose world normal points sideways belong to the extruded outline;
    everything else faces front or back. Detected right after import, before
    any fitting moves the mesh around.
    """
    normal_matrix = obj.matrix_world.to_3x3()
    found = set()
    for polygon in obj.data.polygons:
        normal = (normal_matrix @ polygon.normal).normalized()
        if abs(normal.y) < 0.3:
            found.update(polygon.vertices)
    return found


def _push_out_inside(obj, body_obj, offset):
    """Move any vertex buried in the body back out along the surface normal.

    Projection and seam blending can leave rim/outline vertices a few
    millimetres inside the torso's side bulge; those faces disappear behind
    the skin and show up as a gap strip in three-quarter views.
    """
    to_body = body_obj.matrix_world.inverted()
    to_obj = obj.matrix_world.inverted()
    body_matrix = body_obj.matrix_world
    world_matrix = obj.matrix_world
    moved = 0
    for vertex in obj.data.vertices:
        local = to_body @ (world_matrix @ vertex.co)
        hit, location, normal, _face = body_obj.closest_point_on_mesh(local)
        if not hit:
            continue
        delta = local - location
        if delta.length > 1e-6 and delta.dot(normal) >= 0.0:
            continue
        vertex.co = to_obj @ (body_matrix @ (location + normal * offset))
        moved += 1
    if moved:
        obj.data.update()
    return moved


def fit_provider_mesh(body_obj, landmarks, garment_id, mesh_path, color, back_texture_path=None):
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
    # glTF stores each material in its own primitive, so vertices shared
    # between the front sheet, back sheet, and rim come back as duplicated,
    # unconnected copies (the source imports as ~180 loose islands). Weld them
    # before measuring the outline, otherwise moving the rim leaves the sheets
    # behind and a slit opens along the flank.
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=1e-4)
    bpy.ops.object.mode_set(mode="OBJECT")
    outline = _outline_vertices(garment)
    _fit_mesh_to_envelope(garment, body_obj, landmarks, garment_id)

    profile = garment_fit_profile(garment_id)
    wrap_offset = max(profile["wrap_offset"], float(GARMENTS[garment_id]["offset"]) * 0.75)
    # Project along Y: the photo keeps its x/z layout (no scrambling) and only
    # wraps in depth onto the chest/back.
    # Snapshot pre-projection world positions: photo columns past the body's
    # silhouette need their original y later (Y-project leaves them behind or
    # crushes them onto the tangent line).
    pre_world = [garment.matrix_world @ v.co for v in garment.data.vertices]
    shrinkwrap = garment.modifiers.new("FitToAvatar", "SHRINKWRAP")
    shrinkwrap.target = body_obj
    shrinkwrap.wrap_method = "PROJECT"
    shrinkwrap.use_project_y = True
    shrinkwrap.use_positive_direction = True
    shrinkwrap.use_negative_direction = True
    shrinkwrap.offset = wrap_offset
    bpy.context.view_layer.objects.active = garment
    bpy.ops.object.modifier_apply(modifier=shrinkwrap.name)

    # Rim treatment. Two vertex groups need special care after the Y-project:
    #  - Outline verts whose photo x reaches past the body's half width must
    #    all wrap onto the body's SIDE (same anchor for the front and back
    #    sheet) so the rim closes over the flank. Snapping them one by one to
    #    their nearest point instead makes the rim zigzag between projected
    #    and snapped verts, which shows as spikes and skin gaps.
    #  - Any other vertex whose Y-ray missed the body (sleeve tips past the
    #    silhouette, cloth over the crotch gap) falls back to its own nearest
    #    surface point, which keeps the photo layout intact.
    far = set(_far_vertices(garment, body_obj, limit=0.05))
    segments = build_segments(landmarks)
    torso_span = _body_y_span(body_obj, segments)
    body_center_y = torso_span[0] if torso_span else 0.0

    body_matrix = body_obj.matrix_world
    to_body = body_matrix.inverted()
    world_matrix = garment.matrix_world
    to_garment = world_matrix.inverted()

    body_points = [body_matrix @ vertex.co for vertex in body_obj.data.vertices]
    body_labels = classify_vertices(body_points, segments)
    half_cache = {}

    def body_half(z):
        key = round(z, 2)
        if key not in half_cache:
            xs = [
                point.x for point, label in zip(body_points, body_labels)
                if label not in ARM_LABELS and abs(point.z - key) <= 0.05 and point.x > 0
            ]
            # The body is centred on x=0, so the rightmost non-arm vertex in
            # the slice is the half width.
            half_cache[key] = max(xs) if len(xs) >= 8 else None
        return half_cache[key]

    side_snapped = set()
    for index in outline:
        vertex = garment.data.vertices[index]
        world = world_matrix @ vertex.co
        half = body_half(world.z)
        if half is None or abs(world.x) < 0.5 * half:
            continue
        # Keep the vert's own x when it is already past the flank radius so
        # sleeve cuffs stay spread along the arm instead of piling onto the
        # shoulder; torso-edge verts (x <= half) still anchor at the flank.
        anchor = to_body @ Vector((
            math.copysign(max(abs(world.x), half + 0.06), world.x),
            body_center_y,
            world.z,
        ))
        hit, location, normal, _face = body_obj.closest_point_on_mesh(anchor)
        if hit:
            vertex.co = to_garment @ (body_matrix @ (location + normal * wrap_offset))
            side_snapped.add(index)

    # Photo columns at or past the silhouette edge either miss the Y-ray
    # (x > half width) or hit it at a grazing angle and pile up on the tangent
    # line, which shows as sliver gashes and comb teeth along the side. Wrap
    # them around the flank instead, anchored at their own pre-projection y so
    # the columns stay spread out (outline verts keep the shared centre-y
    # anchor above so the rim still closes).
    silhouette = set()
    for index, vertex in enumerate(garment.data.vertices):
        if index in outline:
            continue
        world = world_matrix @ vertex.co
        half = body_half(world.z)
        if half is None or abs(world.x) < half - 0.01:
            continue
        ax = abs(world.x)
        if ax <= half + 0.06:
            # Flank band: the anchor x is constant, so the columns must be
            # separated by y instead - slide from the column's own
            # pre-projection y toward the shared seam y as it rounds the
            # corner, otherwise every vert of a row lands on one point and
            # the sheet collapses into slivers.
            t = min(max((ax - (half - 0.01)) / 0.07, 0.0), 1.0)
            anchor_y = pre_world[index].y + (body_center_y - pre_world[index].y) * t
        else:
            # Past the flank radius (sleeves): keep the sheet's own depth so
            # front and back stay wrapped around opposite sides of the arm.
            anchor_y = pre_world[index].y
        anchor = to_body @ Vector((
            math.copysign(max(ax, half + 0.06), world.x),
            anchor_y,
            world.z,
        ))
        hit, location, normal, _face = body_obj.closest_point_on_mesh(anchor)
        if hit:
            vertex.co = to_garment @ (body_matrix @ (location + normal * wrap_offset))
            silhouette.add(index)

    for index in far - side_snapped - silhouette:
        vertex = garment.data.vertices[index]
        local = to_body @ (world_matrix @ vertex.co)
        hit, location, normal, _face = body_obj.closest_point_on_mesh(local)
        if hit:
            vertex.co = to_garment @ (body_matrix @ (location + normal * wrap_offset))
    garment.data.update()
    print(
        f"FIT_DEBUG outline={len(outline)} side_snapped={len(side_snapped)} "
        f"silhouette={len(silhouette)} far={len(far)} "
        f"half_z10={body_half(1.0)} half_z12={body_half(1.2)}",
        flush=True,
    )

    # Relax the projection a little so concavities (armpits, neckline) do not
    # leave spiky artefacts behind. Outline verts must NOT be smoothed: the
    # front and back rim verts were welded to the same flank/hem anchor above,
    # and averaging them with their own sheet's interior would pull the seam
    # back open (the visible slit along the side).
    relax_group = garment.vertex_groups.new(name="relax_non_outline")
    relax_group.add(
        [index for index in range(len(garment.data.vertices)) if index not in outline],
        1.0,
        "REPLACE",
    )
    relax = garment.modifiers.new("Relax", "SMOOTH")
    relax.factor = profile["relax_factor"]
    relax.iterations = 2
    relax.vertex_group = relax_group.name
    bpy.ops.object.modifier_apply(modifier=relax.name)

    _push_out_inside(garment, body_obj, wrap_offset)

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
    # The imported GLB is a solidified photo slab: its back sheet must not
    # keep the front print.
    split_mesh_front_back(
        garment,
        color or GARMENTS[garment_id]["color"],
        GARMENTS[garment_id]["roughness"],
        f"provider_{garment_id}",
        back_texture_path,
    )
    for polygon in garment.data.polygons:
        polygon.use_smooth = True
    return garment


def build_skirt(body_obj, landmarks, garment_id, color=None, texture_path=None, back_texture_path=None):
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

    offset = cfg["offset"] * 0.85
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

    textured = bool(texture_path)
    if textured:
        # The photo belongs across the front of the skirt only: planar X/Z UVs
        # (hem = bottom of the image) and a solid back.
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
        _split_bmesh_front_back(bm, body_obj.matrix_world, textured_idx=0, solid_idx=1)

    new_mesh = bpy.data.meshes.new(f"garment_{garment_id}")
    bm.to_mesh(new_mesh)
    bm.free()

    if texture_path or back_texture_path:
        material = make_textured_material(
            f"mat_{garment_id}", texture_path, color or cfg["color"], cfg["roughness"]
        )
    else:
        material = make_material(f"mat_{garment_id}", color or cfg["color"], cfg["roughness"])
    new_mesh.materials.append(material)
    if back_texture_path:
        new_mesh.materials.append(
            make_textured_material(
                f"mat_{garment_id}_back_texture",
                back_texture_path,
                color or cfg["color"],
                cfg["roughness"],
            )
        )
    elif textured:
        new_mesh.materials.append(
            make_material(
                f"mat_{garment_id}_back",
                color or cfg["color"],
                cfg["roughness"],
            )
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
    if textured:
        # offset=1 keeps the split original faces as the OUTER shell (front
        # print / solid back); the generated inner shell inherits the same
        # indices so alpha-clip holes still see through to the skin. Only the
        # rim is forced solid so the fabric edge is not a cutout.
        solid.material_offset_rim = 1
    bpy.ops.object.modifier_apply(modifier=solid.name)
    obj.data.validate(verbose=False)
    return obj


def build_garment(
    body_obj,
    landmarks,
    garment_id,
    color=None,
    texture_path=None,
    back_texture_path=None,
):
    cfg = GARMENTS[garment_id]
    if cfg.get("shape") == "skirt":
        return build_skirt(
            body_obj, landmarks, garment_id, color, texture_path, back_texture_path
        )
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
    offset = max(garment_fit_profile(garment_id)["wrap_offset"], cfg["offset"] * 0.85)
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

    textured = bool(texture_path)
    if textured or back_texture_path:
        # Front faces keep the planar photo UV; back/sides/shoulders go solid.
        _split_bmesh_front_back(bm, body_obj.matrix_world, textured_idx=0, solid_idx=1)

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
    if back_texture_path:
        new_mesh.materials.append(
            make_textured_material(
                f"mat_{garment_id}_back_texture",
                back_texture_path,
                color or cfg["color"],
                cfg["roughness"],
            )
        )
    elif textured:
        new_mesh.materials.append(
            make_material(
                f"mat_{garment_id}_back",
                color or cfg["color"],
                cfg["roughness"],
            )
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
    if textured:
        # Same split as the skirt: split originals = outer shell, generated
        # inner shell inherits indices (clip holes stay see-through), rim solid.
        solid.material_offset_rim = 1
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
                entry.get("back_texture_path"),
            )
            for entry in spec
        ]
        outfit = [entry["template"] for entry in spec]
    else:
        outfit = [g.strip() for g in args.outfit.split(",") if g.strip()]
        outfit_specs = [(g, None, None, None, None) for g in outfit]
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
    for g, color, texture_path, mesh_path, back_texture_path in outfit_specs:
        if mesh_path:
            try:
                garments.append(
                    fit_provider_mesh(
                        export_basemesh,
                        garment_landmarks,
                        g,
                        mesh_path,
                        color,
                        back_texture_path,
                    )
                )
                fitted_items.append({"template": g, "mode": "provider-mesh"})
                continue
            except Exception as exc:
                print(f"[avatar] provider mesh fitting failed for {g}: {exc}", flush=True)
        garments.append(
            build_garment(
                export_basemesh,
                garment_landmarks,
                g,
                color,
                texture_path,
                back_texture_path,
            )
        )
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
