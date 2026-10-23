# Builds a Kikkerland-style solar Rainbow Maker in Blender with a real, meshing gear train,
# bakes a seamless loop and exports FBX for Unity.
# Run: blender --background --python build-rainbow-maker-20261022.py -- <out_dir> [render]
import bpy, bmesh, math, sys, os
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else os.path.dirname(os.path.abspath(__file__))
DO_RENDER = "render" in argv
STAMP = "20261022"

# Layout is measured in pixels off the product photo; 1 px = 0.264 mm (whole thing ~14 cm tall).
PX = 0.000264
FPS = 30
LOOP_S = 30                     # seamless loop length
FRAMES = FPS * LOOP_S

# ---------- scene ----------
bpy.ops.wm.read_factory_settings(use_empty=True)
scn = bpy.context.scene
scn.render.fps = FPS
scn.frame_start, scn.frame_end = 1, FRAMES + 1
col = scn.collection
bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"

def mat(name, rgb, metal=0.0, rough=0.4, alpha=1.0, emit=None, transmission=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    b.inputs["Alpha"].default_value = alpha
    if transmission:
        b.inputs["Transmission Weight"].default_value = transmission
        b.inputs["IOR"].default_value = 1.5
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = 1.5
    if alpha < 1 and hasattr(m, "surface_render_method"):
        m.surface_render_method = "BLENDED"
    return m

M = {
    "clear":   mat("rm_clear_plastic", (0.85, 0.92, 1.0), rough=0.0, alpha=0.07),
    "red":     mat("rm_gear_red", (0.95, 0.05, 0.12), rough=0.3),
    "orange":  mat("rm_gear_orange", (1.0, 0.38, 0.0), rough=0.3),
    "yellow":  mat("rm_gear_yellow", (1.0, 0.85, 0.0), rough=0.3),
    "green":   mat("rm_gear_green", (0.1, 0.85, 0.15), rough=0.3),
    "blue":    mat("rm_gear_blue", (0.05, 0.35, 1.0), rough=0.3),
    "purple":  mat("rm_gear_purple", (0.55, 0.1, 0.9), rough=0.3),
    "copper":  mat("rm_copper_wire", (0.95, 0.5, 0.3), metal=1.0, rough=0.25),
    "bronze":  mat("rm_magnet_wheel", (0.35, 0.25, 0.15), metal=0.8, rough=0.35),
    "steel":   mat("rm_steel", (0.8, 0.8, 0.82), metal=1.0, rough=0.2),
    "panel":   mat("rm_solar_cell", (0.05, 0.08, 0.2), metal=0.3, rough=0.15),
    "panelbk": mat("rm_panel_back", (0.85, 0.7, 0.62), rough=0.5),
    "crystal": mat("rm_crystal", (0.92, 0.96, 1.0), metal=0.6, rough=0.02, alpha=0.55),
}

def link(obj, parent=None):
    col.objects.link(obj)
    if parent:
        obj.parent = parent
    return obj

def mesh_obj(name, bm, material, parent=None, smooth=False):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    for p in me.polygons:
        p.use_smooth = smooth
    me.materials.append(material)
    return link(bpy.data.objects.new(name, me), parent)

def empty(name, loc=(0, 0, 0), parent=None):
    e = bpy.data.objects.new(name, None)
    e.empty_display_size = 0.005
    e.location = loc
    return link(e, parent)

# Photo pixel (x right, y down) -> Blender (x right, z up); y is depth (toward viewer = -y).
DISC_C = (380, 210)
def P(x, y):
    return Vector(((x - DISC_C[0]) * PX, 0, -(y - DISC_C[1]) * PX))

# ---------- gear geometry ----------
MOD = 1.5  # module in px: pitch radius = MOD * teeth / 2

def gear_profile(n, mod):
    """Spur gear outline: n teeth, trapezoid teeth, pitch radius mod*n/2. Tooth 0 centred on +X."""
    rp = mod * n / 2
    ra, rd = rp + mod, rp - 1.25 * mod
    pts = []
    step = 2 * math.pi / n
    for i in range(n):
        a = i * step
        for da, r in ((-0.30, rd), (-0.17, ra), (0.17, ra), (0.30, rd)):
            # da is a fraction of the tooth pitch angle
            pts.append((r * math.cos(a + da * step), r * math.sin(a + da * step)))
    return pts

def spur(name, n, thick_px, material, parent, y_off_px=0.0, hub_r_px=None):
    """Gear in the XZ plane (axle along Y), centred on the parent empty."""
    bm = bmesh.new()
    pts = gear_profile(n, MOD)
    t = thick_px * PX
    y0 = y_off_px * PX
    top = [bm.verts.new((x * PX, y0 - t / 2, z * PX)) for x, z in pts]
    bot = [bm.verts.new((x * PX, y0 + t / 2, z * PX)) for x, z in pts]
    bm.faces.new(top[::-1]); bm.faces.new(bot)
    for i in range(len(pts)):
        j = (i + 1) % len(pts)
        bm.faces.new((top[i], top[j], bot[j], bot[i]))
    return mesh_obj(name, bm, material, parent)

def cylinder(name, r_px, length_px, material, parent=None, axis="Y", segs=24, center=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=r_px * PX,
                          radius2=r_px * PX, depth=length_px * PX)
    rot = {"Y": ("X", math.pi / 2), "X": ("Y", math.pi / 2), "Z": None}[axis]
    if rot:
        from mathutils import Matrix
        bmesh.ops.rotate(bm, verts=bm.verts, matrix=Matrix.Rotation(rot[1], 4, rot[0]))
    bmesh.ops.translate(bm, verts=bm.verts, vec=Vector(center))
    return mesh_obj(name, bm, material, parent, smooth=True)

# ---------- gear train (all speeds follow from tooth counts) ----------
# Each shaft: big gear (driven) + pinion (drives the next big gear). Every stage is 3:1.
# magnet wheel pinion 8 -> red 24 ; red pinion 8 -> ... wait, pinion = next big / 3.
TRAIN = [  # name, big teeth, pinion teeth, colour, photo position hint
    ("magnet_wheel", None, 8,  "bronze", (352, 185)),
    ("gear_red",     24,   10, "red",    (325, 170)),
    ("gear_orange",  30,   12, "orange", (316, 200)),
    ("gear_yellow",  36,   14, "yellow", (330, 235)),
    ("gear_green",   42,   None, "green", (375, 245)),
]
CROWN_T, BEVEL_T = 40, 8  # crown on the green shaft drives the purple pinion on the crystal shaft
LAYER = 6.0                # px between gear layers along the axle

root = empty("rainbow_maker")
housing = empty("housing", parent=root)

# Place gears back from green so each pair sits exactly at pitch-radius distance, in the photo's direction.
pos = {}
pos["gear_green"] = P(*TRAIN[4][4])
for i in range(3, -1, -1):
    name, big, pin, _, hint = TRAIN[i]
    nxt_name, nxt_big = TRAIN[i + 1][0], TRAIN[i + 1][1]
    dist = (MOD * pin / 2 + MOD * nxt_big / 2) * PX
    d = (P(*hint) - P(*TRAIN[i + 1][4])).normalized()
    pos[name] = pos[nxt_name] + d * dist

# Turns per loop for each shaft: crystal shaft = 5 (one turn every 6 s).
crystal_turns = 5
green_turns = crystal_turns * BEVEL_T / CROWN_T          # 1 turn
turns = {"gear_green": green_turns}
for i in range(3, -1, -1):
    name, _, pin, _, _ = TRAIN[i]
    nxt_name, nxt_big = TRAIN[i + 1][0], TRAIN[i + 1][1]
    turns[name] = -turns[nxt_name] * nxt_big / pin      # meshing gears counter-rotate

# Tooth phase so teeth interlock instead of overlapping: driven gear gets half a tooth offset.
phase = {"magnet_wheel": 0.0}
for i in range(4):
    a, b = TRAIN[i], TRAIN[i + 1]
    va = pos[b[0]] - pos[a[0]]
    theta = math.atan2(va.z, va.x)            # direction from driver to driven (in XZ)
    na, nb = a[2], b[1]
    da = phase[a[0]] - theta                  # driver tooth offset from contact line
    db = -(na / nb) * da + math.pi / nb       # driven gap offset
    phase[b[0]] = theta + math.pi + db

shafts = {}
for i, (name, big, pin, colr, _) in enumerate(TRAIN):
    s = empty(name, loc=pos[name], parent=housing)
    s.rotation_mode = "XYZ"
    shafts[name] = s
    # Layers step toward the viewer (-y): big gear meshes on the previous shaft's pinion layer.
    layer_big = -(i - 1) * LAYER + 10
    layer_pin = -i * LAYER + 10
    if big:
        spur(name + "_teeth", big, 3.0, M[colr], s, y_off_px=layer_big)
    else:  # magnet wheel: dark disc with two magnets that the coil kicks; drives via its pinion
        cylinder("magnet_wheel_disc", 13, 4, M["bronze"], s, center=(0, 16 * PX, 0))
        for k in (0, 1):
            cylinder(f"magnet_{k}", 3.2, 4.5, M["steel"], s, segs=12,
                     center=(math.cos(k * math.pi) * 9 * PX, 16 * PX, math.sin(k * math.pi) * 9 * PX))
    if pin:
        spur(name + "_pinion", pin, 3.0, M[colr], s, y_off_px=layer_pin)
    cylinder(name + "_axle", 1.2, 34, M["steel"], s, segs=10, center=(0, 8 * PX, 0))

# Crown gear on the green shaft (teeth on its back face) + purple pinion on the vertical crystal shaft.
g = shafts["gear_green"]
crown_r = MOD * CROWN_T / 2
crown_y = 6   # behind the green gear, teeth facing the back plate
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, segments=48, radius1=crown_r * PX, radius2=crown_r * PX, depth=2 * PX)
from mathutils import Matrix
bmesh.ops.rotate(bm, verts=bm.verts, matrix=Matrix.Rotation(math.pi / 2, 4, "X"))
bmesh.ops.translate(bm, verts=bm.verts, vec=Vector((0, crown_y * PX, 0)))
for k in range(CROWN_T):
    a = 2 * math.pi * k / CROWN_T
    c = Vector((math.cos(a) * (crown_r - 1.5) * PX, (crown_y + 2.2) * PX, math.sin(a) * (crown_r - 1.5) * PX))
    t = bmesh.ops.create_cube(bm, size=1)
    sc = Matrix.Diagonal((3.2 * PX, 2.4 * PX, 1.6 * PX, 1))
    bmesh.ops.transform(bm, verts=t["verts"], matrix=Matrix.Rotation(-a, 4, "Y") @ sc)
    bmesh.ops.translate(bm, verts=t["verts"], vec=c)
