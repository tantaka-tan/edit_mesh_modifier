"""Run in a separate Blender with --background --factory-startup."""

import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

import bpy

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import edit_mesh_modifier as addon
from edit_mesh_modifier import edit_access as access


class Context:
    window = None  # Exercise the modal session deterministically without a GUI loop.

    def __getattr__(self, name):
        return getattr(bpy.context, name)


class Session:
    _timer = None
    _cleanup = addon.EDIT_MESH_MODIFIER_OT_Edit._cleanup
    _restore_source_visibility = addon.EDIT_MESH_MODIFIER_OT_Edit._restore_source_visibility

    def report(self, kind, message):
        raise AssertionError(message)


class Layout:
    def __init__(self):
        self.pies = []
        self.items = []

    def menu_pie(self):
        pie = Layout()
        self.pies.append(pie)
        return pie

    def operator_enum(self, *args, **kwargs):
        self.items.append(('enum', args, kwargs))

    def operator(self, *args, **kwargs):
        self.items.append(('operator', args, kwargs))


class EditAccessTests(unittest.TestCase):
    def setUp(self):
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.ops.mesh.primitive_cube_add()
        self.obj = bpy.context.object
        self.context = Context()
        self.assertEqual(bpy.context.area.type, 'VIEW_3D')

    def build(self):
        self.assertEqual(bpy.ops.edit_mesh_modifier.add(), {'FINISHED'})
        mod = self.obj.modifiers[-1]
        return mod, addon.get_modifier_socket_value(mod, addon.OBJ_SOCKET)

    def test_selected_stage_and_exit_restore_source(self):
        first, first_cache = self.build()
        second, second_cache = self.build()
        self.obj.modifiers.active = first
        session = Session()
        self.assertTrue(access.EDIT_MESH_MODIFIER_OT_ToggleEdit.poll(self.context))
        self.assertEqual(addon.EDIT_MESH_MODIFIER_OT_Edit.execute(session, self.context), {'FINISHED'})
        try:
            self.assertEqual(bpy.context.object, first_cache)
            self.assertTrue(self.obj.hide_get())
            self.assertTrue(access.editing_cache(self.context))
            self.assertTrue(access.EDIT_MESH_MODIFIER_OT_ToggleEdit.poll(self.context))
            self.assertEqual(access.EDIT_MESH_MODIFIER_OT_ToggleEdit.execute(None, self.context), {'FINISHED'})
            self.assertEqual(bpy.context.mode, 'OBJECT')
        finally:
            addon.EDIT_MESH_MODIFIER_OT_Edit.modal(session, self.context, SimpleNamespace(type='TIMER'))
        self.assertEqual(bpy.context.object, self.obj)
        self.assertFalse(self.obj.hide_get())
        self.assertEqual(len(first_cache.users_collection), 0)
        self.assertEqual(len(second_cache.users_collection), 0)
        self.assertEqual(self.obj.modifiers.active, first)

    def test_invalid_selection_and_regular_edit_mode(self):
        self.assertFalse(access.EDIT_MESH_MODIFIER_OT_ToggleEdit.poll(self.context))
        self.build()
        native = self.obj.modifiers.new('Other', 'SUBSURF')
        self.obj.modifiers.active = native
        self.assertFalse(access.EDIT_MESH_MODIFIER_OT_ToggleEdit.poll(self.context))
        self.obj.modifiers.active = self.obj.modifiers[0]
        bpy.ops.object.mode_set(mode='EDIT')
        self.assertFalse(access.editing_cache(self.context))
        self.assertFalse(access.EDIT_MESH_MODIFIER_OT_ToggleEdit.poll(self.context))
        bpy.ops.object.mode_set(mode='OBJECT')

    def test_toggle_delegates_to_existing_edit_operator(self):
        self.build()
        operation = mock.Mock(return_value={'RUNNING_MODAL'})
        ops = SimpleNamespace(edit_mesh_modifier=SimpleNamespace(edit=operation))
        with mock.patch.object(access, 'bpy', SimpleNamespace(ops=ops, data=bpy.data)):
            self.assertEqual(access.EDIT_MESH_MODIFIER_OT_ToggleEdit.execute(None, self.context), {'FINISHED'})
        operation.assert_called_once_with('INVOKE_DEFAULT')

    def test_pie_uses_same_radial_layout_as_native_modes(self):
        self.build()
        layout = Layout()
        access._pie_hook[1](SimpleNamespace(layout=layout), self.context)
        self.assertEqual(len(layout.pies), 1)
        items = layout.pies[0].items
        self.assertEqual(items[0][1], ('object.mode_set', 'mode'))
        self.assertEqual(items[1][1], ('edit_mesh_modifier.toggle_edit',))
        self.assertEqual(items[1][2]['text'], 'Edit Poly')

    def test_preference_hides_entry(self):
        self.build()
        context = SimpleNamespace(preferences=SimpleNamespace(addons={
            'edit_mesh_modifier': SimpleNamespace(preferences=SimpleNamespace(show_in_mode_pie=False))}))
        layout = Layout()
        access._pie_hook[1](SimpleNamespace(layout=layout), context)
        self.assertEqual(len(layout.pies[0].items), 1)

    def test_unregister_preserves_other_menu_callbacks(self):
        menu = bpy.types.VIEW3D_MT_object_mode_pie
        callback = lambda self, context: None
        menu.append(callback)
        old_hook = access._pie_hook
        try:
            access.unregister()
            self.assertIn(callback, menu.draw._draw_funcs)
            self.assertIn(old_hook[2], menu.draw._draw_funcs)
            self.assertNotIn(old_hook[1], menu.draw._draw_funcs)
            access.register()
            self.assertIsNotNone(access._pie_hook)
            self.assertIn(callback, menu.draw._draw_funcs)
            self.assertEqual(sum(f.__qualname__.endswith('draw_with_edit_poly')
                                 for f in menu.draw._draw_funcs), 1)
        finally:
            menu.remove(callback)


addon.register()
area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
with bpy.context.temp_override(area=area):
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(EditAccessTests))
addon.unregister()
if not result.wasSuccessful():
    raise RuntimeError('Edit access tests failed')
