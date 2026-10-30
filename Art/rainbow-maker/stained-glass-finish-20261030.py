"""Persistent glass finish and model-only exports; called by the existing builder.

Preserves the measured assembly, shafts, crystal cut and 120-second animation.
No downloaded textures or add-ons. Studio scenery never enters the GLB/FBX.
"""
import bpy
import bmesh
import math
import os
import json
from mathutils import Vector

DATE = "20261030"


def apply_modifier(obj, modifier):
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    obj.select_set(False)


def principled(material, color, roughness, transmission=0, ior=1.5, metal=0):
    nt = material.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bs.inputs["Base Color"].default_value = (*color, 1)
    bs.inputs["Roughness"].default_value = roughness
    bs.inputs["Metallic"].default_value = metal
    bs.inputs["IOR"].default_value = ior
    bs.inputs["Transmission Weight"].default_value = transmission
    bs.inputs["Alpha"].default_value = 1
    nt.links.new(bs.outputs[0], out.inputs["Surface"])
    material.diffuse_color = (*color, 1)
    if hasattr(material, "surface_render_method"):
        material.surface_render_method = "DITHERED"
    return bs, out


def thickness(material, value):
    group = bpy.data.node_groups.get("glTF Material Output")
    if group is None:
        group = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
        group.interface.new_socket(name="Thickness", in_out="INPUT", socket_type="NodeSocketFloat")
        group.nodes.new("NodeGroupInput")
        group.nodes.new("NodeGroupOutput")
    node = material.node_tree.nodes.new("ShaderNodeGroup")
    node.node_tree = group
    node.inputs["Thickness"].default_value = value


def crystal_dispersion(material):
    # RGB spectral approximation for Cycles, retained from the prior local work.
    # Use a restrained spread around lead crystal's IOR instead of diamond values.
    nt = material.node_tree
    glasses = []
    for color, ior in (((1, 0, 0, 1), 1.60), ((0, 1, 0, 1), 1.62), ((0, 0, 1, 1), 1.65)):
        glass = nt.nodes.new("ShaderNodeBsdfGlass")
        glass.inputs["Color"].default_value = color
        glass.inputs["IOR"].default_value = ior
        glass.inputs["Roughness"].default_value = 0.012
        glasses.append(glass)
    a, b = nt.nodes.new("ShaderNodeAddShader"), nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(glasses[0].outputs[0], a.inputs[0])
    nt.links.new(glasses[1].outputs[0], a.inputs[1])
    nt.links.new(a.outputs[0], b.inputs[0])
    nt.links.new(glasses[2].outputs[0], b.inputs[1])
    nt.links.new(b.outputs[0], nt.nodes.get("Material Output").inputs["Surface"])


