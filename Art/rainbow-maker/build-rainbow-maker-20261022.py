# Builds Astra's double-crystal Kikkerland solar Rainbow Maker in Blender with a real, meshing gear train,
# bakes a seamless loop and exports FBX for Unity.
# Run: blender --background --python build-rainbow-maker-20261022.py -- <out_dir> [still N] [closeup|angle] [render]
# Layout comes from Astra's own photos (2026-10-23), measured in "model px": 1 px = 0.264 mm, origin = centre of the
# main disc, x to the right and y DOWN as seen from the room.
import bpy, bmesh, math, sys, os
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else os.path.dirname(os.path.abspath(__file__))
DO_RENDER = "render" in argv
STAMP = "20261022"   # file names stay the same so Unity keeps the FBX's GUID

PX = 0.000264
FPS = 30
LOOP_S = 60                     # seamless loop length
FRAMES = FPS * LOOP_S

# ---------- scene ----------
bpy.ops.wm.read_factory_settings(use_empty=True)
scn = bpy.context.scene
scn.render.fps = FPS
scn.frame_start, scn.frame_end = 1, FRAMES + 1
col = scn.collection
bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"

def mat(name, rgb, metal=0.0, rough=0.4, alpha=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    b.inputs["Alpha"].default_value = alpha
    if alpha < 1 and hasattr(m, "surface_render_method"):
        m.surface_render_method = "BLENDED"
    return m

M = {
    "clear":   mat("rm_clear_plastic", (0.85, 0.92, 1.0), rough=0.0, alpha=0.04),
    "red":     mat("rm_gear_red", (0.85, 0.08, 0.05), rough=0.3),
    "orange":  mat("rm_gear_orange", (1.0, 0.35, 0.0), rough=0.3),
    "yellow":  mat("rm_gear_yellow", (1.0, 0.85, 0.0), rough=0.3),
    "lime":    mat("rm_gear_lime", (0.35, 0.95, 0.1), rough=0.3),
    "green":   mat("rm_gear_green", (0.1, 0.85, 0.15), rough=0.3),
    "blue":    mat("rm_gear_blue", (0.05, 0.35, 1.0), rough=0.3),
    "teal":    mat("rm_gear_teal", (0.0, 0.45, 0.55), rough=0.3),
    "purple":  mat("rm_gear_purple", (0.55, 0.1, 0.9), rough=0.3),
    "coral":   mat("rm_gear_coral", (0.95, 0.3, 0.25), rough=0.3),
    "copper":  mat("rm_copper_wire", (0.75, 0.38, 0.2), metal=1.0, rough=0.3),
    "brass":   mat("rm_magnet_wheel", (0.7, 0.55, 0.3), metal=0.9, rough=0.3),
    "steel":   mat("rm_steel", (0.8, 0.8, 0.82), metal=1.0, rough=0.2),
    "black":   mat("rm_black_metal", (0.03, 0.03, 0.035), metal=0.6, rough=0.4),
    "screw":   mat("rm_screw", (0.02, 0.02, 0.02), metal=0.5, rough=0.35),
    "panel":   mat("rm_solar_cell", (0.12, 0.06, 0.05), metal=0.3, rough=0.15),
    "panelbk": mat("rm_panel_back", (0.2, 0.11, 0.08), rough=0.5),
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

def P(x, y, depth=0.0):
    """model px (x right, y down, depth toward the glass) -> Blender (x right, z up, -y toward the room)."""
    return Vector((x * PX, depth * PX, -y * PX))

def cylinder(name, r_px, length_px, material, parent=None, axis="Y", segs=24, center=(0, 0, 0), r2_px=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=r_px * PX,
                          radius2=(r2_px if r2_px is not None else r_px) * PX, depth=length_px * PX)
    rot = {"Y": ("X", -math.pi / 2), "X": ("Y", math.pi / 2), "Z": None}[axis]
    if rot:
        bmesh.ops.rotate(bm, verts=bm.verts, matrix=Matrix.Rotation(rot[1], 4, rot[0]))
    bmesh.ops.translate(bm, verts=bm.verts, vec=Vector(center))
    return mesh_obj(name, bm, material, parent, smooth=True)

def box(name, size_px, material, parent=None, loc=(0, 0, 0)):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1)
    bmesh.ops.scale(bm, vec=(size_px[0] * PX, size_px[1] * PX, size_px[2] * PX), verts=bm.verts)
    o = mesh_obj(name, bm, material, parent); o.location = loc
    return o

def prism(name, outline_xz, y0_px, y1_px, material, parent=None):
    """Extrude a 2D outline (Blender x,z in metres) between depths y0..y1 (px); triangulated for Unity."""
    bm = bmesh.new()
    a = [bm.verts.new((x, y0_px * PX, z)) for x, z in outline_xz]
    b = [bm.verts.new((x, y1_px * PX, z)) for x, z in outline_xz]
    bm.faces.new(a[::-1]); bm.faces.new(b)
    n = len(outline_xz)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((a[i], a[j], b[j], b[i]))
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return mesh_obj(name, bm, material, parent)

# ---------- gear geometry ----------
MOD = 1.5  # module in px: pitch radius = MOD * teeth / 2

def gear_profile(n, mod):
    """Spur gear outline: n trapezoid teeth, pitch radius mod*n/2. Tooth 0 centred on +X."""
    rp = mod * n / 2
    ra, rd = rp + mod, rp - 1.25 * mod
    pts, step = [], 2 * math.pi / n
    for i in range(n):
        a = i * step
        for da, r in ((-0.30, rd), (-0.17, ra), (0.17, ra), (0.30, rd)):
            pts.append((r * math.cos(a + da * step), r * math.sin(a + da * step)))
    return pts

def spur(name, n, thick_px, material, parent, y_off_px=0.0):
    """Gear in the XZ plane (axle along Y), centred on the parent empty."""
    bm = bmesh.new()
    pts = gear_profile(n, MOD)
    t, y0 = thick_px * PX, y_off_px * PX
    top = [bm.verts.new((x * PX, y0 - t / 2, z * PX)) for x, z in pts]
    bot = [bm.verts.new((x * PX, y0 + t / 2, z * PX)) for x, z in pts]
    bm.faces.new(top[::-1]); bm.faces.new(bot)
    for i in range(len(pts)):
        j = (i + 1) % len(pts)
        bm.faces.new((top[i], top[j], bot[j], bot[i]))
    bmesh.ops.triangulate(bm, faces=bm.faces[:2])
    return mesh_obj(name, bm, material, parent)

def crown(name, n, y_px, material, parent):
    """Face gear on the parent's axle at depth y, teeth pointing toward the room (-y)."""
    r = MOD * n / 2
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=40, radius1=(r + 1) * PX, radius2=(r + 1) * PX, depth=2 * PX)
    bmesh.ops.rotate(bm, verts=bm.verts, matrix=Matrix.Rotation(math.pi / 2, 4, "X"))
    bmesh.ops.translate(bm, verts=bm.verts, vec=Vector((0, y_px * PX, 0)))
    for k in range(n):
        a = 2 * math.pi * k / n
        c = Vector((math.cos(a) * (r - 1.5) * PX, (y_px - 2.2) * PX, math.sin(a) * (r - 1.5) * PX))
        t = bmesh.ops.create_cube(bm, size=1)
        sc = Matrix.Diagonal((3.2 * PX, 2.4 * PX, 1.6 * PX, 1))
        bmesh.ops.transform(bm, verts=t["verts"], matrix=Matrix.Rotation(-a, 4, "Y") @ sc)
        bmesh.ops.translate(bm, verts=t["verts"], vec=c)
    return mesh_obj(name, bm, material, parent)