mesh_obj("crown_gear_blue", bm, M["blue"], g)

bevel_r = MOD * BEVEL_T / 2
shaft_pos = pos["gear_green"] + Vector((0, (crown_y + 2.2 + bevel_r) * PX, -(crown_r - 1.5) * PX))
crystal_shaft = empty("crystal_shaft", loc=shaft_pos, parent=housing)
crystal_shaft.rotation_mode = "XYZ"
pin_bm = bmesh.new()
pts = gear_profile(BEVEL_T, MOD)
t = 3 * PX
lo = [pin_bm.verts.new((x * PX, z * PX, -t)) for x, z in pts]
hi = [pin_bm.verts.new((x * PX * 0.8, z * PX * 0.8, 0)) for x, z in pts]   # tapered = bevel look
pin_bm.faces.new(lo[::-1]); pin_bm.faces.new(hi)
for i in range(len(pts)):
    j = (i + 1) % len(pts)
    pin_bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
mesh_obj("bevel_pinion_purple", pin_bm, M["purple"], crystal_shaft)
drop_px = (340 - 270) + 30
cylinder("crystal_shaft_rod", 1.6, drop_px, M["steel"], crystal_shaft, axis="Z", segs=12,
         center=(0, 0, -drop_px / 2 * PX))

# Crystal: faceted octagon hanging from a jump ring on the shaft end.
ring_z = -(drop_px + 6) * PX
rc = bpy.data.curves.new("jump_ring", "CURVE"); rc.dimensions = "3D"
rs = rc.splines.new("POLY"); rs.points.add(15); rs.use_cyclic_u = True
for k in range(16):
    a = 2 * math.pi * k / 16
    rs.points[k].co = (4 * PX * math.cos(a), 0, 4 * PX * math.sin(a), 1)
