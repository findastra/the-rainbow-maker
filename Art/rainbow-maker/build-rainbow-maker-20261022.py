# Builds Astra's double-crystal Kikkerland solar Rainbow Maker in Blender with a real, meshing gear train,
# bakes a seamless loop and exports FBX for Unity.
# Run: blender --background --python build-rainbow-maker-20261022.py -- <out_dir> [still N] [closeup|angle] [render]
# Layout comes from Astra's own photos (2026-10-23), measured in "model px": 1 px = 0.264 mm, origin = centre of the
# main disc, x to the right and y DOWN as seen from the room.
import bpy, bmesh, math, sys, os
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(argv[0]) if argv else os.path.dirname(os.path.abspath(__file__))
DO_RENDER = "render" in argv
STAMP = "20261022"   # file names stay the same so Unity keeps the FBX's GUID

PX = 0.000264
FPS = 30
LOOP_S = 120                    # seamless loop length; Astra's real one turns about this slowly (2026-10-23)
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
    "crystal": mat("rm_crystal", (1.0, 1.0, 1.0), rough=0.0),
}
# Cut crystal: full transmission, lead-crystal IOR, and dispersion so it splits light into colours (Cycles shows
# the dispersion; EEVEE refracts with raytracing). Unity uses its own crystal shader instead.
_b = M["crystal"].node_tree.nodes["Principled BSDF"]
_b.inputs["Transmission Weight"].default_value = 1.0
_b.inputs["IOR"].default_value = 1.55
if "Dispersion" in _b.inputs:
    _b.inputs["Dispersion"].default_value = 0.6
for attr, val in (("use_raytrace_refraction", True), ("use_screen_refraction", True)):
    if hasattr(M["crystal"], attr):
        setattr(M["crystal"], attr, val)

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
    """Extrude a 2D outline (Blender x,z in metres) between depths y0..y1 (px)."""
    bm = bmesh.new()
    a = [bm.verts.new((x, y0_px * PX, z)) for x, z in outline_xz]
    b = [bm.verts.new((x, y1_px * PX, z)) for x, z in outline_xz]
    bm.faces.new(a[::-1]); bm.faces.new(b)
    n = len(outline_xz)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((a[i], a[j], b[j], b[i]))
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
    # Dielectric refraction needs an outward closed surface. Inverted faces used to cause
    # black diagonal artifacts that were mistaken for cut-glass facets.
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
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
    return mesh_obj(name, bm, material, parent)

# ---------- crystals ----------
# Astra's crystals (photos 2026-10-23): flat-topped octagons ~31 mm across and ~10 mm thick. Each face has an
# eight-point star (16 facets meeting at a low point in the middle), then a ring of 24 bevel facets out to a thin
# girdle, and a hole near the top for the hook.
def crystal_hole_drop(r_px):
    """px from the crystal's centre up to its hole."""
    return r_px * math.cos(math.radians(22.5)) - 7

