"""Build a small 2.5D GLB from a wardrobe item's cutout PNG.

The cutout is the only per-item visual information we have (the detector already
removed the background). The script samples the alpha mask on a grid, keeps the
cells that belong to the garment, extrudes them into a thin closed shell, and
maps the original cutout onto the shell as a texture.

Run:
  blender --background --python generate_item_mesh.py -- \
      --cutout item.png --output item.glb --slot top --max-size 0.65

It prints one machine-readable line:
  ITEM_MESH_RESULT {"ok": true, "bytes": ..., "width": ..., ...}
"""

import argparse
import json
import sys
import traceback

import bmesh
import bpy

GRID_MAX = 160
ALPHA_THRESHOLD = 0.16
DEFAULT_THICKNESS = 0.006

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
    print("ITEM_MESH_RESULT " + json.dumps(payload), flush=True)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cutout", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--slot", default="top")
    parser.add_argument("--max-size", type=float, default=None)
    parser.add_argument("--thickness", type=float, default=DEFAULT_THICKNESS)
    parser.add_argument("--grid", type=int, default=GRID_MAX)
    args, _unknown = parser.parse_known_args(sys.argv[sys.argv.index("--") + 1:])
    return args


def load_cutout(path, grid):
    texture = bpy.data.images.load(path, check_existing=False)
    texture.pack()

    work = texture.copy()
    width, height = work.size
    if width <= 0 or height <= 0:
        raise RuntimeError("The cutout has no pixels")
    scale = min(1.0, float(grid) / max(width, height))
    grid_w = max(4, int(round(width * scale)))
    grid_h = max(4, int(round(height * scale)))
    if (grid_w, grid_h) != (width, height):
        work.scale(grid_w, grid_h)
    if tuple(work.size) != (grid_w, grid_h):
        grid_w, grid_h = work.size
    return texture, work, grid_w, grid_h


def alpha_grid(image, width, height):
    pixels = list(image.pixels)
    if len(pixels) < width * height * 4:
        raise RuntimeError("The cutout pixel buffer is incomplete")

    def alpha(x, y):
        index = (y * width + x) * 4 + 3
        return pixels[index]

    cells = []
    for y in range(height - 1):
        for x in range(width - 1):
            a = (alpha(x, y) + alpha(x + 1, y) + alpha(x, y + 1) + alpha(x + 1, y + 1)) / 4.0
            if a >= ALPHA_THRESHOLD:
                cells.append((x, y))
    return cells


def build_mesh(cells, grid_w, grid_h):
    bm = bmesh.new()
    verts = {}

    def vertex(x, y):
        key = (x, y)
        if key not in verts:
            verts[key] = bm.verts.new((float(x), 0.0, float(y)))
        return verts[key]

    uv_layer = bm.loops.layers.uv.new("UVMap")
    for x, y in cells:
        v00 = vertex(x, y)
        v10 = vertex(x + 1, y)
        v11 = vertex(x + 1, y + 1)
        v01 = vertex(x, y + 1)
        face = bm.faces.new((v00, v10, v11, v01))
        for loop, (px, py) in zip(face.loops, ((x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1))):
            loop[uv_layer].uv = (px / grid_w, py / grid_h)

    if not bm.faces:
        bm.free()
        raise RuntimeError("The cutout alpha channel is empty")

    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    mesh = bpy.data.meshes.new("item_mesh")
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new("item_mesh", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def normalise(obj, cells, grid_w, grid_h, target_size, thickness):
    min_x = min(x for x, _ in cells)
    max_x = max(x for x, _ in cells) + 1
    min_y = min(y for _, y in cells)
    max_y = max(y for _, y in cells) + 1
    width_units = max(1, max_x - min_x)
    height_units = max(1, max_y - min_y)

    for vertex in obj.data.vertices:
        vertex.co.x -= (min_x + max_x) * 0.5
        vertex.co.z -= min_y
    obj.data.update()

    factor = target_size / max(width_units, height_units)
    obj.scale = (factor, factor, factor)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    solid = obj.modifiers.new("Thickness", "SOLIDIFY")
    solid.thickness = thickness
    solid.offset = 0.0
    solid.use_even_offset = True
    bpy.ops.object.modifier_apply(modifier=solid.name)
    obj.data.validate(verbose=False)

    # Center the thickness around the plane, then sit the item on y=0 in Blender
    # (after the glTF Z-up -> Y-up conversion this is the viewer's ground plane).
    for vertex in obj.data.vertices:
        vertex.co.y -= thickness * 0.5
    obj.data.update()
    return obj.dimensions.copy()


def make_material(texture, name="item_material"):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.diffuse_color = (0.8, 0.8, 0.8, 1.0)

    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    image_node = nodes.new("ShaderNodeTexImage")
    image_node.image = texture
    image_node.interpolation = "Linear"
    image_node.extension = "CLIP"
    links.new(image_node.outputs["Color"], bsdf.inputs["Base Color"])
    if "Alpha" in bsdf.inputs:
        links.new(image_node.outputs["Alpha"], bsdf.inputs["Alpha"])

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


def main():
    args = parse_args()
    bpy.ops.wm.read_factory_settings(use_empty=True)

    texture, work, grid_w, grid_h = load_cutout(args.cutout, args.grid)
    cells = alpha_grid(work, grid_w, grid_h)
    obj = build_mesh(cells, grid_w, grid_h)

    target_size = args.max_size or SLOT_MAX_SIZE.get(args.slot, 0.6)
    dimensions = normalise(obj, cells, grid_w, grid_h, target_size, args.thickness)

    obj.data.materials.append(make_material(texture))
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    output = args.output
    bpy.ops.export_scene.gltf(
        filepath=output,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_materials="EXPORT",
        export_image_format="AUTO",
    )

    import os
    size = os.path.getsize(output)
    if size <= 0:
        raise RuntimeError("Export produced an empty file")

    emit({
        "ok": True,
        "bytes": size,
        "output": output,
        "slot": args.slot,
        "grid": [grid_w, grid_h],
        "faces": len(obj.data.polygons),
        "width": round(float(dimensions.x), 4),
        "height": round(float(dimensions.z), 4),
        "depth": round(float(dimensions.y), 4),
        "thickness": args.thickness,
    })


try:
    main()
except Exception as exc:
    traceback.print_exc()
    emit({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
    sys.exit(1)