def bevel_pinion(name, n, material, parent):
    """Small cone gear on a vertical (Z) shaft, wide end up, like the real bevel pinions."""
    bm = bmesh.new()
    pts = gear_profile(n, MOD)
    lo = [bm.verts.new((x * PX * 0.7, z * PX * 0.7, -4 * PX)) for x, z in pts]
    hi = [bm.verts.new((x * PX, z * PX, 0)) for x, z in pts]
    bm.faces.new(lo[::-1]); bm.faces.new(hi)
    for i in range(len(pts)):
        j = (i + 1) % len(pts)
        bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
    bmesh.ops.triangulate(bm, faces=bm.faces[:2])
    return mesh_obj(name, bm, material, parent)

# ---------- gear train ----------
# From the photos: the coil kicks the brass magnet wheel; red -> orange, then orange splits:
#   orange -> yellow -> big green (right output)      orange -> lime -> blue (left output, in the lower-left lobe)
# Each output has a crown gear on its axle (teal on green, purple on blue) turning a bevel pinion (purple on the
# right, coral on the left) on a vertical shaft that carries a crystal. Tooth counts are chosen so every shaft makes
# whole turns per loop; the real counts are unknown.
GEARS = [  # name, driver, big teeth, pinion teeth, colour, photo position (model px)
    ("magnet_wheel", None,          None, 8,    "brass",  (-35, 1)),
    ("gear_red",     "magnet_wheel", 24,  10,   "red",    (-58, 27)),
    ("gear_orange",  "gear_red",     30,  10,   "orange", (-32, 43)),
    ("gear_yellow",  "gear_orange",  30,  10,   "yellow", (1, 32)),
    ("gear_green",   "gear_yellow",  40,  None, "green",  (40, 53)),
    ("gear_lime",    "gear_orange",  20,  10,   "lime",   (-30, 72)),   # straight under orange, clear of yellow
    ("gear_blue",    "gear_lime",    30,  None, "blue",   (-48, 110)),
]
G = {g[0]: dict(zip(("name", "driver", "big", "pin", "colour", "hint"), g)) for g in GEARS}
OUTPUTS = [  # side, gear, crown teeth/colour, bevel teeth/colour, crystal centre y (px), crystal radius (px)
    ("right", "gear_green", 20, "teal",   8, "purple", 280, 52),
    ("left",  "gear_blue",  20, "purple", 8, "coral",  377, 58),
]
LAYER = 6.0          # px between gear layers along the axle; layer 0 is deepest (toward the glass)
def layer_y(layer):
    return 10 - layer * LAYER

