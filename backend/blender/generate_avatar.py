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
  gender age muscle weight height proportions cupsize firmness legLength

`legLength` is not an MPFB property: it scales the body below the hip landmark
after MPFB shaping, then reports the achieved body ratios in AVATAR_RESULT.
"""

import argparse
import importlib
import json
import os
import re
import sys
import traceback

import bpy
from mathutils import Vector

BLENDER_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if BLENDER_SCRIPT_DIR not in sys.path:
    sys.path.insert(0, BLENDER_SCRIPT_DIR)



def clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def read_joint_landmarks(basemesh):
    """Average the joint-cube vertex groups into anatomical landmark positions."""
    saved = [(m, m.show_viewport, m.show_render) for m in basemesh.modifiers]
    for m, _vp, _rn in saved:
        m.show_viewport = False
        m.show_render = False

    index_to_name = {vg.index: vg.name for vg in basemesh.vertex_groups}
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = basemesh.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()

    accumulated = {}
    for vertex in mesh.vertices:
        for group in basemesh.data.vertices[vertex.index].groups:
            name = index_to_name.get(group.group)
            if name and name.startswith("joint-") and group.weight > 0.3:
                accumulated.setdefault(name, []).append(evaluated.matrix_world @ vertex.co)
    evaluated.to_mesh_clear()

    for m, show_viewport, show_render in saved:
        m.show_viewport = show_viewport
        m.show_render = show_render

    landmarks = {}
    for name, points in accumulated.items():
        total = Vector((0.0, 0.0, 0.0))
        for point in points:
            total += point
        landmarks[name.replace("joint-", "")] = total / len(points)
    return landmarks


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


def compute_metrics(landmarks, leg_factor: float = 1.0) -> dict:
    def landmark(name):
        return landmarks[name]

    l_shoulder = landmark("l-shoulder")
    r_shoulder = landmark("r-shoulder")
    l_hip = landmark("l-upper-leg")
    r_hip = landmark("r-upper-leg")
    l_ankle = landmark("l-ankle")
    r_ankle = landmark("r-ankle")

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


def render_silhouette_views(body_obj, out_prefix: str) -> dict:
    """Render transparent front/side masks of the generated body for fitting."""
    matrix_world = body_obj.matrix_world
    coords = [matrix_world @ vertex.co for vertex in body_obj.data.vertices]
    if not coords:
        raise RuntimeError("Cannot render silhouettes for an empty body mesh")

    mins = Vector((
        min(point.x for point in coords),
        min(point.y for point in coords),
        min(point.z for point in coords),
    ))
    maxs = Vector((
        max(point.x for point in coords),
        max(point.y for point in coords),
        max(point.z for point in coords),
    ))
    center = (mins + maxs) * 0.5
    size = maxs - mins
    height = max(size.z, 1e-4)
    distance = max(size.x, size.y, size.z) * 2.0

    for obj in bpy.data.objects:
        try:
            obj.hide_render = obj is not body_obj
        except Exception:
            continue

    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
    scene.render.film_transparent = True
    scene.render.resolution_x = 480
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    scene.world = bpy.data.worlds.new("SilhouetteWorld")

    camera_data = bpy.data.cameras.new("SilhouetteCamera")
    camera_data.type = "ORTHO"
    camera_data.sensor_fit = "VERTICAL"
    camera_data.ortho_scale = height * 1.12
    camera = bpy.data.objects.new("SilhouetteCamera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera

    paths = {}
    for name, direction in (("front", Vector((0.0, -1.0, 0.0))), ("side", Vector((1.0, 0.0, 0.0)))):
        camera.location = center + direction.normalized() * distance
        camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
        path = f"{out_prefix}_{name}.png"
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        paths[name] = path

    return paths


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
    "legLength",
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


DETAIL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*$")


def read_details(path):
    if not path:
        return {}
    with open(path, "r", encoding="utf-8-sig") as f:
        details = json.load(f)
    if not isinstance(details, dict):
        raise ValueError("Details must be a JSON object")
    return details


def apply_detail_targets(TargetService, basemesh, details):
    """Load whitelisted local detail targets after the macro shape is computed."""
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--params", required=True)
    parser.add_argument("--details", default=None)
    parser.add_argument("--silhouettes", default=None)
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
        if key == "legLength":
            continue
        HumanObjectProperties.set_value(key, float(value), entity_reference=basemesh)
        applied[key] = float(value)
    TargetService.reapply_macro_details(basemesh)
    applied_details, missing_details = apply_detail_targets(TargetService, basemesh, details)
    bpy.context.view_layer.update()

    landmarks = read_joint_landmarks(basemesh)
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

    bake_shape_keys_if_any(TargetService, export_basemesh)
    for child in ObjectService.get_list_of_children(export_root):
        bake_shape_keys_if_any(TargetService, child)

    leg_factor = apply_leg_length(export_basemesh, float(params.get("legLength", 0.5)), landmarks["pelvis"].z)
    height_factor, height_pivot = 1.0, None
    if args.height_cm is not None:
        height_factor, height_pivot = scale_to_height(
            [export_basemesh] + list(ObjectService.get_list_of_children(export_root)),
            args.height_cm / 100.0,
        )
        landmarks = scale_landmarks(landmarks, height_factor, height_pivot)
    metrics = compute_metrics(landmarks, leg_factor)
    metrics["heightMeters"] = round(mesh_height(export_basemesh), 4)

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

    silhouette_paths = {}
    if args.silhouettes:
        silhouette_paths = render_silhouette_views(export_basemesh, args.silhouettes)

    emit({
        "ok": True,
        "params_applied": applied,
        "details_applied": applied_details,
        "details_missing": missing_details,
        "output": args.output,
        "silhouettes": silhouette_paths,
        "bytes": size,
        "metrics": metrics,
    })


try:
    main()
except Exception as e:
    traceback.print_exc()
    emit({"ok": False, "error": f"{type(e).__name__}: {e}"})
    sys.exit(1)