def make_crystal(name, r_px, parent):
    R = r_px * PX
    # A steep star pyramid in the middle (about 22 degrees) and a flatter ring of bevels out to the rim, as in
    # Astra's photos: the steep facets bounce light around inside, which gives the patchwork and the fire.
    girdle = 0.05 * R          # half thickness of the rim
    ring_depth = 0.12 * R      # where the bevels meet the star
    apex = 0.36 * R            # centre of each face (total thickness 0.72 R, about 11 mm)
    ring_r = 0.6
    corner = [math.radians(22.5 + 45 * k) for k in range(8)]   # flat top edge between corners 1 and 2
    mid = [math.radians(45 + 45 * k) for k in range(8)]
    bm = bmesh.new()
    def face(sign):
        o = [bm.verts.new((R * math.cos(a), sign * girdle, R * math.sin(a))) for a in corner]
        c = [bm.verts.new((ring_r * R * math.cos(a), sign * ring_depth, ring_r * R * math.sin(a))) for a in corner]
        e = [bm.verts.new((ring_r * R * math.cos(math.radians(22.5)) * math.cos(a), sign * ring_depth,
                           ring_r * R * math.cos(math.radians(22.5)) * math.sin(a))) for a in mid]
        tip = bm.verts.new((0, sign * apex, 0))
        for k in range(8):
            j = (k + 1) % 8
            for f in ((tip, c[k], e[k]), (tip, e[k], c[j]),                        # star
                      (c[k], o[k], e[k]), (e[k], o[k], o[j]), (e[k], o[j], c[j])):  # bevels
                bm.faces.new(f if sign < 0 else f[::-1])
        return o
    front, back = face(-1), face(1)
    for k in range(8):
        j = (k + 1) % 8
        bm.faces.new((front[k], front[j], back[j], back[k]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    obj = mesh_obj(name, bm, M["crystal"], parent)
    # the drilled hole: a short clear tube through the crystal near its top edge
    cylinder(name + "_hole", 2.6, r_px * 0.66, M["clear"], obj, center=(0, 0, crystal_hole_drop(r_px) * PX), segs=12)
    return obj

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
    # The crystal hangs from the hook through a hole just under its flat top edge.
    hole_z = -(rod + 30)                                   # px, the hook's lower bend
    cry = make_crystal("crystal_" + side, cr, cs)
    cry.location = (0, 0, (hole_z - crystal_hole_drop(cr)) * PX)

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
if "crystals" in argv:   # the two crystals up close
    cam.data.lens, cam.location, look = 100, (0.02, -0.30, -0.085), Vector((0, 0, -0.085))
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
if "crystals" in argv:   # overcast sky over a dark city, like Astra's window photos; the glass bends both
    nt = world.node_tree
    tc, sep = nt.nodes.new("ShaderNodeTexCoord"), nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = -1, 1
    nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], ramp.inputs["Fac"])
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (0.03, 0.03, 0.03, 1)
    els[1].position, els[1].color = 0.47, (0.12, 0.1, 0.09, 1)
    for pos, c in ((0.5, (0.55, 0.57, 0.6, 1)), (1.0, (0.85, 0.87, 0.9, 1))):
        e = els.new(pos); e.color = c
    nt.links.new(ramp.outputs["Color"], nt.nodes["Background"].inputs[0])
    nt.nodes["Background"].inputs[1].default_value = 1.4
# neon strips behind the camera give the glass something bright to bend and split
for k, (rgb, x) in enumerate((((1, 0.1, 0.65), -0.12), ((0.2, 0.9, 1), 0.0), ((1, 0.9, 0.3), 0.12))):
    strip = bpy.data.objects.new("neon_strip_%d" % k, bpy.data.lights.new("neon_strip_%d" % k, "AREA"))
    strip.data.shape, strip.data.size, strip.data.size_y = "RECTANGLE", 0.02, 0.4
    strip.data.color, strip.data.energy = rgb, 8
    strip.location = (x, -0.35, -0.05)
    strip.rotation_euler = (math.radians(90), 0, 0)
    col.objects.link(strip)

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