rc.bevel_depth = 0.9 * PX
ring = link(bpy.data.objects.new("jump_ring", rc), crystal_shaft)
ring.data.materials.append(M["steel"])
ring.location = (0, 0, ring_z)
bm = bmesh.new()
R, T = 52 * PX, 16 * PX
front = [bm.verts.new((R * math.cos(a), -T / 2, R * math.sin(a))) for a in [math.pi / 8 + k * math.pi / 4 for k in range(8)]]
back = [bm.verts.new((v.co.x, T / 2, v.co.z)) for v in front]
mid = [bm.verts.new((R * 1.08 * math.cos(a), 0, R * 1.08 * math.sin(a))) for a in [math.pi / 8 + k * math.pi / 4 for k in range(8)]]
cf = bm.verts.new((0, -T * 0.9, 0)); cb = bm.verts.new((0, T * 0.9, 0))
for i in range(8):
    j = (i + 1) % 8
    bm.faces.new((cf, front[j], front[i]))
    bm.faces.new((cb, back[i], back[j]))
    bm.faces.new((front[i], front[j], mid[j], mid[i]))
    bm.faces.new((mid[i], mid[j], back[j], back[i]))
crystal = mesh_obj("crystal", bm, M["crystal"], crystal_shaft)
crystal.location = (0, 0, ring_z - (4 + 52 * 1.08) * PX)