# layers: a gear's big wheel sits on its driver's pinion layer, its pinion one layer nearer the room
for g in GEARS:
    d = G[g[0]]
    d["layer_big"] = G[d["driver"]]["layer_pin"] if d["driver"] else None
    d["layer_pin"] = (d["layer_big"] + 1) if d["layer_big"] is not None else 0

# positions: each driven gear sits exactly pitch-radius apart from its driver, in the photo's direction
for g in GEARS:
    d = G[g[0]]
    if not d["driver"]:
        d["pos"] = Vector(d["hint"])
        continue
    dr = G[d["driver"]]
    dist = MOD * dr["pin"] / 2 + MOD * d["big"] / 2
    d["pos"] = dr["pos"] + (Vector(d["hint"]) - Vector(dr["hint"])).normalized() * dist

def outer_r(d, which):
    n = d["big"] if which == "big" else d["pin"]
    return MOD * n / 2 + MOD

# check: wheels on one layer that don't mesh must not overlap
meshes = {(G[n]["driver"], n) for n in G if G[n]["driver"]}
wheels = [(d["name"], w, d["layer_big"] if w == "big" else d["layer_pin"]) for d in G.values()
          for w in ("big", "pin") if (d["big"] if w == "big" else d["pin"])]
for i, (a, wa, la) in enumerate(wheels):
    for b, wb, lb in wheels[i + 1:]:
        if la != lb or a == b or (a, b) in meshes or (b, a) in meshes:
            continue
        gap = (G[a]["pos"] - G[b]["pos"]).length - outer_r(G[a], wa) - outer_r(G[b], wb)
        if gap < 0.5:
            print("GEAR CLASH: %s %s and %s %s on layer %d (gap %.1f px)" % (a, wa, b, wb, la, gap))

# turns per loop, from the magnet wheel down (meshing gears counter-rotate)
G["magnet_wheel"]["turns"] = 216.0
for g in GEARS[1:]:
    d, dr = G[g[0]], G[g[1]]
    d["turns"] = -dr["turns"] * dr["pin"] / d["big"]
for side, gear, ct, _, bt, _, _, _ in OUTPUTS:
    G[gear]["crystal_turns"] = abs(G[gear]["turns"]) * ct / bt

# tooth phase so teeth interlock: the driven wheel gets a half-tooth offset at the contact line
G["magnet_wheel"]["phase"] = 0.0
for g in GEARS[1:]:
    d, dr = G[g[0]], G[g[1]]
    v = d["pos"] - dr["pos"]
    theta = math.atan2(-v.y, v.x)               # photo y is down; Blender z is up
    na, nb = dr["pin"], d["big"]
    da = dr["phase"] - theta
    db = -(na / nb) * da + math.pi / nb
    d["phase"] = theta + math.pi + db

root = empty("rainbow_maker")
housing = empty("housing", parent=root)