# ---------- photographic details; final exporter keeps only the model subtree ----------
REAL = "real" in argv or "studio" in argv
REAL_STAMP = "20261023"
if REAL:
    import random
    rnd = random.Random(7)

    def bsdf(m):
        return m.node_tree.nodes["Principled BSDF"]

    def setv(m, **vals):
        b = bsdf(m)
        for k, v in vals.items():
            name = k.replace("_", " ")
            if name in b.inputs:
                b.inputs[name].default_value = v

    def add_bump(m, node, out, strength, distance=0.0005):
        nt = m.node_tree
        bp = nt.nodes.new("ShaderNodeBump")
        bp.inputs["Strength"].default_value = strength
        bp.inputs["Distance"].default_value = distance
        nt.links.new(node.outputs[out], bp.inputs["Height"])
        nt.links.new(bp.outputs["Normal"], bsdf(m).inputs["Normal"])

    def noise_bump(m, scale, strength):
        # object coordinates (metres): the default box-fitted coordinates stretch noise on a 1 mm gear into streaks
        nt = m.node_tree
        tc, n = nt.nodes.new("ShaderNodeTexCoord"), nt.nodes.new("ShaderNodeTexNoise")
        nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
        n.inputs["Scale"].default_value = scale
        add_bump(m, n, "Fac", strength)

    # The case, caps, neck and panel frame are thin hollow acrylic shells: shiny and see-through without bending
    # what's inside (the model's solid blocks would refract like lumps of glass). The sleeves and collars are solid
    # clear plastic, so they get real refraction.
    solid_acrylic = mat("rm_solid_acrylic", (0.98, 0.99, 1.0), rough=0.02)
    setv(solid_acrylic, Transmission_Weight=1.0, IOR=1.49)
    for o in bpy.data.objects:
        if o.type == "MESH" and o.name.startswith(("sleeve_", "collar_", "screw_post")):
            o.data.materials[0] = solid_acrylic
    setv(M["clear"], Roughness=0.02, Coat_Weight=1.0, Base_Color=(0.98, 0.99, 1, 1))
    nt = M["clear"].node_tree
    # a clear shell shows where you see it edge-on (rims, curves), almost nothing where you look straight through
    lw, edge = nt.nodes.new("ShaderNodeLayerWeight"), nt.nodes.new("ShaderNodeMapRange")
    lw.inputs["Blend"].default_value = 0.3
    edge.inputs["To Min"].default_value, edge.inputs["To Max"].default_value = 0.03, 0.7
    nt.links.new(lw.outputs["Facing"], edge.inputs["Value"])
    # only the camera sees the rims: to light they stay see-through, or they cast dark lines across the gears
    lp, only_cam = nt.nodes.new("ShaderNodeLightPath"), nt.nodes.new("ShaderNodeMix")
    only_cam.data_type = "FLOAT"
    only_cam.inputs["A"].default_value = 0.02
    nt.links.new(lp.outputs["Is Camera Ray"], only_cam.inputs["Factor"])
    nt.links.new(edge.outputs["Result"], only_cam.inputs["B"])
    nt.links.new(only_cam.outputs["Result"], bsdf(M["clear"]).inputs["Alpha"])
    # round moulded dimples (the circles all over the case in Astra's photos)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 160
    nt.links.new(tc.outputs["Object"], vor.inputs["Vector"])
    ring = nt.nodes.new("ShaderNodeMapRange")
    ring.inputs["From Min"].default_value, ring.inputs["From Max"].default_value = 0.22, 0.3
    ring.inputs["To Min"].default_value, ring.inputs["To Max"].default_value = 1, 0
    nt.links.new(vor.outputs["Distance"], ring.inputs["Value"])
    add_bump(M["clear"], ring, "Result", 0.05, 0.0001)   # faint: strong dimples mirror the street as dark arcs
    # gears: glossy translucent moulded plastic that glows when the window lights it from behind
    for k in ("red", "orange", "yellow", "lime", "green", "blue", "teal", "purple", "coral"):
        if "plaingears" not in argv:   # glassy gears that bend the light through their facets (Astra's pick)
            setv(M[k], Transmission_Weight=0.6, Roughness=0.15, IOR=1.46, Coat_Weight=0.3)
            continue
        # a little light glows through the plastic (subsurface) rather than refracting through 1 mm of gear
        setv(M[k], Subsurface_Weight=0.2, Subsurface_Scale=0.002, Roughness=0.15, IOR=1.46, Coat_Weight=0.3)
        bsdf(M[k]).inputs["Subsurface Radius"].default_value = (1.0, 1.0, 1.0)
        noise_bump(M[k], 2500, 0.04)
    setv(M["copper"], Roughness=0.25, Base_Color=(0.72, 0.33, 0.17, 1))

    # The spool, as on Astra's unit: hundreds of turns of fine enamelled copper. The model's single thick helix
    # reads as a spring up close, so the render replaces it with real strands: two layers of 0.2 mm wire, each
    # turn its own loop, wavering a little like hand-guided winding, under glossy enamel.
    bpy.data.objects["coil_wire"].hide_render = True
    COIL_L = 92
    WIRE_R, PITCH = 0.36, 0.76                                    # px: 0.095 mm radius, 0.2 mm between turns
    wire_mat = mat("rm_enamel_wire", (0.6, 0.22, 0.08), metal=1.0, rough=0.2)
    setv(wire_mat, Coat_Weight=0.8, Coat_Roughness=0.05, Coat_Tint=(1.0, 0.75, 0.55, 1))   # the enamel
    wob = random.Random(3)
    for layer, (radius, phase) in enumerate(((20.3, 0.0), (21.1, 0.5))):
        turns_n = int(COIL_L / PITCH) - 2
        per_turn = 24
        cu = bpy.data.curves.new("coil_strands_%d" % layer, "CURVE"); cu.dimensions = "3D"
        sp = cu.splines.new("POLY")
        sp.points.add(turns_n * per_turn - 1)
        x0 = -COIL_L / 2 + 1 + phase * PITCH
        for k in range(turns_n * per_turn):
            a = 2 * math.pi * k / per_turn
            x = x0 + PITCH * k / per_turn + wob.uniform(-0.03, 0.03)
            r = radius + wob.uniform(-0.04, 0.04)
            sp.points[k].co = (x * PX, r * PX * math.cos(a), r * PX * math.sin(a), 1)
        cu.bevel_depth = WIRE_R * PX
        cu.bevel_resolution = 3
        strands = link(bpy.data.objects.new("coil_strands_%d" % layer, cu), bpy.data.objects["coil"])
        strands.data.materials.append(wire_mat)
    # the wire's two tails run off the end of the spool
    for k, (xe, ze) in enumerate(((-46, 24), (46, 24))):
        cu = bpy.data.curves.new("coil_tail_%d" % k, "CURVE"); cu.dimensions = "3D"
        sp = cu.splines.new("NURBS"); sp.points.add(3)
        for i, pt in enumerate(((xe, 0, 21), (xe * 1.05, 6, 26), (xe * 0.9, 14, 29), (xe * 0.6, 18, 30))):
            sp.points[i].co = (pt[0] * PX, pt[1] * PX, pt[2] * PX, 1)
        cu.bevel_depth = WIRE_R * PX
        tail = link(bpy.data.objects.new("coil_tail_%d" % k, cu), bpy.data.objects["coil"])
        tail.data.materials.append(wire_mat)
    setv(M["brass"], Roughness=0.3)
    setv(M["steel"], Roughness=0.12)
    setv(M["black"], Roughness=0.5, Metallic=0.4)
    noise_bump(M["black"], 4000, 0.08)
    setv(M["screw"], Roughness=0.35, Metallic=0.7)
    setv(M["panel"], Base_Color=(0.08, 0.05, 0.045, 1), Roughness=0.06, Coat_Weight=1.0)
    setv(M["panelbk"], Base_Color=(0.06, 0.035, 0.03, 1), Roughness=0.3)

    def solid(name, size, loc, material):
        bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1)
        bmesh.ops.scale(bm, vec=size, verts=bm.verts)
        o = mesh_obj(name, bm, material); o.location = loc
        return o

    def lambert(name, rgb, rough=0.8, emit=None, strength=0.0):
        m = mat(name, rgb, rough=rough)
        if emit:
            setv(m, Emission_Color=(*emit, 1), Emission_Strength=strength)
        return m

    # the window pane the suction cup holds on to, with raindrops on the outside
    pane_y = 42 * PX
    # the pane is pure see-through: a reflecting pane would mirror the sparkle lights as a white haze
    glass = mat("window_glass", (1, 1, 1), rough=0.0)
    gn = glass.node_tree
    clear_pane = gn.nodes.new("ShaderNodeBsdfTransparent")
    gn.links.new(clear_pane.outputs[0], gn.nodes["Material Output"].inputs["Surface"])
    solid("window_pane", (1.2, 0.005, 1.2), (0, pane_y + 0.0025, 0), glass)
    water = mat("rain", (1, 1, 1), rough=0.0)
    setv(water, Transmission_Weight=1.0, IOR=1.33)
    for k in range(110):
        r = rnd.uniform(0.0004, 0.0016)
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=r)
        bmesh.ops.scale(bm, vec=(1, 0.3, 1.2), verts=bm.verts)      # flattened beads, slightly run down
        d = mesh_obj("raindrop", bm, water, smooth=True)
        # rain gathers in loose vertical runs, like on Astra's window
        run = rnd.choice((-0.19, -0.16, -0.11, 0.12, 0.17, 0.2)) if k % 3 else rnd.uniform(-0.22, 0.22)
        d.location = (run + rnd.uniform(-0.006, 0.006), pane_y + 0.005 + r * 0.2, rnd.uniform(-0.2, 0.14))
    # overcast sky over a city: blocks far outside, blurred by the lens like in the photos
    w = scn.world.node_tree
    tcw, sep, mr = w.nodes.new("ShaderNodeTexCoord"), w.nodes.new("ShaderNodeSeparateXYZ"), w.nodes.new("ShaderNodeMapRange")
    ramp = w.nodes.new("ShaderNodeValToRGB")
    w.links.new(tcw.outputs["Generated"], sep.inputs[0])
    mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = -1, 1
    w.links.new(sep.outputs["Z"], mr.inputs["Value"])
    w.links.new(mr.outputs["Result"], ramp.inputs["Fac"])
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (0.05, 0.05, 0.05, 1)
    els[1].position, els[1].color = 0.5, (0.5, 0.52, 0.54, 1)
    e = els.new(0.62); e.color = (0.8, 0.82, 0.84, 1)
    e = els.new(1.0); e.color = (0.86, 0.87, 0.89, 1)
    w.links.new(ramp.outputs["Color"], w.nodes["Background"].inputs[0])
    w.nodes["Background"].inputs[1].default_value = 1.3
    concrete = [lambert("concrete_%d" % k, c, rough=0.5) for k, c in enumerate(
        ((0.18, 0.18, 0.19), (0.12, 0.11, 0.1), (0.25, 0.22, 0.2), (0.09, 0.1, 0.12), (0.22, 0.14, 0.11),
         (0.3, 0.3, 0.31)))]
    roof = lambert("wet_roof", (0.35, 0.35, 0.37), rough=0.2)
    for k in range(60):
        dist = rnd.uniform(10, 90)
        x = rnd.uniform(-60, 60)
        # Astra looks down over rooftops: near buildings stay below eye level, only far ones reach above it
        h = rnd.uniform(6, 22) if dist < 45 else rnd.uniform(10, 36)
        h = min(h, 16 + dist * 0.12)
        wdt, dep = rnd.uniform(6, 26), rnd.uniform(6, 20)
        solid("building", (wdt, dep, h), (x, dist + dep / 2, -18 + h / 2), rnd.choice(concrete))
    solid("rooftop_below", (24, 16, 0.4), (-6, 9, -6.5), roof)
    solid("street", (300, 300, 0.2), (0, 120, -18.2), lambert("asphalt", (0.07, 0.07, 0.075), rough=0.6))
    warm = lambert("street_light", (1, 0.7, 0.4), emit=(1, 0.62, 0.3), strength=40)
    for k in range(18):
        bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=0.25)
        s = mesh_obj("street_light", bm, warm)
        s.location = (rnd.uniform(-35, 35), rnd.uniform(18, 60), rnd.uniform(-16, -11))
    # light: the overcast sky, a little room light from behind the camera, and a low sun breaking through the
    # clouds up to the right. The sun is a glowing disc (not a lamp) so the glass can bend it into flashes.
    for o in bpy.data.objects:
        if o.type == "LIGHT":
            o.hide_render = True
    sun_mat = lambert("sun_disc", (1, 1, 1), emit=(1.0, 0.93, 0.8), strength=15000)
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=3.0)
    sun_disc = mesh_obj("sun_disc", bm, sun_mat)
    SUN_POS = Vector((30, 70, 28))     # up and to the right, outside the window, near enough the line of sight
    sun_disc.location = SUN_POS        # that the facets can bend it into fire
    # Sparkle lights: a flat pendant mostly mirrors what is behind the viewer, so a ring of small bright lights
    # sits there (sunlit room, lamps), the way jewellers light a stone. Each facet catches a different one as the
    # crystal turns, and that is the twinkle.
    spark_mat = lambert("sparkle_light", (1, 1, 1), emit=(1.0, 0.96, 0.9), strength=400)
    for k in range(10):
        a = 2 * math.pi * k / 10
        tilt = math.radians(18 if k % 2 else 34)
        d = Vector((math.sin(tilt) * math.cos(a), -math.cos(tilt), math.sin(tilt) * math.sin(a)))
        bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=0.035)
        s = mesh_obj("sparkle_light_%d" % k, bm, spark_mat)
        s.location = Vector((0, 0, -0.08)) + d * 1.4
        # seen only in reflections and through glass: the lights themselves stay out of the picture and
        # don't wash the window and raindrops (like studio lights behind black cards)
        s.visible_camera = s.visible_diffuse = s.visible_shadow = s.visible_volume_scatter = False
    b_c = bsdf(M["crystal"])
    print("CRYSTAL INPUTS", [(i.name, i.default_value) for i in b_c.inputs if i.name in ("IOR", "Dispersion", "Transmission Weight", "Roughness")])
    # Facets only glitter against contrast, so the sky gets a bright glow around the sun and ragged clouds,
    # bright where they thin and dark where they bank up.
    sky_dir = w.nodes.new("ShaderNodeVectorMath"); sky_dir.operation = "NORMALIZE"
    w.links.new(tcw.outputs["Generated"], sky_dir.inputs[0])
    toward = w.nodes.new("ShaderNodeVectorMath"); toward.operation = "DOT_PRODUCT"
    toward.inputs[1].default_value = SUN_POS.normalized()
    w.links.new(sky_dir.outputs["Vector"], toward.inputs[0])
    halo = w.nodes.new("ShaderNodeMapRange")
    halo.inputs["From Min"].default_value, halo.inputs["From Max"].default_value = 0.75, 1.0
    halo.inputs["To Min"].default_value, halo.inputs["To Max"].default_value = 0.0, 3.0
    w.links.new(toward.outputs["Value"], halo.inputs["Value"])
    clouds = w.nodes.new("ShaderNodeTexNoise")
    clouds.inputs["Scale"].default_value = 2.5
    clouds.inputs["Detail"].default_value = 6
    clouds.inputs["Roughness"].default_value = 0.6
    w.links.new(tcw.outputs["Generated"], clouds.inputs["Vector"])
    cloud_c = w.nodes.new("ShaderNodeMapRange")
    cloud_c.inputs["From Min"].default_value, cloud_c.inputs["From Max"].default_value = 0.35, 0.65
    cloud_c.inputs["To Min"].default_value, cloud_c.inputs["To Max"].default_value = 0.45, 1.3
    w.links.new(clouds.outputs["Fac"], cloud_c.inputs["Value"])
    bright = w.nodes.new("ShaderNodeMath"); bright.operation = "ADD"
    w.links.new(cloud_c.outputs["Result"], bright.inputs[0])
    w.links.new(halo.outputs["Result"], bright.inputs[1])
    # only above the horizon: the city below keeps the plain ramp
    above = w.nodes.new("ShaderNodeMath"); above.operation = "GREATER_THAN"; above.inputs[1].default_value = 0.0
    w.links.new(sep.outputs["Z"], above.inputs[0])
    gain = w.nodes.new("ShaderNodeMath"); gain.operation = "MULTIPLY_ADD"
    w.links.new(above.outputs["Value"], gain.inputs[0])
    w.links.new(bright.outputs["Value"], gain.inputs[1])
    gain.inputs[2].default_value = 1.0
    skycol = w.nodes.new("ShaderNodeMix"); skycol.data_type = "RGBA"; skycol.blend_type = "MULTIPLY"
    skycol.inputs["Factor"].default_value = 1.0
    w.links.new(ramp.outputs["Color"], skycol.inputs[6])
    tint = w.nodes.new("ShaderNodeCombineColor")
    for i in range(3):
        w.links.new(gain.outputs["Value"], tint.inputs[i])
    w.links.new(tint.outputs["Color"], skycol.inputs[7])
    w.links.new(skycol.outputs[2], w.nodes["Background"].inputs[0])
    # Diamond-grade crystal. Blender 4.5's glass has no dispersion control, so the crystal is three glasses added
    # together, red, green and blue, each bending light a little differently: white light fans out into colour
    # at every facet edge, and a facet that catches the sun throws real rainbow fire.
    cn = M["crystal"].node_tree
    out = cn.nodes["Material Output"]
    glasses = []
    for rgb, ior in (((1, 0, 0, 1), 1.70), ((0, 1, 0, 1), 1.75), ((0, 0, 1, 1), 1.82)):
        g = cn.nodes.new("ShaderNodeBsdfGlass")
        g.distribution = "GGX"
        g.inputs["Color"].default_value = rgb
        g.inputs["Roughness"].default_value = 0.0
        g.inputs["IOR"].default_value = ior
        glasses.append(g)
    add1, add2 = cn.nodes.new("ShaderNodeAddShader"), cn.nodes.new("ShaderNodeAddShader")
    cn.links.new(glasses[0].outputs[0], add1.inputs[0])
    cn.links.new(glasses[1].outputs[0], add1.inputs[1])
    cn.links.new(add1.outputs[0], add2.inputs[0])
    cn.links.new(glasses[2].outputs[0], add2.inputs[1])
    cn.links.new(add2.outputs[0], out.inputs["Surface"])
    room = bpy.data.objects.new("room_light", bpy.data.lights.new("room_light", "AREA"))
    room.data.energy, room.data.size, room.data.color = 3, 0.8, (1, 0.95, 0.9)
    room.location = (0.1, -0.6, 0.15)
    room.rotation_euler = (Vector((0, 0, 0)) - room.location).to_track_quat("-Z", "Y").to_euler()
    col.objects.link(room)
    # camera like Astra's close photo: the maker fills the frame, sharp from panel to crystals, the city soft
    cam.data.lens = 66
    cam.location = (0.0, -0.31, -0.04)
    cam.rotation_euler = (Vector((0, 0, -0.03)) - Vector(cam.location)).to_track_quat("-Z", "Y").to_euler()
    cam.data.dof.use_dof = True
    cam.data.dof.focus_distance = 0.31
    cam.data.dof.aperture_fstop = 8.0
    for flag, part in (("zoomgear", "gear_green"), ("zoomcoil", "coil"), ("zoomcrystal", "crystal_right")):
        if flag in argv:   # test views filling the frame
            cam.data.lens = 300 if flag == "zoomgear" else 220
            target = bpy.data.objects[part].matrix_world.translation
            cam.rotation_euler = (target - Vector(cam.location)).to_track_quat("-Z", "Y").to_euler()
            cam.data.dof.focus_distance = (target - Vector(cam.location)).length
            cam.data.dof.aperture_fstop = 16.0
    scn.view_settings.view_transform = "AgX"
    scn.view_settings.look = "AgX - Medium High Contrast" if "AgX - Medium High Contrast" in [
        i.identifier for i in scn.view_settings.bl_rna.properties["look"].enum_items] else "None"
    scn.view_settings.exposure = -0.7
    scn.render.use_motion_blur = "still" not in argv     # only the video; stills stay crisp
    scn.render.motion_blur_shutter = 0.5