def finish(ctx):
    scn, root, mats = ctx["scn"], ctx["root"], ctx["M"]
    argv, outdir, px = ctx["argv"], os.path.abspath(ctx["OUT"]), ctx["PX"]
    os.makedirs(outdir, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    model = [root] + list(root.children_recursive)

    # REAL's fine enamel coil replaces the coarse coil in every exported asset too.
    if bpy.data.objects.get("coil_strands_0"):
        old = bpy.data.objects.get("coil_wire")
        if old:
            bpy.data.objects.remove(old, do_unlink=True)
    dg = bpy.context.evaluated_depsgraph_get()
    for obj in list(root.children_recursive):
        if obj.type != "CURVE":
            continue
        # Low tube subdivision is enough at this real-world wire diameter.
        obj.data.bevel_resolution = 0
        obj.data.use_fill_caps = True
        bpy.context.view_layer.update()
        mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(bpy.context.evaluated_depsgraph_get()))
        for face in mesh.polygons:
            face.use_smooth = True
        replacement = bpy.data.objects.new(obj.name + "_mesh", mesh)
        scn.collection.objects.link(replacement)
        replacement.parent = obj.parent
        replacement.matrix_parent_inverse = obj.matrix_parent_inverse.copy()
        replacement.matrix_basis = obj.matrix_basis.copy()
        name = obj.name
        bpy.data.objects.remove(obj, do_unlink=True)
        replacement.name = name

    # Saturated but nonzero channels keep colored glass from becoming black on
    # repeated transmission. Surface reflection stays white because metal=0.
    colors = {
        "red": (0.9, 0.16, 0.11), "orange": (1.0, 0.42, 0.08),
        "yellow": (1.0, 0.82, 0.17), "lime": (0.53, 0.94, 0.14),
        "green": (0.12, 0.77, 0.26), "blue": (0.10, 0.38, 0.94),
        "teal": (0.07, 0.66, 0.77), "purple": (0.56, 0.18, 0.86),
        "coral": (0.96, 0.24, 0.31),
    }
    for key, color in colors.items():
        material = mats[key]
        bs, out = principled(material, color, 0.045, 1.0, 1.52)
        bs.inputs["Coat Weight"].default_value = 0.18
        bs.inputs["Coat Roughness"].default_value = 0.025
        thickness(material, 0.000792)
        material["finish"] = "Polished stained glass; dielectric reflection and colored transmission"

    principled(mats["clear"], (0.98, 0.995, 1.0), 0.026, 1.0, 1.49)
    solid = bpy.data.materials.get("rm_solid_acrylic")
    if solid:
        principled(solid, (0.98, 0.995, 1.0), 0.022, 1.0, 1.49)
    # A single physical dielectric also survives glTF export. Retain the newer
    # steep crystal geometry instead of using three added RGB glass shaders.
    bs, _ = principled(mats["crystal"], (0.985, 0.995, 1), 0.012, 1.0, 1.62)
    bs.inputs["Coat Weight"].default_value = 0.12
    bs.inputs["Coat Roughness"].default_value = 0.01
    thickness(mats["crystal"], 0.010)
    principled(mats["panelbk"], (0.035, 0.018, 0.016), 0.11, metal=0.2)

    model = [root] + list(root.children_recursive)
    for obj in model:
        if obj.type != "MESH":
            continue
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        if obj.name.startswith("u_cap_"):
            # The cap opens onto the main case. A second closed rear plate here
            # was coincident with the case front and caused dark refractive stacks.
            rear_y = max(v.co.y for v in bm.verts)
            rear = [f for f in bm.faces if all(abs(v.co.y - rear_y) < 1e-7 for v in f.verts)]
            bmesh.ops.delete(bm, geom=rear, context="FACES")
        if obj.name.startswith(("sleeve_", "collar_")):
            # Open tubes: remove coincident end membranes where sleeve sections
            # and collars meet. Solidify closes the wall into a thin annular rim.
            caps = [f for f in bm.faces if abs(f.normal.z) > 0.99]
            bmesh.ops.delete(bm, geom=caps, context="FACES")
        bm.to_mesh(obj.data)
        bm.free()

        is_gear = any(m and m.name.startswith("rm_gear_") for m in obj.data.materials)
        is_shell = obj.name.startswith(("housing_case", "u_cap_", "panel_frame", "neck", "sleeve_", "collar_", "suction_cup"))
        if is_gear or is_shell:
            bevel = obj.modifiers.new("Polished edge", "BEVEL")
            bevel.width = (0.22 if is_gear else 0.40) * px
            bevel.segments = 3
            bevel.limit_method = "ANGLE"
            bevel.angle_limit = math.radians(25)
            apply_modifier(obj, bevel)
        if is_shell:
            # A real thin shell avoids refracting through an 11 mm solid block.
            shell = obj.modifiers.new("Hollow acrylic wall", "SOLIDIFY")
            shell.thickness = 0.00020
            shell.offset = -1.0
            shell.use_even_offset = True
            apply_modifier(obj, shell)
            obj.data.materials.clear()
            obj.data.materials.append(mats["clear"])
        if is_gear:
            # Subtle actual cut facets, portable to GLB: triangulate each broad
            # face around its center, subdivide those triangles, then displace
            # their interior by tens of micrometres. The toothed perimeter stays
            # fixed, so tooth contact and clearance do not change.
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            broad = [f for f in bm.faces if len(f.verts) > 12 and abs(f.normal.y) > 0.98]
            for face in broad:
                bmesh.ops.poke(bm, faces=[face], offset=0, center_mode="MEAN_WEIGHTED")
            edges = [e for e in bm.edges if len(e.link_faces) == 2 and all(abs(f.normal.y) > 0.98 for f in e.link_faces)]
            if edges:
                bmesh.ops.subdivide_edges(bm, edges=edges, cuts=1, use_grid_fill=True)
            bm.normal_update()
            # Only vertices surrounded by front/back faces receive relief.
            for v in bm.verts:
                if v.link_faces and all(abs(f.normal.y) > 0.98 for f in v.link_faces):
                    x, z = v.co.x / px, v.co.z / px
                    wave = math.sin(x * 0.30 + z * 0.13) * math.cos(z * 0.24 - x * 0.11)
                    v.co.y += 0.14 * px * wave
            bmesh.ops.triangulate(bm, faces=bm.faces[:])
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
            bm.to_mesh(obj.data)
            bm.free()
            # Smooth the shallow glass relief without rounding tooth silhouettes.
            # This avoids the old radial triangle streaks on the broad face.
            for face in obj.data.polygons:
                face.use_smooth = abs(face.normal.y) > 0.75
            obj.data.set_sharp_from_angle(angle=math.radians(15))

    scn.frame_set(1)
    bpy.context.view_layer.update()
    if "studio" in argv:
        studio(scn, root, ctx["cam"], argv)
    scn.render.engine = "CYCLES"
    scn.cycles.samples = 128
    scn.cycles.use_denoising = True
    scn.cycles.max_bounces = 24
    scn.cycles.transmission_bounces = 20
    scn.cycles.transparent_max_bounces = 16
    scn.cycles.glossy_bounces = 12
    scn.cycles.sample_clamp_indirect = 10
    scn.cycles.time_limit = 55 if "draft" in argv else 120
    scn.render.use_motion_blur = False
    scn.view_settings.view_transform = "AgX"
    scn.view_settings.look = "AgX - Medium High Contrast"
    scn.view_settings.exposure = 0
    scn.render.resolution_x, scn.render.resolution_y = ((750, 1000) if "draft" in argv else (1500, 2000))
    scn.render.resolution_percentage = 100
    if "gearview" in argv:
        cam = scn.camera
        cam.location = (0.035, -0.245, -0.012)
        target = Vector((0, 0, -0.016))
        cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = 0.066
        scn.render.resolution_x = scn.render.resolution_y = 1200 if "draft" not in argv else 800

    # Select exactly the assembly; cameras/lights/background never enter model files.
    bpy.ops.object.select_all(action="DESELECT")
    model = [root] + list(root.children_recursive)
    for obj in model:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = root
    root["animation_seconds"] = 120
    root["finish_version"] = DATE
    root["units"] = "metres"

    report = {"version": DATE, "loop_seconds": 120, "objects": [], "material_transmission": {}, "bounds_m": {}}
    corners = []
    for obj in model:
        if obj.type != "MESH":
            continue
        obj.data.calc_loop_triangles()
        bm = bmesh.new(); bm.from_mesh(obj.data)
        item = {"name": obj.name, "triangles": len(obj.data.loop_triangles),
                "nonmanifold_edges": sum(not e.is_manifold for e in bm.edges),
                "signed_volume_m3": bm.calc_volume(signed=True)}
        bm.free()
        report["objects"].append(item)
        corners.extend(obj.matrix_world @ Vector(c) for c in obj.bound_box)
    report["total_triangles"] = sum(o["triangles"] for o in report["objects"])
    report["bounds_m"] = {"min": [min(c[i] for c in corners) for i in range(3)], "max": [max(c[i] for c in corners) for i in range(3)]}
    for key in colors:
        report["material_transmission"][key] = mats[key].node_tree.nodes.get("Principled BSDF").inputs["Transmission Weight"].default_value
    with open(os.path.join(outdir, f"rainbow-maker-validation-{DATE}.json"), "w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)

    if "noexport" not in argv:
        # FBX retains hierarchy/animation; Unity uses its own material shaders.
        bpy.ops.export_scene.fbx(filepath=os.path.join(outdir, f"rainbow-maker-glass-{DATE}.fbx"),
            use_selection=True, object_types={"EMPTY", "MESH"}, apply_scale_options="FBX_SCALE_ALL",
            axis_forward="-Z", axis_up="Y", bake_anim=True, bake_anim_use_all_actions=False,
            bake_anim_use_nla_strips=False, bake_anim_force_startend_keying=False,
            bake_anim_simplify_factor=0, use_mesh_modifiers=True, add_leaf_bones=False, use_triangles=True)
        # Typical WebGL transmission passes cannot see another transmissive
        # object behind the case. Use a reflective alpha shell for the WEB copy
        # while leaving the actual colored gears/crystals as volume transmission.
        web_shell = mats["clear"].copy()
        web_shell.name = "rm_clear_web_shell"
        bs, _ = principled(web_shell, (0.93, 0.97, 1), 0.04, 0, 1.49)
        bs.inputs["Alpha"].default_value = 0.025
        web_shell.surface_render_method = "BLENDED"
        changes = []
        for obj in model:
            if obj.type == "MESH":
                for index, material in enumerate(obj.data.materials):
                    if material == mats["clear"] or material == solid:
                        changes.append((obj, index, material))
                        obj.data.materials[index] = web_shell
        try:
            bpy.ops.export_scene.gltf(filepath=os.path.join(outdir, f"rainbow-maker-glass-{DATE}.glb"),
                export_format="GLB", use_selection=True, export_apply=True, export_animations=True,
                export_animation_mode="SCENE", export_anim_scene_split_object=False,
                export_anim_slide_to_zero=True,
                export_frame_range=True, export_frame_step=2,
                export_force_sampling=True, export_cameras=False, export_lights=False, export_extras=True)
        finally:
            for obj, index, material in changes:
                obj.data.materials[index] = material
            bpy.data.materials.remove(web_shell)
    crystal_dispersion(mats["crystal"])
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(outdir, f"rainbow-maker-glass-{DATE}.blend"))
    print("GLASS FINISH", report["total_triangles"], "triangles", report["bounds_m"])