shafts = {}
for g in GEARS:
    d = G[g[0]]
    s = empty(d["name"], loc=P(*d["pos"]), parent=housing)
    s.rotation_mode = "XYZ"
    shafts[d["name"]] = s
    if d["big"]:
        spur(d["name"] + "_teeth", d["big"], 3.0, M[d["colour"]], s, y_off_px=layer_y(d["layer_big"]))
    else:   # brass magnet wheel: a disc with two magnets the coil kicks, behind its pinion
        cylinder("magnet_wheel_disc", 17, 3, M["brass"], s, center=(0, 16 * PX, 0), segs=32)
        for k in (0, 1):
            cylinder("magnet_%d" % k, 3.5, 4, M["black"], s, segs=12,
                     center=(math.cos(k * math.pi) * 11 * PX, 16 * PX, math.sin(k * math.pi) * 11 * PX))
    if d["pin"]:
        spur(d["name"] + "_pinion", d["pin"], 3.0, M[d["colour"]], s, y_off_px=layer_y(d["layer_pin"]))
    cylinder(d["name"] + "_axle", 1.2, 44, M["steel"], s, segs=10, center=(0, 8 * PX, 0))

# ---------- outputs: crown -> bevel pinion -> shaft -> sleeve -> hook -> crystal ----------
CROWN_Y = -20                       # crown sits in the U-cap in front of the case; teeth face the room
crystal_shafts = {}
for side, gear, ct, ccol, bt, bcol, cy, cr in OUTPUTS:
    g = G[gear]
    s = shafts[gear]
    cylinder(gear + "_crown_axle", 1.4, 14, M["steel"], s, segs=10, center=(0, -15 * PX, 0))
    crown("crown_" + side, ct, CROWN_Y, M[ccol], s)
    crown_r = MOD * ct / 2
    bevel_r = MOD * bt / 2
    top = g["pos"] + Vector((0, crown_r - 1.5))          # pinion top touches the crown's lowest teeth
    depth = CROWN_Y - 2.2 - bevel_r
    cs = empty("crystal_shaft_" + side, loc=P(top.x, top.y, depth), parent=housing)
    cs.rotation_mode = "XYZ"
    crystal_shafts[side] = (cs, g["crystal_turns"])
    bevel_pinion("bevel_" + side, bt, M[bcol], cs)
    hang = cy - cr - top.y                                # px from pinion to crystal top
    rod = hang - 34
    cylinder("crystal_rod_" + side, 2.2, rod, M["steel"], cs, axis="Z", segs=12, center=(0, 0, -rod / 2 * PX))
    # S-hook: an elongated wire loop between the rod end and the crystal
    hc = bpy.data.curves.new("hook_" + side, "CURVE"); hc.dimensions = "3D"
    sp = hc.splines.new("POLY"); sp.points.add(23); sp.use_cyclic_u = True
    for k in range(24):
        a = 2 * math.pi * k / 24
        sp.points[k].co = (4 * PX * math.cos(a), 0, (-rod - 17 + 15 * math.sin(a)) * PX, 1)
    hc.bevel_depth = 0.8 * PX
    hook = link(bpy.data.objects.new("hook_" + side, hc), cs)
    hook.data.materials.append(M["steel"])
    # faceted octagon, flat top, eight-point star on both faces
    R, T = cr * PX, cr * 0.3 * PX
    bm = bmesh.new()
    outer_f = [bm.verts.new((R * math.cos(a), -T * 0.18, R * math.sin(a))) for a in [math.radians(22.5 + 45 * k) for k in range(8)]]
    outer_b = [bm.verts.new((v.co.x, T * 0.18, v.co.z)) for v in outer_f]
    inner_f = [bm.verts.new((0.55 * R * math.cos(a), -T * 0.42, 0.55 * R * math.sin(a))) for a in [math.radians(45 * k) for k in range(8)]]
    inner_b = [bm.verts.new((v.co.x, T * 0.42, v.co.z)) for v in inner_f]
    cf, cb = bm.verts.new((0, -T * 0.5, 0)), bm.verts.new((0, T * 0.5, 0))
    for k in range(8):
        j = (k + 1) % 8
        # outer_f[k] sits between inner_f[k] and inner_f[k+1]
        bm.faces.new((cf, inner_f[j], inner_f[k]))
        bm.faces.new((inner_f[k], inner_f[j], outer_f[k]))
        bm.faces.new((outer_f[(k - 1) % 8], inner_f[k], outer_f[k]))
        bm.faces.new((cb, inner_b[k], inner_b[j]))
        bm.faces.new((inner_b[j], inner_b[k], outer_b[k]))
        bm.faces.new((inner_b[k], outer_b[(k - 1) % 8], outer_b[k]))
        bm.faces.new((outer_f[k], outer_f[j], outer_b[j], outer_b[k]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    cry = mesh_obj("crystal_" + side, bm, M["crystal"], cs)
    cry.location = (0, 0, -(hang + cr * math.cos(math.radians(22.5))) * PX)

# ---------- housing: peanut-shaped clear case ----------
CIRCLES = [((0, 0), 100), ((-48, 112), 47), ((62, 62), 30)]   # main disc, lower-left lobe, right bump
def inside(px, py):
    return any((px - cx) ** 2 + (py - cy) ** 2 <= r * r for (cx, cy), r in CIRCLES)
c0 = (-5, 25)
outline = []
for k in range(220):
    a = 2 * math.pi * k / 220
    r = 1.0
    while inside(c0[0] + r * math.cos(a), c0[1] + r * math.sin(a)) and r < 400:
        r += 0.5
    x, y = c0[0] + r * math.cos(a), c0[1] + r * math.sin(a)
    outline.append((x * PX, -y * PX))
outline.reverse()
prism("housing_case", outline, -14, 30, M["clear"], housing)
# black coil frame and the arm down to the magnet wheel
coil = empty("coil", loc=P(-9, -40, 8), parent=housing)
coil.rotation_euler = (0, math.radians(5), 0)
cylinder("coil_core", 20, 96, M["black"], coil, axis="X", segs=20)
cu = bpy.data.curves.new("coil_wire", "CURVE"); cu.dimensions = "3D"
sp = cu.splines.new("POLY")
TURNS, PERT = 60, 24
sp.points.add(TURNS * PERT - 1)
for k in range(TURNS * PERT):
    a = 2 * math.pi * k / PERT
    sp.points[k].co = ((-46 + 92 * k / (TURNS * PERT)) * PX, 21.5 * PX * math.cos(a), 21.5 * PX * math.sin(a), 1)
cu.bevel_depth = 1.2 * PX; cu.bevel_resolution = 1
wire = link(bpy.data.objects.new("coil_wire", cu), coil)
wire.data.materials.append(M["copper"])
for end in (-1, 1):
    box("coil_frame_end", (6, 40, 54), M["black"], coil, loc=(end * 52 * PX, 0, 0))
box("coil_frame_bottom", (112, 30, 6), M["black"], coil, loc=(0, 0, -27 * PX))
box("coil_frame_top", (112, 30, 4), M["steel"], coil, loc=(0, 0, 27 * PX))
box("coil_arm", (14, 6, 40), M["black"], housing, loc=P(-28, -10, 20))
box("circuit_chip", (14, 6, 8), M["black"], housing, loc=P(-40, -72, 8))
# screw posts through the case, black socket heads on the room side
for sx, sy in ((-3, -83), (55, -53), (-74, -40), (79, 35), (-70, 56), (9, 90), (-85, 125)):
    cylinder("screw_post", 4, 44, M["clear"], housing, center=P(sx, sy, 8), segs=12)
    cylinder("screw_head", 5, 3, M["screw"], housing, center=P(sx, sy, -15.5), segs=16)
# suction cup on the back of the main disc
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, segments=32, radius1=34 * PX, radius2=10 * PX, depth=12 * PX)
bmesh.ops.rotate(bm, verts=bm.verts, matrix=Matrix.Rotation(math.pi / 2, 4, "X"))
cup = mesh_obj("suction_cup", bm, M["clear"], housing, smooth=True); cup.location = P(0, 0, 36)
# U-shaped clear caps in front of each crown, and the sleeves the shafts run down
SLEEVES = {   # side: list of (top y, bottom y, top r, bottom r) sections, collar (top y, height, r)
    "right": ([(93, 125, 23, 12), (125, 140, 12, 12)], (140, 18, 23)),
    "left":  ([(135, 255, 23, 16)], (255, 20, 23)),
}
for side, gear, ct, _, _, _, _, _ in OUTPUTS:
    gx, gy = G[gear]["pos"]
    sections, (coly, colh, colr) = SLEEVES[side]
    cap_top, cap_bot, w = gy - 24, sections[0][0], 26
    u = [(gx + w * math.cos(a), cap_top + w - w * math.sin(a)) for a in [math.pi * k / 16 for k in range(17)]]
    u += [(gx - w, cap_bot), (gx + w, cap_bot)]
    prism("u_cap_" + side, [(x * PX, -y * PX) for x, y in reversed(u)], -40, -14, M["clear"], housing)
    sx = G[gear]["pos"].x
    sdepth = CROWN_Y - 2.2 - MOD * 8 / 2
    for i, (t, b, rt, rb) in enumerate(sections):
        o = cylinder("sleeve_%s_%d" % (side, i), rb, b - t, M["clear"], housing, axis="Z", r2_px=rt, segs=32)
        o.location = P(sx, (t + b) / 2, sdepth)
    o = cylinder("collar_" + side, colr, colh, M["clear"], housing, axis="Z", segs=32)
    o.location = P(sx, coly + colh / 2, sdepth)
# hinged solar panel on top, tilted 20 degrees so the cells face up through the glass
hinge = empty("solar_panel", loc=P(1, -88, 8), parent=housing)
hinge.rotation_euler = (math.radians(20), 0, 0)
box("panel_frame", (159, 24, 110), M["clear"], hinge, loc=(0, 0, 55 * PX))
box("panel_back", (146, 2, 96), M["panelbk"], hinge, loc=(0, -9 * PX, 55 * PX))
box("panel_cells", (146, 2, 96), M["panel"], hinge, loc=(0, 9 * PX, 55 * PX))
for k in range(1, 3):
    box("cell_band", (146, 1, 2), M["black"], hinge, loc=(0, -10.2 * PX, (55 - 48 + k * 32) * PX))
for hx in (-52, 51):
    box("hinge_clip", (22, 14, 18), M["black"], hinge, loc=(hx * PX, -6 * PX, 8 * PX))
box("neck", (80, 30, 22), M["clear"], housing, loc=P(1, -95, 8))

# ---------- animation: linear, seamless loop ----------
def spin(obj, axis_idx, turns_, base=0.0):
    obj.rotation_euler[axis_idx] = base
    obj.keyframe_insert("rotation_euler", index=axis_idx, frame=1)
    obj.rotation_euler[axis_idx] = base + turns_ * 2 * math.pi
    obj.keyframe_insert("rotation_euler", index=axis_idx, frame=FRAMES + 1)

# Blender's Y rotation is clockwise seen from the room, so the sign flips relative to the photo view.
for name, s in shafts.items():
    spin(s, 1, -G[name]["turns"], base=-G[name]["phase"])
for side, (cs, turns) in crystal_shafts.items():
    spin(cs, 2, turns)
for ob in bpy.data.objects:
    ad = ob.animation_data
    if ad and ad.action:
        curves = []
        try:
            curves = list(ad.action.fcurves)
        except Exception:
            pass
        if not curves and hasattr(ad.action, "layers"):
            for L in ad.action.layers:
                for st in L.strips:
                    for cb in st.channelbags:
                        curves += list(cb.fcurves)
        for fc in curves:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"

print("TURNS PER LOOP (%d s):" % LOOP_S, {n: round(G[n]["turns"], 3) for n in G},
      {side: t for side, (_, t) in crystal_shafts.items()})

# ---------- camera + light for previews ----------
cam = bpy.data.objects.new("preview_camera", bpy.data.cameras.new("preview_camera"))
col.objects.link(cam)
cam.data.lens = 85
look = Vector((0, 0, -0.032))
cam.location = (0.07, -0.47, -0.032)
if "closeup" in argv:
    cam.data.lens, cam.location, look = 150, (0.0, -0.40, -0.012), Vector((0, 0, -0.012))
if "angle" in argv:   # like Astra's photo from below-left of the window
    cam.data.lens, cam.location, look = 70, (-0.2, -0.32, -0.12), Vector((0, 0, -0.03))
cam.rotation_euler = (look - Vector(cam.location)).to_track_quat("-Z", "Y").to_euler()
scn.camera = cam
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 2.0
sun.rotation_euler = (math.radians(60), math.radians(-20), math.radians(-30))
col.objects.link(sun)
key = bpy.data.objects.new("key_light", bpy.data.lights.new("key_light", "AREA"))
key.data.energy, key.data.size = 6, 0.3
key.location = (-0.15, -0.3, 0.1)
key.rotation_euler = (math.radians(70), 0, math.radians(-25))
col.objects.link(key)
scn.view_settings.view_transform = "Standard"
scn.view_settings.exposure = -1.3
world = bpy.data.worlds.new("bg"); scn.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.15, 0.15, 0.17, 1)  # graphite gray

# Curves (coil wire, hooks) become real meshes so Unity gets them.
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
    o.select_set(o.type in {"MESH", "EMPTY"})
bpy.ops.export_scene.fbx(filepath=fbx, use_selection=True, object_types={"EMPTY", "MESH"},
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
    scn.frame_start, scn.frame_end = 1, 180
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