if DO_RENDER or "still" in argv:
    eng = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    scn.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in eng else "BLENDER_EEVEE"
    if hasattr(scn.eevee, "use_raytracing"):
        scn.eevee.use_raytracing = True
    if REAL:   # the graphics card renders the photo-real version
        prefs = bpy.context.preferences.addons["cycles"].preferences
        try:
            prefs.compute_device_type = "HIP"
            prefs.get_devices()
            for d in prefs.devices:
                d.use = "RX" in d.name          # the Radeon RX card, not the CPU's built-in graphics
            scn.cycles.device = "GPU"
        except Exception as e:
            print("GPU not available, rendering on the CPU:", e)
    if "cycles" in argv or REAL:   # true glass with dispersion; slower
        scn.render.engine = "CYCLES"
        scn.cycles.samples = 192
        scn.cycles.use_denoising = True
        scn.cycles.max_bounces = scn.cycles.transmission_bounces = scn.cycles.glossy_bounces = 16
    scn.render.resolution_x, scn.render.resolution_y = 540, 960
    if REAL:
        # glitter needs light traced far into the glass and back out, and sparkles left unclamped
        scn.cycles.samples = 128
        scn.cycles.time_limit = 90                     # seconds per frame, whatever the glass does
        scn.cycles.max_bounces = 16
        scn.cycles.transmission_bounces = 16           # enough for in, two or three inner bounces, and out
        scn.cycles.glossy_bounces = 8
        scn.cycles.sample_clamp_indirect = 12          # flashes stay bright, runaway paths don't
        scn.cycles.sample_clamp_direct = 0
        scn.cycles.blur_glossy = 0.0
        scn.cycles.caustics_reflective = scn.cycles.caustics_refractive = True
        scn.cycles.use_denoising = "nodenoise" not in argv
        scn.render.resolution_x, scn.render.resolution_y = 1080, 1440   # the photos' 3:4
    scn.render.film_transparent = False
