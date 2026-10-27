"""Apply a cutout texture to an externally generated item mesh.

Hunyuan3D's shape-only endpoint returns a clean GLB without UVs or materials.
The textured endpoint needs more GPU quota than the free tier often allows, so
this script decimates the generated mesh and projects the item cutout onto it
with a front/back planar UV map.

Run:
  blender --background --python texture_item_mesh.py -- \
      --mesh white_mesh.glb --texture cutout.png --output item.glb
"""

import argparse
import json
import os
import sys
import traceback

import bpy
from mathutils import Vector


def emit(payload):
    print("ITEM_TEXTURE_RESULT " + json.dumps(payload), flush=True)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh", required=True)
    parser.add_argument("--texture", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--target-faces", type=int, default=30000)
    args, _unknown = parser.parse_known_args(sys.argv[sys.argv.index("--") + 1:])
    return args


def mesh_objects():
    return [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]


def apply_transforms(objects):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    if objects:
        bpy.context.view_layer.objects.active = objects[0]
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


def decimate(objects, target_faces):
    total = sum(len(obj.data.polygons) for obj in objects)
    if total <= target_faces or target_faces <= 0:
        return total
    ratio = max(0.001, min(1.0, target_faces / total))
    for obj in objects:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        modifier = obj.modifiers.new("Decimate", "DECIMATE")
        modifier.decimate_type = "COLLAPSE"
        modifier.ratio = ratio
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        obj.data.validate(verbose=False)
    return sum(len(obj.data.polygons) for obj in objects)


def make_material(texture_path):
    image = bpy.data.images.load(texture_path, check_existing=False)
    image.pack()
    material = bpy.data.materials.new("item_cutout")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = image
    tex.interpolation = "Linear"
    tex.extension = "CLIP"
    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    if "Alpha" in bsdf.inputs:
        links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    try:
        material.blend_method = "CLIP"
    except Exception:
        pass
    try:
        material.surface_render_method = "DITHERED"
    except Exception:
        pass
    material.use_backface_culling = False
    return material


def add_uvs(objects):
    points = []
    for obj in objects:
        points.extend(v.co for v in obj.data.vertices)
    if not points:
        return
    min_x = min(p.x for p in points)
    max_x = max(p.x for p in points)
    min_z = min(p.z for p in points)
    max_z = max(p.z for p in points)
    span_x = max(1e-6, max_x - min_x)
    span_z = max(1e-6, max_z - min_z)

    for obj in objects:
        uv_layer = obj.data.uv_layers.get("UVMap") or obj.data.uv_layers.new(name="UVMap")
        mesh = obj.data
        for polygon in mesh.polygons:
            for loop_index in polygon.loop_indices:
                co = mesh.vertices[mesh.loops[loop_index].vertex_index].co
                uv_layer.data[loop_index].uv = (
                    (co.x - min_x) / span_x,
                    (co.z - min_z) / span_z,
                )
        for polygon in mesh.polygons:
            polygon.use_smooth = True


def main():
    args = parse_args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=args.mesh)
    objects = mesh_objects()
    if not objects:
        raise RuntimeError("The generated mesh contains no mesh objects")

    apply_transforms(objects)
    faces_before = sum(len(obj.data.polygons) for obj in objects)
    faces = decimate(objects, args.target_faces)
    add_uvs(objects)

    material = make_material(args.texture)
    for obj in objects:
        obj.data.materials.clear()
        obj.data.materials.append(material)

    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(
        filepath=args.output,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_materials="EXPORT",
        export_image_format="AUTO",
    )

    size = os.path.getsize(args.output)
    if size <= 0:
        raise RuntimeError("Export produced an empty file")
    emit({
        "ok": True,
        "output": args.output,
        "bytes": size,
        "faces_before": faces_before,
        "faces": faces,
        "texture": "cutout-planar",
    })


try:
    main()
except Exception as exc:
    traceback.print_exc()
    emit({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
    sys.exit(1)
