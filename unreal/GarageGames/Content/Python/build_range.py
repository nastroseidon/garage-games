"""Builds the Garage Games range level (Content/Maps/Range) from code.

The layout (all seven targets from the repo's games.py, mown stripes,
yardage boards, light towers, a tree line and hills) comes from
range_layout.py. If free Fab / Quixel trees, rocks or grass are on this PC
(Content/Fab or Content/Megascans), they replace the simple shapes; see
unreal/README.md. Lighting starts as night; switch with
garage_env.set_time_of_day("day").

Safe to run again: it replaces everything it made before (actors named
GG_...).

Run it in the editor: Tools > Execute Python Script... > build_range.py,
or from a terminal with the editor open:
    python tools/unreal_exec.py unreal/GarageGames/Content/Python/build_range.py
"""

import os
import sys

import unreal

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import importlib  # noqa: E402

import director  # noqa: E402  (repo root)
import games  # noqa: E402
import garage_env  # noqa: E402
import garage_stream as gs  # noqa: E402
import range_layout as R  # noqa: E402

# the editor keeps imported modules in memory; pick up any edits since the last build
for _m in (games, director, gs, R, garage_env):
    importlib.reload(_m)

MAP = "/Game/Maps/Range"
ART = garage_env.ART
YD = gs.YARD_CM
START_LIGHTING = "night"

assets = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)


def base_material():
    path = ART + "/M_GarageColor"
    if eal.does_asset_exist(path):
        return unreal.load_asset(path)
    mat = assets.create_asset("M_GarageColor", ART, unreal.Material, unreal.MaterialFactoryNew())
    color = mel.create_material_expression(mat, unreal.MaterialExpressionVectorParameter, -500, 0)
    color.set_editor_property("parameter_name", "Color")
    color.set_editor_property("default_value", unreal.LinearColor(1, 1, 1, 1))
    glow = mel.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, -500, 250)
    glow.set_editor_property("parameter_name", "Glow")
    glow.set_editor_property("default_value", 0.0)
    rough = mel.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, -500, 400)
    rough.set_editor_property("parameter_name", "Roughness")
    rough.set_editor_property("default_value", 0.8)
    mult = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -250, 250)
    mel.connect_material_expressions(color, "", mult, "A")
    mel.connect_material_expressions(glow, "", mult, "B")
    mel.connect_material_property(color, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(mult, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.recompile_material(mat)
    eal.save_loaded_asset(mat)
    return mat


def material(key, hex_, glow=0.0, roughness=0.8):
    name = "MI_" + key
    path = "%s/%s" % (ART, name)
    if eal.does_asset_exist(path):
        mi = unreal.load_asset(path)
    else:
        mi = assets.create_asset(name, ART, unreal.MaterialInstanceConstant,
                                 unreal.MaterialInstanceConstantFactoryNew())
        mel.set_material_instance_parent(mi, base_material())
    mel.set_material_instance_vector_parameter_value(mi, "Color", garage_env.hex_color(hex_))
    mel.set_material_instance_scalar_parameter_value(mi, "Glow", glow)
    mel.set_material_instance_scalar_parameter_value(mi, "Roughness", roughness)
    eal.save_loaded_asset(mi)
    return mi


def all_materials():
    mats = {k: material(k, *v) for k, v in R.MATERIALS.items()}
    for i, T in enumerate(games.TARGETS):
        mats[R.target_material(i)] = material(R.target_material(i), T["color"], 0.6, 0.5)
        mats[R.target_inner_material(i)] = material(R.target_inner_material(i), T["color"], 0.2, 0.6)
    mats["ball"] = material("ball", "#ffffff", 0.4, 0.3)
    # tidy up material assets an older build made but this one doesn't use
    # (names compare case-insensitively: Windows treats MI_White and MI_white as one file)
    keep = {"m_garagecolor"} | {"mi_" + k.lower() for k in mats}
    for path in eal.list_assets(ART, recursive=False):
        if path.split(".")[-1].lower() not in keep:
            eal.delete_asset(path)
    return mats


def mesh_height_cm(mesh):
    return max(1.0, mesh.get_bounds().box_extent.z * 2)


def spawn_mesh(p, mats, dressing, counters):
    loc = [c * YD for c in p["pos"]]
    rot = unreal.Rotator(roll=0, pitch=0, yaw=p.get("yaw", 0.0))
    role = p.get("role")
    pool = dressing.get(role) if role in ("tree", "rock") else None
    if role == "trunk" and dressing.get("tree"):
        return None  # a real tree brings its own trunk
    if pool:
        mesh = pool[counters.setdefault(role, 0) % len(pool)]
        counters[role] += 1
        a = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(loc[0], loc[1], 0), rot)
        a.static_mesh_component.set_static_mesh(mesh)
        want = (p["size"][2] / 0.75 if role == "tree" else p["size"][2]) * YD  # cone is 3/4 of a tree's height
        s = want / mesh_height_cm(mesh)
        a.set_actor_scale3d(unreal.Vector(s, s, s))
    else:
        a = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(*loc), rot)
        smc = a.static_mesh_component
        smc.set_static_mesh(unreal.load_asset("/Engine/BasicShapes/" + p["mesh"]))
        mat = mats[p["material"]]
        if dressing.get("grass") and p["material"] in ("rough",):
            mat = dressing["grass"]
        smc.set_material(0, mat)
        size = [max(v, 0.001) * YD / 100.0 for v in p["size"]]
        if p["mesh"] == "Plane":
            size[2] = 1.0
        a.set_actor_scale3d(unreal.Vector(*size))
    a.set_actor_label(p["name"])
    return a


