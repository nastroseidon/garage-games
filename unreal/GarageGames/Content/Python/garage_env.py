"""Day / night switch and Fab / Quixel dressing for the Garage Games range.

From the editor's Python console (or tools/unreal_exec.py):
    import garage_env
    garage_env.set_time_of_day("night")   # or "day"
    garage_env.dressing()                 # which Fab / Quixel assets build_range.py would use
"""

import unreal

import range_layout as R

ART = "/Game/Garage"
DRESSING_FOLDERS = ["/Game/Fab", "/Game/Megascans"]  # where Fab and Quixel Bridge import (never committed)
TREE_WORDS = ("tree", "pine", "oak", "fir", "spruce", "birch", "maple", "conifer")
BUSH_WORDS = ("bush", "shrub", "hedge")
ROCK_WORDS = ("rock", "boulder", "stone", "cliff")
GRASS_WORDS = ("grass", "lawn", "turf", "meadow")


def hex_color(h, scale=1.0):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    # sRGB -> linear, which is what material colours use
    lin = [(c / 12.92) if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return unreal.LinearColor(lin[0] * scale, lin[1] * scale, lin[2] * scale, 1.0)


def srgb(h):
    h = h.lstrip("#")
    return unreal.Color(r=int(h[0:2], 16), g=int(h[2:4], 16), b=int(h[4:6], 16), a=255)


def _actors():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()


def _by_label(prefix):
    return [a for a in _actors() if a.get_actor_label().startswith(prefix)]


def _glow(name, value):
    path = "%s/%s" % (ART, name)
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        mi = unreal.load_asset(path)
        unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(mi, "Glow", value)
        unreal.EditorAssetLibrary.save_loaded_asset(mi)


def set_time_of_day(name="night", save=True):
    """Apply a lighting setup from range_layout.LIGHTING to the open Range level."""
    L = R.LIGHTING[name]
    for sun in _by_label("GG_Sun"):
        sun.set_actor_rotation(unreal.Rotator(roll=0, pitch=L["sun_pitch"], yaw=L["sun_yaw"]), False)
        lc = sun.light_component
        lc.set_intensity(L["sun_lux"])
        lc.set_light_color(hex_color(L["sun_color"]))
    for sky in _by_label("GG_SkyLight"):
        sky.light_component.set_intensity(L["sky"])
    for fog in _by_label("GG_Fog"):
        fog.component.set_fog_density(L["fog"])
        fog.component.set_fog_inscattering_color(hex_color(L["fog_color"]))
    for spot in _by_label("GG_Tower_"):
        if isinstance(spot, unreal.SpotLight):
            spot.spot_light_component.set_intensity(L["towers"])
            spot.spot_light_component.set_visibility(L["towers"] > 0)
    for pp in _by_label("GG_PostProcess"):
        s = pp.get_editor_property("settings")
        s.set_editor_property("override_auto_exposure_min_brightness", True)
        s.set_editor_property("override_auto_exposure_max_brightness", True)
        s.set_editor_property("auto_exposure_min_brightness", L["exposure"][0])
        s.set_editor_property("auto_exposure_max_brightness", L["exposure"][1])
        pp.set_editor_property("settings", s)
    for i in range(10):
        _glow("MI_" + R.target_material(i), L["glow"])
        _glow("MI_" + R.target_inner_material(i), L["glow"] * 0.35)
    _glow("MI_lamp", L["lamp_glow"])
    if save:
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    unreal.log("[Garage Games] lighting: %s" % name)


def dressing():
    """Fab / Quixel assets on this PC that the range can use (empty if none were downloaded).

    {"tree": [StaticMesh...], "rock": [...], "grass": MaterialInterface or None}
    """
    ar = unreal.AssetRegistryHelpers.get_asset_registry()
    found = {"tree": [], "rock": [], "grass": None}
    for folder in DRESSING_FOLDERS:
        for data in ar.get_assets_by_path(folder, recursive=True):
            name = str(data.asset_name).lower()
            cls = str(data.asset_class_path.asset_name)
            if cls == "StaticMesh":
                if any(w in name for w in TREE_WORDS + BUSH_WORDS):
                    found["tree"].append(data.get_asset())
                elif any(w in name for w in ROCK_WORDS):
                    found["rock"].append(data.get_asset())
            elif cls in ("MaterialInstanceConstant", "Material") and found["grass"] is None:
                if any(w in name for w in GRASS_WORDS):
                    found["grass"] = data.get_asset()
    unreal.log("[Garage Games] dressing: %d tree meshes, %d rock meshes, grass material: %s" % (
        len(found["tree"]), len(found["rock"]), found["grass"].get_name() if found["grass"] else "none"))
    return found
