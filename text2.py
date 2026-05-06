import bpy
import sys
import os
import random

# =========================
# USER RANDOMIZATION KNOBS
# =========================
RANDOMIZE = True

HUE_SHIFT = 0.03        # 0.0 - 0.5
SAT_JITTER = 0.25         # 0.0 - 1.0
VAL_JITTER = 0.3         # 0.0 - 1.0

ROUGHNESS_JITTER = 0.35   # 0.0 - 1.0
METALLIC_JITTER = 0.2    # 0.0 - 1.0

ADD_DIRT = True
DIRT_STRENGTH = 0.30     # 0.0 - 1.0
DIRT_SCALE = 18.0        # larger = finer noise

ADD_BUMP = True
BUMP_STRENGTH = 0.2      # 0.0 - 1.0
BUMP_SCALE = 40.0         # larger = finer bump

TEXTURE_RES = 2048
COLLISION_DECIMATE = 0.1


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


argv = sys.argv
argv = argv[argv.index("--") + 1:]
input_path = argv[0]
output_dir = argv[1]
os.makedirs(output_dir, exist_ok=True)

# --------- CLEAN SCENE ----------
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# --------- IMPORT GLB ----------
bpy.ops.import_scene.gltf(filepath=input_path)
mesh_objs = [o for o in bpy.context.selected_objects if o.type == 'MESH']
if not mesh_objs:
    print("Error: No mesh found.")
    sys.exit(1)

obj = mesh_objs[0]
bpy.context.view_layer.objects.active = obj
obj.select_set(True)

# --------- APPLY TRANSFORMS & NORMALIZE ----------
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bbox = obj.dimensions
scale_factor = 1.0 / max(bbox)
obj.scale = (scale_factor, scale_factor, scale_factor)
bpy.ops.object.transform_apply(scale=True)

# --------- MESH CLEANUP & UV ----------
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.remove_doubles()
bpy.ops.mesh.normals_make_consistent(inside=False)

if not obj.data.uv_layers:
    print("No UVs found, generating smart UV project...")
    bpy.ops.uv.smart_project()
else:
    print(f"Using existing UVs: {[uv.name for uv in obj.data.uv_layers]}")

bpy.ops.object.mode_set(mode='OBJECT')

# --------- EXPORT VISUAL MESH ----------
visual_path = os.path.join(output_dir, "visual.obj")
bpy.ops.wm.obj_export(filepath=visual_path, export_selected_objects=True)

# --------- CREATE BAKE IMAGE ----------
bake_img = bpy.data.images.new("BakedTexture", width=TEXTURE_RES, height=TEXTURE_RES)

