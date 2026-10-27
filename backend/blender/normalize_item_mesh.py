"""Validate and normalize an imported wardrobe mesh before it is stored.

The image-to-3D providers return arbitrary origins and scales. This pass makes
their GLBs predictable for the wardrobe viewer without pretending to fit them
to a body avatar.
"""

import argparse
import json
import os
import sys
import traceback

import bpy

SLOT_MAX_SIZE = {
    "top": 0.68,
    "bottom": 1.0,
    "dress": 1.2,
    "outerwear": 0.9,
    "shoes": 0.32,
    "bag": 0.36,
    "accessory": 0.3,
}


def emit(payload):
    print("ITEM_NORMALIZE_RESULT " + json.dumps(payload), flush=True)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--slot", default="accessory")
    parser.add_argument("--target-faces", type=int, default=30000)
    args, _unknown = parser.parse_known_args(sys.argv[sys.argv.index("--") + 1:])
    return args


def mesh_objects():
    return [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]


def select(objects):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    if objects:
        bpy.context.view_layer.objects.active = objects[0]


def decimate(objects, target_faces):
    before = sum(len(obj.data.polygons) for obj in objects)
    if target_faces <= 0 or before <= target_faces:
        return before, before
    ratio = max(0.001, min(1.0, target_faces / before))
    for obj in objects:
        select([obj])
        modifier = obj.modifiers.new("DressMeDecimate", "DECIMATE")
        modifier.decimate_type = "COLLAPSE"
        modifier.ratio = ratio
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        obj.data.validate(verbose=False)
    return before, sum(len(obj.data.polygons) for obj in objects)


def normalize(objects, target_size):
    select(objects)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    points = [vertex.co.copy() for obj in objects for vertex in obj.data.vertices]
    if not points:
        raise RuntimeError("The generated mesh has no vertices")
    min_x = min(point.x for point in points)
    max_x = max(point.x for point in points)
    min_y = min(point.y for point in points)
    max_y = max(point.y for point in points)
    min_z = min(point.z for point in points)
    max_z = max(point.z for point in points)
    span = max(max_x - min_x, max_y - min_y, max_z - min_z)
    if span <= 1e-6:
        raise RuntimeError("The generated mesh has zero dimensions")

    scale = target_size / span
    centre_x = (min_x + max_x) * 0.5
    centre_z = (min_z + max_z) * 0.5
    for obj in objects:
        for vertex in obj.data.vertices:
            vertex.co.x = (vertex.co.x - centre_x) * scale
            vertex.co.y = (vertex.co.y - min_y) * scale
            vertex.co.z = (vertex.co.z - centre_z) * scale
        obj.data.update()
    return {
        "width": round((max_x - min_x) * scale, 4),
        "height": round((max_y - min_y) * scale, 4),
        "depth": round((max_z - min_z) * scale, 4),
        "scale": round(scale, 6),
    }


def main():
    args = parse_args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=args.mesh)
    objects = mesh_objects()
    if not objects:
        raise RuntimeError("The generated GLB contains no mesh objects")

    for obj in objects:
        if len(obj.data.vertices) == 0 or len(obj.data.polygons) == 0:
            raise RuntimeError(f"Mesh object {obj.name!r} is empty")
        obj.data.validate(verbose=False)
        for polygon in obj.data.polygons:
            polygon.use_smooth = True

    faces_before, faces = decimate(objects, args.target_faces)
    dimensions = normalize(objects, SLOT_MAX_SIZE.get(args.slot, 0.6))
    select(objects)
    bpy.ops.export_scene.gltf(
        filepath=args.output,
        export_format="GLB",
        use_selection=True,
        export_materials="EXPORT",
        export_image_format="AUTO",
    )
    size = os.path.getsize(args.output)
    if size <= 0:
        raise RuntimeError("Export produced an empty file")
    emit({
        "ok": True,
        "bytes": size,
        "objects": len(objects),
        "faces_before": faces_before,
        "faces": faces,
        "dimensions": dimensions,
        "slot": args.slot,
    })


try:
    main()
except Exception as exc:
    traceback.print_exc()
    emit({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
    sys.exit(1)
