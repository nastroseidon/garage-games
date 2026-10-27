"""Builds the proof-of-concept range level (Content/Maps/Range) from code.

An empty range with one target (Blue, from TARGETS in the repo's games.py),
a ball, the shot camera, and daylight. Safe to run again: it replaces
everything it made before (actors named GG_...).

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

import director  # noqa: E402  (repo root)
import games  # noqa: E402
import garage_stream as gs  # noqa: E402

MAP = "/Game/Maps/Range"
ART = "/Game/Garage"
TARGET = games.TARGETS[3]  # Blue, 120 yds
YD = gs.YARD_CM

assets = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)


def hex_color(h, scale=1.0):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    # sRGB -> linear, which is what material colors use
    lin = [(c / 12.92) if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return unreal.LinearColor(lin[0] * scale, lin[1] * scale, lin[2] * scale, 1.0)


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


def material(name, color, glow=0.0, roughness=0.8):
    path = "%s/%s" % (ART, name)
    if eal.does_asset_exist(path):
        mi = unreal.load_asset(path)
    else:
        mi = assets.create_asset(name, ART, unreal.MaterialInstanceConstant,
                                 unreal.MaterialInstanceConstantFactoryNew())
        mel.set_material_instance_parent(mi, base_material())
    mel.set_material_instance_vector_parameter_value(mi, "Color", color)
    mel.set_material_instance_scalar_parameter_value(mi, "Glow", glow)
    mel.set_material_instance_scalar_parameter_value(mi, "Roughness", roughness)
    eal.save_loaded_asset(mi)
    return mi


def shape(label, mesh, mat, loc, scale, movable=False):
    a = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(*loc))
    smc = a.static_mesh_component
    if movable:
        smc.set_mobility(unreal.ComponentMobility.MOVABLE)
    smc.set_static_mesh(unreal.load_asset("/Engine/BasicShapes/" + mesh))
    smc.set_material(0, mat)
    a.set_actor_scale3d(unreal.Vector(*scale))
    a.set_actor_label(label)
    return a


def disc(label, mat, d_yd, l_yd, radius_yd, height_cm, base_cm=0.0):
    """A flat cylinder (the engine's cylinder is 100 cm wide and 100 cm tall, centred)."""
    s = radius_yd * 2 * YD / 100.0
    return shape(label, "Cylinder", mat, (d_yd * YD, l_yd * YD, base_cm + height_cm / 2), (s, s, height_cm / 100.0))


def build():
    if eal.does_asset_exist(MAP):
        levels.load_level(MAP)
    else:
        levels.new_level(MAP)
    for a in actors.get_all_level_actors():
        if a.get_actor_label().startswith("GG_"):
            actors.destroy_actor(a)

    # ---- light and sky ----
    sun = actors.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 1000),
                                        unreal.Rotator(roll=0, pitch=-38, yaw=-35))
    sun.set_actor_label("GG_Sun")
    sun.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    sun.light_component.set_editor_property("atmosphere_sun_light", True)
    sky = actors.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 500))
    sky.set_actor_label("GG_SkyLight")
    sky.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    sky.light_component.set_editor_property("real_time_capture", True)
    actors.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0)).set_actor_label("GG_SkyAtmosphere")
    fog = actors.spawn_actor_from_class(unreal.ExponentialHeightFog, unreal.Vector(0, 0, 0))
    fog.set_actor_label("GG_Fog")

    # ---- the range ----
    grass = material("MI_Grass", hex_color("#2f7d3a"), roughness=0.95)
    shape("GG_Ground", "Plane", grass, (135 * YD, 0, 0), (330 * YD / 100, 160 * YD / 100, 1))
    shape("GG_TeeMat", "Cube", material("MI_TeeMat", hex_color("#3a3a3a")), (0, 0, 2), (1.5, 1.5, 0.04))

    # ---- one target, from games.py ----
    T = TARGET
    rim = material("MI_Target_" + T["name"], hex_color(T["color"]), glow=0.6, roughness=0.5)
    inner = material("MI_Target_%s_Inner" % T["name"], hex_color(T["color"], 0.55), glow=0.2)
    disc("GG_Target", rim, T["d"], T["l"], T["r"], 6)
    disc("GG_TargetInner", inner, T["d"], T["l"], T["r"] * games.INNER, 4, base_cm=6)
    disc("GG_TargetCenter", rim, T["d"], T["l"], games.CENTER, 3, base_cm=10)
    pin_h = 350
    shape("GG_FlagPin", "Cylinder", material("MI_White", hex_color("#f2f2f2")),
          (T["d"] * YD, T["l"] * YD, pin_h / 2), (0.04, 0.04, pin_h / 100.0))
    shape("GG_Flag", "Cube", material("MI_Flag", hex_color("#ff3b3b"), glow=0.3),
          (T["d"] * YD, T["l"] * YD + 45, pin_h - 30), (0.02, 0.9, 0.6))

    # ---- the ball and the shot camera (garage_bridge.py moves these) ----
    shape("GG_Ball", "Sphere", material("MI_Ball", hex_color("#ffffff"), glow=0.4, roughness=0.3),
          (0, 0, 2.7), (0.054, 0.054, 0.054), movable=True)
    idle = director.idle_camera()
    pos, look = gs.to_unreal(idle["pos"]), gs.to_unreal(idle["look"])
    pitch, yaw, roll = gs.look_rotation(pos, look)
    cam = actors.spawn_actor_from_class(unreal.CameraActor, unreal.Vector(*pos),
                                        unreal.Rotator(roll=roll, pitch=pitch, yaw=yaw))
    cam.set_actor_label("GG_ShotCamera")
    cam.camera_component.set_editor_property("constrain_aspect_ratio", False)
    cam.camera_component.set_field_of_view(gs.horizontal_fov(idle["fov"]))

    levels.save_current_level()
    eal.save_directory(ART)
    levels.pilot_level_actor(cam)
    unreal.log("[Garage Games] range built: %s target at %d yds" % (T["name"], T["d"]))


build()