# Final material/geometry processing is deliberately after the REAL block, before every export.
# The model subtree is exported separately from the photographic/studio environment.
import importlib.util
_spec = importlib.util.spec_from_file_location("stained_glass", os.path.join(os.path.dirname(__file__), "stained-glass-finish-20261030.py"))
_finish = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_finish)
_finish.finish(globals())

for a in argv:   # hide:<name prefix>,... leaves parts out of a test render
    if a.startswith("hide:"):
        for o in bpy.data.objects:
            if o.name.startswith(tuple(a[5:].split(","))):
                o.hide_render = True
name = "real" if REAL else "preview"
stamp = "20261030"
if "still" in argv:
    scn.frame_set(int(argv[argv.index("still") + 1]) if len(argv) > argv.index("still") + 1 else 1)
    scn.render.image_settings.file_format = "PNG"
    scn.render.filepath = os.path.join(OUT, f"rainbow-maker-{'real-' if REAL else ''}check-{stamp}.png")
    bpy.ops.render.render(write_still=True)
if DO_RENDER:
    scn.frame_start, scn.frame_end = 1, (240 if REAL else 180)
    scn.render.image_settings.file_format = "FFMPEG"
    scn.render.ffmpeg.format = "MPEG4"
    scn.render.ffmpeg.codec = "H264"
    scn.render.ffmpeg.constant_rate_factor = "HIGH"
    scn.render.filepath = os.path.join(OUT, f"rainbow-maker-{name}-{stamp}.mp4")
    bpy.ops.render.render(animation=True)
    scn.render.image_settings.file_format = "PNG"
    scn.frame_set(1)
    scn.render.filepath = os.path.join(OUT, f"rainbow-maker-{'real' if REAL else 'still'}-{stamp}.png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED")