# ---------- housing ----------
cylinder("housing_disc_front", 100, 3, M["clear"], housing, center=(0, -14 * PX, 0), segs=64)
cylinder("housing_disc_back", 100, 3, M["clear"], housing, center=(0, 30 * PX, 0), segs=64)
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=False, segments=64, radius1=100 * PX, radius2=100 * PX, depth=44 * PX)
bmesh.ops.rotate(bm, verts=bm.verts, matrix=Matrix.Rotation(math.pi / 2, 4, "X"))
bmesh.ops.translate(bm, verts=bm.verts, vec=Vector((0, 8 * PX, 0)))
mesh_obj("housing_rim", bm, M["clear"], housing, smooth=True)
# metal motor plate behind the gears
bm = bmesh.new()
bmesh.ops.create_circle(bm, cap_ends=True, segments=40, radius=78 * PX)
bmesh.ops.rotate(bm, verts=bm.verts, matrix=Matrix.Rotation(math.pi / 2, 4, "X"))
bmesh.ops.translate(bm, verts=bm.verts, vec=Vector((0, 26 * PX, 0)))
mesh_obj("motor_plate", bm, M["steel"], housing)
# screws
for sx, sy in ((290, 205), (470, 205), (300, 260), (455, 260), (370, 120)):
    cylinder("screw", 4, 3, M["steel"], housing, center=P(sx, sy) + Vector((0, -16 * PX, 0)), segs=12)
# copper coil: helix of wire around a bobbin, tilted like the photo
coil = empty("coil", loc=P(410, 192) + Vector((0, -2 * PX, 0)), parent=housing)
coil.rotation_euler = (0, math.radians(-17), 0)
cylinder("coil_bobbin", 13, 92, M["clear"], coil, axis="Z")
cu = bpy.data.curves.new("coil_wire", "CURVE"); cu.dimensions = "3D"
sp = cu.splines.new("POLY")
TURNS, PERT = 70, 24
sp.points.add(TURNS * PERT - 1)
for k in range(TURNS * PERT):
    a = 2 * math.pi * k / PERT
    layer = 16
    sp.points[k].co = (layer * PX * math.cos(a), layer * PX * math.sin(a), (-40 + 80 * k / (TURNS * PERT)) * PX, 1)
