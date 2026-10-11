"""Render preview images of a GLB (front / side / three-quarter) to verify fit.

  blender --background --python render_preview.py -- --glb model.glb --out path\\prefix
"""

import argparse
import os
import sys

import bpy
from mathutils import Vector


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    parser = argparse.ArgumentParser()
    parser.add_argument("--glb", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=args.glb)

    objs = [o for o in bpy.data.objects if o.type == "MESH"]
    mins = Vector((1e9, 1e9, 1e9))
    maxs = Vector((-1e9, -1e9, -1e9))
    for o in objs:
        for corner in o.bound_box:
            w = o.matrix_world @ Vector(corner)
            for i in range(3):
                mins[i] = min(mins[i], w[i])
                maxs[i] = max(maxs[i], w[i])
    center = (mins + maxs) * 0.5
    height = (maxs - mins).z
    print("BBOX", [round(v, 3) for v in mins], [round(v, 3) for v in maxs], flush=True)

    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 480
    scene.render.resolution_y = 720
    scene.render.film_transparent = False
    scene.world = bpy.data.worlds.new("W")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.9, 0.9, 0.88, 1.0)
        bg.inputs[1].default_value = 1.0

    light_data = bpy.data.lights.new("Sun", type="SUN")
    light_data.energy = 3.0
    light = bpy.data.objects.new("Sun", light_data)
    light.rotation_euler = (0.6, 0.2, -0.4)
    scene.collection.objects.link(light)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50
    cam = bpy.data.objects.new("Cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam

    dist = height * 1.5
    views = {
        "front": Vector((0.0, -1.0, 0.0)),
        "threeq": Vector((0.7, -0.9, 0.1)),
        "side": Vector((1.0, 0.0, 0.0)),
    }
    for name, direction in views.items():
        direction = direction.normalized()
        cam.location = center + direction * dist
        to_target = (center - cam.location).normalized()
        cam.rotation_euler = to_target.to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = f"{args.out}_{name}.png"
        bpy.ops.render.render(write_still=True)
        print("WROTE", scene.render.filepath, flush=True)


main()