def spawn_text(p):
    loc = [c * YD for c in p["pos"]]
    a = actors.spawn_actor_from_class(unreal.TextRenderActor, unreal.Vector(*loc),
                                      unreal.Rotator(roll=0, pitch=0, yaw=p.get("yaw", 0.0)))
    t = a.text_render
    t.set_text(unreal.Text(p["text"]))
    t.set_world_size(p["height"] * YD)
    t.set_text_render_color(garage_env.srgb(p["color"]))
    t.set_horizontal_alignment(unreal.HorizTextAligment.EHTA_CENTER)
    t.set_vertical_alignment(unreal.VerticalTextAligment.EVRTA_TEXT_CENTER)
    a.set_actor_label(p["name"])
    return a


def spawn_spot(p):
    loc = [c * YD for c in p["pos"]]
    a = actors.spawn_actor_from_class(unreal.SpotLight, unreal.Vector(*loc),
                                      unreal.Rotator(roll=0, pitch=p["pitch"], yaw=p["yaw"]))
    c = a.spot_light_component
    c.set_mobility(unreal.ComponentMobility.MOVABLE)
    c.set_editor_property("intensity_units", unreal.LightUnits.CANDELAS)
    c.set_outer_cone_angle(p["cone"] / 2)
    c.set_inner_cone_angle(p["cone"] / 4)
    c.set_attenuation_radius(p["reach"] * YD)
    c.set_light_color(garage_env.hex_color("#fff1d0"))
    c.set_cast_shadows(False)  # eight shadowed spotlights cost a lot of frame time
    a.set_actor_label(p["name"])
    return a


def build():
    if eal.does_asset_exist(MAP):
        levels.load_level(MAP)
    else:
        levels.new_level(MAP)
    for a in actors.get_all_level_actors():
        if a.get_actor_label().startswith("GG_"):
            actors.destroy_actor(a)

    # ---- sky, sun, fog, exposure ----
    sun = actors.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 1000))
    sun.set_actor_label("GG_Sun")
    sun.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    sun.light_component.set_editor_property("atmosphere_sun_light", True)
    sky = actors.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 500))
    sky.set_actor_label("GG_SkyLight")
    sky.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    sky.light_component.set_editor_property("real_time_capture", True)
    actors.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0)).set_actor_label("GG_SkyAtmosphere")
    actors.spawn_actor_from_class(unreal.ExponentialHeightFog, unreal.Vector(0, 0, 0)).set_actor_label("GG_Fog")
    pp = actors.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 0))
    pp.set_editor_property("unbound", True)
    pp.set_actor_label("GG_PostProcess")

    # ---- the range, from range_layout.py ----
    mats = all_materials()
    dressing = garage_env.dressing()
    counters = {}
    for p in R.layout(games.TARGETS, games.INNER, games.CENTER):
        if p["kind"] == "mesh":
            spawn_mesh(p, mats, dressing, counters)
        elif p["kind"] == "text":
            spawn_text(p)
        elif p["kind"] == "spot":
            spawn_spot(p)

    # ---- the ball and the shot camera (garage_bridge.py moves these) ----
    ball = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 2.7))
    ball.static_mesh_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    ball.static_mesh_component.set_static_mesh(unreal.load_asset("/Engine/BasicShapes/Sphere"))
    ball.static_mesh_component.set_material(0, mats["ball"])
    ball.set_actor_scale3d(unreal.Vector(0.054, 0.054, 0.054))
    ball.set_actor_label("GG_Ball")
    idle = director.idle_camera()
    pos, look = gs.to_unreal(idle["pos"]), gs.to_unreal(idle["look"])
    pitch, yaw, roll = gs.look_rotation(pos, look)
    cam = actors.spawn_actor_from_class(unreal.CameraActor, unreal.Vector(*pos),
                                        unreal.Rotator(roll=roll, pitch=pitch, yaw=yaw))
    cam.set_actor_label("GG_ShotCamera")
    cam.camera_component.set_editor_property("constrain_aspect_ratio", False)
    cam.camera_component.set_field_of_view(gs.horizontal_fov(idle["fov"]))

    garage_env.set_time_of_day(START_LIGHTING, save=False)
    levels.save_current_level()
    eal.save_directory(ART)
    levels.pilot_level_actor(cam)
    unreal.log("[Garage Games] range built: %d targets, %s lighting, %d Fab trees, %d Fab rocks" % (
        len(games.TARGETS), START_LIGHTING, len(dressing["tree"]), len(dressing["rock"])))


build()