def studio(scn, root, cam, argv):
    keep = {root, cam, *root.children_recursive}
    for obj in list(bpy.data.objects):
        if obj not in keep:
            bpy.data.objects.remove(obj, do_unlink=True)
    nt = scn.world.node_tree
    nt.nodes.clear()
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs[0].default_value = (0.13, 0.16, 0.21, 1)
    bg.inputs[1].default_value = 0.6
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(bg.outputs[0], out.inputs[0])

    def area(name, loc, energy, size, size_y, target=(0, 0, -0.03), color=(1, 1, 1)):
        obj = bpy.data.objects.new(name, bpy.data.lights.new(name, "AREA"))
        scn.collection.objects.link(obj)
        obj.location = loc
        obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
        obj.data.shape = "RECTANGLE"
        obj.data.energy, obj.data.size, obj.data.size_y = energy, size, size_y
        obj.data.color = color
        return obj
    area("studio_key", (-0.16, -0.15, 0.09), 1.0, 0.035, 0.24)
    area("studio_strip", (0.15, -0.11, -0.02), 1.0, 0.016, 0.25)
    area("studio_top", (0.02, -0.03, 0.18), 1.5, 0.15, 0.03)
    area("studio_front_strip", (-0.085, -0.30, 0.025), 0.6, 0.006, 0.16)
    area("studio_backlight", (-0.10, 0.08, 0.025), 0.5, 0.09, 0.19, color=(1.0, 0.95, 0.87))
    # Bright cards behind the glass make transmission readable and offer strong
    # internal-reflection contrast without downloading an environment map.
    backdrop = bpy.data.materials.new("studio_backdrop")
    backdrop.use_nodes = True
    bs, _ = principled(backdrop, (0.015, 0.025, 0.045), 0.85)
    bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0.16, -0.025), rotation=(math.pi / 2, 0, 0))
    panel = bpy.context.object
    panel.name = "studio_backdrop"
    panel.scale = (0.4, 0.4, 0.4)
    panel.data.materials.append(backdrop)
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 0.185
    cam.data.dof.use_dof = False
    cam.location = (0.045, -0.42, -0.020)
    target = Vector((0, 0, -0.027))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    scn.camera = cam
