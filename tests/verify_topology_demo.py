"""Open dist/topology-protection-demo.blend in a fresh factory Blender, then run.

Checks saved-node persistence without importing the add-on and render visibility.
"""
import pathlib
import tempfile

import bpy
from mathutils import Vector

obj = bpy.data.objects['Topology Protection Demo']
sub = obj.modifiers['Toggle this Subdivision']
last = obj.modifiers[-1]


def coordinates():
    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(graph)
    mesh = evaluated.to_mesh()
    try:
        return [tuple(v.co) for v in mesh.vertices]
    finally:
        evaluated.to_mesh_clear()


original = coordinates()
assert len(original) == 26
sub.show_viewport = False
assert len(coordinates()) == 8
sub.show_viewport = True
assert coordinates() == original
print('Saved-node off/on test passed without loading the add-on')

scene = bpy.context.scene
camera_data = bpy.data.cameras.new('Test Camera')
camera = bpy.data.objects.new('Test Camera', camera_data)
scene.collection.objects.link(camera)
camera.location = (4, -6, 4)
camera.rotation_euler = (-Vector(camera.location)).to_track_quat('-Z', 'Y').to_euler()
scene.camera = camera
scene.render.engine = 'BLENDER_WORKBENCH'
scene.render.resolution_x = scene.render.resolution_y = 128
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.film_transparent = True
folder = pathlib.Path(tempfile.mkdtemp(prefix='edit-poly-render-test-'))


def render(name):
    path = folder / (name + '.png')
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    image = bpy.data.images.load(str(path))
    try:
        pixels = list(image.pixels)
        assert any(pixels[3::4]), 'Render was empty'
        return pixels
    finally:
        bpy.data.images.remove(image)


sub.show_render = False
paused = render('protected')
last.show_render = False
bypassed = render('explicit-bypass')
assert paused == bypassed, 'Render guard did not match bypassed geometry'
last.show_render = True
sub.show_render = True
resumed = render('resumed')
assert resumed != bypassed, 'Restored render did not show the edited stage'
assert coordinates() == original, 'Render visibility altered the viewport result'
print('Render off/on and independent viewport state passed:', folder)