cu.bevel_depth = 1.1 * PX; cu.bevel_resolution = 1
wire = link(bpy.data.objects.new("coil_wire", cu), coil)
wire.data.materials.append(M["copper"])
for end in (-1, 1):
    cylinder("coil_flange", 21, 3, M["steel"], coil, axis="Z", center=(0, 0, end * 44 * PX), segs=24)
# neck + solar panel on top
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1)
bmesh.ops.scale(bm, vec=(60 * PX, 30 * PX, 40 * PX), verts=bm.verts)
mesh_obj("neck", bm, M["clear"], housing).location = P(375, 108) + Vector((0, 8 * PX, 0))
panel = empty("solar_panel", loc=P(372, 50) + Vector((0, 8 * PX, 0)), parent=housing)
for nm, sz, y, m_ in (("panel_frame", (160, 26, 90), 0, "clear"), ("panel_back", (148, 2, 78), -9, "panelbk"),
                      ("panel_cells", (148, 2, 78), 9, "panel")):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1)
    bmesh.ops.scale(bm, vec=(sz[0] * PX, sz[1] * PX, sz[2] * PX), verts=bm.verts)
    o = mesh_obj(nm, bm, M[m_], panel); o.location = (0, y * PX, 0)
for k in range(1, 4):   # cell grid lines
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1)
    bmesh.ops.scale(bm, vec=(148 * PX, 1 * PX, 1.2 * PX), verts=bm.verts)
    o = mesh_obj("cell_line", bm, M["steel"], panel); o.location = (0, 10.2 * PX, (-39 + k * 19.5) * PX)
# suction cup on the window side of the panel
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, segments=32, radius1=26 * PX, radius2=8 * PX, depth=12 * PX)
bmesh.ops.rotate(bm, verts=bm.verts, matrix=Matrix.Rotation(-math.pi / 2, 4, "X"))
cup = mesh_obj("suction_cup", bm, M["clear"], panel, smooth=True); cup.location = (0, 27 * PX, 0)
# spout under the disc that holds the crystal shaft
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=7 * PX, radius2=22 * PX, depth=46 * PX)
spout = mesh_obj("spout", bm, M["clear"], housing, smooth=True)
spout.location = Vector((shaft_pos.x, shaft_pos.y, shaft_pos.z - 26 * PX))

# ---------- animation: linear, seamless loop ----------
def spin(obj, axis_idx, turns_, base=0.0):
    obj.rotation_euler[axis_idx] = base
    obj.keyframe_insert("rotation_euler", index=axis_idx, frame=1)
    obj.rotation_euler[axis_idx] = base + turns_ * 2 * math.pi
    obj.keyframe_insert("rotation_euler", index=axis_idx, frame=FRAMES + 1)

# Blender's Y-axis rotation is clockwise when viewed from -Y (the viewer), so flip sign for the photo view.
for name, s in shafts.items():
    spin(s, 1, -turns[name], base=-phase[name])
spin(crystal_shaft, 2, crystal_turns)
# Make every key linear (works for both layered and legacy actions).
for ob in bpy.data.objects:
    ad = ob.animation_data
    if ad and ad.action:
        curves = []
        if hasattr(ad.action, "fcurves"):
            try:
                curves = list(ad.action.fcurves)
            except Exception:
                curves = []
        if not curves and hasattr(ad.action, "layers"):
            for L in ad.action.layers:
                for st in L.strips:
                    for cb in st.channelbags:
                        curves += list(cb.fcurves)
        for fc in curves:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"

print("TURNS PER LOOP:", {k: round(v, 3) for k, v in turns.items()}, "crystal:", crystal_turns)

