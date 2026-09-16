"""Run with Blender --background --factory-startup --python this_file.py."""
import pathlib
import sys

import bpy

root = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root.parent))
import edit_mesh_modifier as addon

addon.register()
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
bpy.ops.mesh.primitive_cube_add()
obj = bpy.context.object
obj.name = 'Topology Protection Demo'
bpy.ops.edit_mesh_modifier.add()
first_cache = addon.get_modifier_socket_value(obj.modifiers[-1], addon.OBJ_SOCKET)
first_cache.data.vertices[0].co.x -= 0.25
first_cache.data.update()
sub = obj.modifiers.new('Toggle this Subdivision', 'SUBSURF')
sub.levels = sub.render_levels = 1
bpy.ops.edit_mesh_modifier.add()
cache = addon.get_modifier_socket_value(obj.modifiers[-1], addon.OBJ_SOCKET)
cache.data.vertices[0].co.z += 0.5
cache.data.update()
obj['Instructions'] = 'Toggle the middle Subdivision off/on. Edit Poly 2 bypasses/reappears; edits stay intact.'
for area in bpy.context.screen.areas:
    if area.type == 'PROPERTIES':
        area.spaces.active.context = 'MODIFIER'
    elif area.type == 'VIEW_3D':
        area.spaces.active.region_3d.view_distance = 6
        area.spaces.active.region_3d.view_location = (0, 0, 0)
target = root / 'dist' / 'topology-protection-demo.blend'
target.parent.mkdir(exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(target))
addon.unregister()
print('Saved demo:', target)