# --------- MATERIAL RANDOMIZATION ----------
def randomize_material(mat):
    if mat is None:
        return

    mat.use_nodes = True
    nt = mat.node_tree
    nodes = nt.nodes
    links = nt.links

    bsdf = None
    for n in nodes:
        if n.type == 'BSDF_PRINCIPLED':
            bsdf = n
            break
    if bsdf is None:
        return

    # Bake target image node
    img_node = nodes.new(type='ShaderNodeTexImage')
    img_node.image = bake_img
    nodes.active = img_node

    if not RANDOMIZE:
        return

    # -------------------------
    # Roughness / Metallic
    # -------------------------
    if "Roughness" in bsdf.inputs:
        r = bsdf.inputs["Roughness"].default_value
        bsdf.inputs["Roughness"].default_value = clamp(
            r + random.uniform(-ROUGHNESS_JITTER, ROUGHNESS_JITTER)
        )

    if "Metallic" in bsdf.inputs:
        m = bsdf.inputs["Metallic"].default_value
        bsdf.inputs["Metallic"].default_value = clamp(
            m + random.uniform(-METALLIC_JITTER, METALLIC_JITTER)
        )

    # -------------------------
    # Base Color perturbation
    # -------------------------
    base_input = bsdf.inputs["Base Color"]

    hsv = nodes.new(type='ShaderNodeHueSaturation')
    hsv.inputs["Hue"].default_value = 0.5 + random.uniform(-HUE_SHIFT, HUE_SHIFT)
    hsv.inputs["Saturation"].default_value = 1.0 + random.uniform(-SAT_JITTER, SAT_JITTER)
    hsv.inputs["Value"].default_value = 1.0 + random.uniform(-VAL_JITTER, VAL_JITTER)

    # Rewire existing base color source -> HSV -> BSDF
    if base_input.is_linked:
        src_link = base_input.links[0]
        from_socket = src_link.from_socket
        links.remove(src_link)
        links.new(from_socket, hsv.inputs["Color"])
        links.new(hsv.outputs["Color"], base_input)
    else:
        rgba = base_input.default_value
        hsv.inputs["Color"].default_value = rgba
        links.new(hsv.outputs["Color"], base_input)

    # -------------------------
    # Dirt overlay
    # -------------------------
    if ADD_DIRT:
        texcoord = nodes.new(type='ShaderNodeTexCoord')
        mapping = nodes.new(type='ShaderNodeMapping')
        noise = nodes.new(type='ShaderNodeTexNoise')
        ramp = nodes.new(type='ShaderNodeValToRGB')
        mix = nodes.new(type='ShaderNodeMixRGB')

        mapping.inputs["Scale"].default_value = (DIRT_SCALE, DIRT_SCALE, DIRT_SCALE)
        noise.inputs["Scale"].default_value = 5.0
        noise.inputs["Detail"].default_value = 8.0

        ramp.color_ramp.elements[0].position = 0.35
        ramp.color_ramp.elements[1].position = 0.75

        mix.blend_type = 'MULTIPLY'
        mix.inputs["Fac"].default_value = DIRT_STRENGTH
        mix.inputs[2].default_value = (0.75, 0.75, 0.75, 1.0)

        links.new(texcoord.outputs["Object"], mapping.inputs["Vector"])
        links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
        links.new(noise.outputs["Fac"], ramp.inputs["Fac"])

        # Insert dirt after HSV
        links.remove(base_input.links[0])
        links.new(hsv.outputs["Color"], mix.inputs[1])
        links.new(ramp.outputs["Color"], mix.inputs[2])
        links.new(mix.outputs["Color"], base_input)

    # -------------------------
    # Bump / micro surface
    # -------------------------
    if ADD_BUMP:
        texcoord2 = nodes.new(type='ShaderNodeTexCoord')
        mapping2 = nodes.new(type='ShaderNodeMapping')
        noise2 = nodes.new(type='ShaderNodeTexNoise')
        bump = nodes.new(type='ShaderNodeBump')

        mapping2.inputs["Scale"].default_value = (BUMP_SCALE, BUMP_SCALE, BUMP_SCALE)
        noise2.inputs["Scale"].default_value = 8.0
        noise2.inputs["Detail"].default_value = 12.0
        bump.inputs["Strength"].default_value = BUMP_STRENGTH

        links.new(texcoord2.outputs["Object"], mapping2.inputs["Vector"])
        links.new(mapping2.outputs["Vector"], noise2.inputs["Vector"])
        links.new(noise2.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


for mat in obj.data.materials:
    randomize_material(mat)

# --------- BAKE ----------
bpy.context.scene.render.engine = 'CYCLES'
bpy.context.scene.cycles.device = 'CPU'

bpy.context.scene.render.bake.use_pass_direct = False
bpy.context.scene.render.bake.use_pass_indirect = False
bpy.context.scene.render.bake.use_pass_color = True

bpy.ops.object.select_all(action='DESELECT')
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.object.bake(type='DIFFUSE')

# --------- SAVE TEXTURE ----------
texture_path = os.path.join(output_dir, "texture.png")
bake_img.filepath_raw = texture_path
bake_img.file_format = 'PNG'
bake_img.save()
print(f"Texture saved to: {texture_path}")

# --------- CREATE COLLISION MESH ----------
bpy.ops.object.select_all(action='DESELECT')
collision_obj = obj.copy()
collision_obj.data = obj.data.copy()
bpy.context.collection.objects.link(collision_obj)
collision_obj.data.materials.clear()
bpy.context.view_layer.objects.active = collision_obj
collision_obj.select_set(True)

mod = collision_obj.modifiers.new(name="Decimate", type='DECIMATE')
mod.ratio = COLLISION_DECIMATE
bpy.ops.object.modifier_apply(modifier="Decimate")

collision_path = os.path.join(output_dir, "collision.obj")
bpy.ops.wm.obj_export(filepath=collision_path, export_selected_objects=True)
print(f"Collision mesh exported: {len(collision_obj.data.vertices)} vertices")

# --------- PATCH MTL ----------
mtl_path = visual_path.replace(".obj", ".mtl")
if os.path.exists(mtl_path):
    with open(mtl_path, 'a') as f:
        f.write(f"\nmap_Kd texture.png\n")
    print("MTL patched with texture reference")

print("Processing complete")