# ---------- camera + light for preview ----------
cam = bpy.data.objects.new("preview_camera", bpy.data.cameras.new("preview_camera"))
col.objects.link(cam)
cam.location = (0.06, -0.40, -0.013)
cam.rotation_euler = (math.radians(90), 0, math.radians(8.5))
cam.data.lens = 85
scn.camera = cam
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 2.0
scn.view_settings.view_transform = "Standard"
scn.view_settings.exposure = -1.3
sun.rotation_euler = (math.radians(60), math.radians(-20), math.radians(-30))
col.objects.link(sun)
key = bpy.data.objects.new("key_light", bpy.data.lights.new("key_light", "AREA"))
key.data.energy, key.data.size = 6, 0.3
key.location = (-0.15, -0.3, 0.1)
key.rotation_euler = (math.radians(70), 0, math.radians(-25))
col.objects.link(key)
if "closeup" in argv:
    cam.data.lens = 220
    cam.location = (0.0, -0.40, 0.0)
    cam.rotation_euler = (math.radians(90), 0, 0)
world =bpy.data.worlds.new("bg"); scn.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.15, 0.15, 0.17, 1)  # graphite gray

# Curves (coil wire, jump ring) become real meshes so Unity gets them.
dg = bpy.context.evaluated_depsgraph_get()
for ob in [o for o in bpy.data.objects if o.type == "CURVE"]:
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    new = bpy.data.objects.new(ob.name, me)
    new.parent, new.matrix_parent_inverse = ob.parent, ob.matrix_parent_inverse.copy()
    new.location, new.rotation_euler = ob.location.copy(), ob.rotation_euler.copy()
    col.objects.link(new)
    bpy.data.objects.remove(ob)
    new.name = new.name.split(".")[0]

os.makedirs(OUT, exist_ok=True)
blend = os.path.join(OUT, f"rainbow-maker-{STAMP}.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend)

# ---------- FBX for Unity ----------
fbx = os.path.join(OUT, f"rainbow-maker-{STAMP}.fbx")
for o in bpy.data.objects:
    o.select_set(o.type in {"MESH", "CURVE", "EMPTY"})
bpy.ops.export_scene.fbx(filepath=fbx, use_selection=True, object_types={"EMPTY", "MESH", "OTHER"},
                         apply_scale_options="FBX_SCALE_ALL", axis_forward="-Z", axis_up="Y",
                         bake_anim=True, bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False,
                         # only the spinning shafts get keys; a keyed root would pin the model to the
                         # world origin at 1x scale when Unity's Animator plays the clip
                         bake_anim_force_startend_keying=False, bake_anim_simplify_factor=0.0,
                         use_mesh_modifiers=True, add_leaf_bones=False)
print("WROTE", blend, fbx)

if DO_RENDER or "still" in argv:
    eng = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    scn.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in eng else "BLENDER_EEVEE"
    scn.render.resolution_x, scn.render.resolution_y = 540, 960
    scn.render.film_transparent = False
if "still" in argv:
    scn.frame_set(int(argv[argv.index("still") + 1]) if len(argv) > argv.index("still") + 1 else 1)
    scn.render.image_settings.file_format = "PNG"
    scn.render.filepath = os.path.join(OUT, f"rainbow-maker-check-{STAMP}.png")
    bpy.ops.render.render(write_still=True)
if DO_RENDER:
    scn.frame_start, scn.frame_end = 1, 150
    scn.render.image_settings.file_format = "FFMPEG"
    scn.render.ffmpeg.format = "MPEG4"
    scn.render.ffmpeg.codec = "H264"
    scn.render.filepath = os.path.join(OUT, f"rainbow-maker-preview-{STAMP}.mp4")
    bpy.ops.render.render(animation=True)
    scn.render.image_settings.file_format = "PNG"
    scn.frame_set(1)
    scn.render.filepath = os.path.join(OUT, f"rainbow-maker-still-{STAMP}.png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED")
