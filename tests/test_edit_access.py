"""Run in a separate Blender with --background --factory-startup."""

import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

import bpy
try:
    from _bpy_restrict_state import RestrictBlend
except ImportError:
    from bpy_restrict_state import RestrictBlend

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
        access._resume_auto_edit()
        self.assertEqual(bpy.context.area.type, 'VIEW_3D')

    def auto_operator(self, operation):
        return mock.patch.object(access, 'bpy', SimpleNamespace(
            context=bpy.context, app=bpy.app, data=bpy.data,
            ops=SimpleNamespace(object=bpy.ops.object,
                                edit_mesh_modifier=SimpleNamespace(edit=operation))))

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
            self.assertFalse(bpy.app.timers.is_registered(access._auto_edit_tick))
            self.assertTrue(all(callback not in handlers for handlers, callback in access._auto_handlers))
            self.assertIn(callback, menu.draw._draw_funcs)
            self.assertIn(old_hook[2], menu.draw._draw_funcs)
            self.assertNotIn(old_hook[1], menu.draw._draw_funcs)
            with RestrictBlend():
                access.register()
            self.assertTrue(bpy.app.timers.is_registered(access._auto_edit_tick))
            self.assertTrue(all(handlers.count(callback) == 1 for handlers, callback in access._auto_handlers))
            self.assertIsNotNone(access._pie_hook)
            self.assertIn(callback, menu.draw._draw_funcs)
            self.assertEqual(sum(f.__qualname__.endswith('draw_with_edit_poly')
                                 for f in menu.draw._draw_funcs), 1)
        finally:
            menu.remove(callback)

    def test_auto_entry_selects_active_stage_and_does_not_reenter_cache(self):
        first, cache = self.build()
        self.build()
        self.obj.modifiers.active = first
        session = Session()
        operation = mock.Mock(side_effect=lambda *args:
                              addon.EDIT_MESH_MODIFIER_OT_Edit.execute(session, self.context))
        access._auto_edit_tick()  # Observe Object Mode.
        bpy.ops.object.mode_set(mode='EDIT', toggle=True)
        try:
            with self.auto_operator(operation):
                access._auto_edit_tick()
                self.assertEqual(bpy.context.object, cache)
                self.assertTrue(self.obj.hide_get())
                access._auto_edit_tick()
                operation.assert_called_once_with('INVOKE_DEFAULT')
                bpy.ops.object.mode_set(mode='OBJECT')
                addon.EDIT_MESH_MODIFIER_OT_Edit.modal(session, self.context, SimpleNamespace(type='TIMER'))
                access._auto_edit_tick()
                self.assertEqual(bpy.context.object, self.obj)
                self.assertFalse(self.obj.hide_get())
                self.assertEqual(operation.call_count, 1)
        finally:
            if bpy.context.object == cache:
                session._cleanup(self.context)

    def test_auto_off_keeps_source_editing(self):
        self.build()
        access._auto_edit_tick()
        bpy.ops.object.mode_set(mode='EDIT')
        operation = mock.Mock()
        with mock.patch.object(access, '_auto_enabled', return_value=False), self.auto_operator(operation):
            self.assertIsNone(access._auto_edit_tick())
        operation.assert_not_called()
        self.assertEqual(bpy.context.object, self.obj)
        self.assertEqual(self.obj.mode, 'EDIT')

    def test_enabling_while_editing_waits_for_next_entry(self):
        self.build()
        bpy.ops.object.mode_set(mode='EDIT')
        access.update_auto_edit(None, bpy.context)
        operation = mock.Mock(return_value={'FINISHED'})
        with self.auto_operator(operation):
            access._auto_edit_tick()
            operation.assert_not_called()
            bpy.ops.object.mode_set(mode='OBJECT')
            access._auto_edit_tick()
            bpy.ops.object.mode_set(mode='EDIT')
            access._auto_edit_tick()
            operation.assert_called_once_with('INVOKE_DEFAULT')

    def test_disabled_viewport_stage_keeps_source_editing(self):
        self.build()  # An enabled earlier stage must not become the edit target.
        mod, cache = self.build()
        mod.show_viewport = False
        operation = mock.Mock()
        for render in (True, False):
            with self.subTest(render=render), self.auto_operator(operation):
                mod.show_render = render
                access._auto_edit_tick()
                bpy.ops.object.mode_set(mode='EDIT')
                access._auto_edit_tick()
                access._auto_edit_tick()
                operation.assert_not_called()
                self.assertEqual(bpy.context.object, self.obj)
                self.assertEqual(self.obj.mode, 'EDIT')
                self.assertFalse(self.obj.hide_get())
                self.assertEqual(len(cache.users_collection), 0)
                self.assertFalse(mod.show_viewport)
                bpy.ops.object.mode_set(mode='OBJECT')

    def test_reenabled_viewport_stage_redirects_on_next_entry(self):
        mod, cache = self.build()
        mod.show_viewport = False
        mod.show_render = False
        session = Session()
        operation = mock.Mock(side_effect=lambda *args:
                              addon.EDIT_MESH_MODIFIER_OT_Edit.execute(session, self.context))
        try:
            with self.auto_operator(operation):
                access._auto_edit_tick()
                bpy.ops.object.mode_set(mode='EDIT')
                access._auto_edit_tick()
                mod.show_viewport = True
                access._auto_edit_tick()
                operation.assert_not_called()
                self.assertEqual(bpy.context.object, self.obj)
                bpy.ops.object.mode_set(mode='OBJECT')
                access._auto_edit_tick()
                bpy.ops.object.mode_set(mode='EDIT')
                access._auto_edit_tick()
                operation.assert_called_once_with('INVOKE_DEFAULT')
                self.assertEqual(bpy.context.object, cache)
                self.assertTrue(self.obj.hide_get())
                self.assertFalse(mod.show_render)
        finally:
            if bpy.context.object == cache:
                session._cleanup(self.context)

    def test_auto_ignores_other_modifiers_and_missing_caches(self):
        mod, cache = self.build()
        native = self.obj.modifiers.new('Other', 'SUBSURF')
        self.obj.modifiers.active = native
        operation = mock.Mock()
        with self.auto_operator(operation):
            access._auto_edit_tick()
            bpy.ops.object.mode_set(mode='EDIT')
            access._auto_edit_tick()
            operation.assert_not_called()
            bpy.ops.object.mode_set(mode='OBJECT')
            self.obj.modifiers.active = mod
            addon.set_modifier_socket_value(mod, addon.OBJ_SOCKET, None)
            access._auto_edit_tick()
            bpy.ops.object.mode_set(mode='EDIT')
            access._auto_edit_tick()
            operation.assert_not_called()

    def test_auto_does_not_redirect_undo_or_load_restoration(self):
        self.build()
        access._auto_edit_tick()
        operation = mock.Mock()
        with self.auto_operator(operation):
            access._pause_auto_edit()
            bpy.ops.object.mode_set(mode='EDIT')
            access._auto_edit_tick()
            access._resume_auto_edit()
            access._auto_edit_tick()
            operation.assert_not_called()

    def test_failed_auto_entry_restores_mode_without_repeated_attempts(self):
        self.build()
        access._auto_edit_tick()
        bpy.ops.object.mode_set(mode='EDIT')

        def fail(*args):
            bpy.ops.object.mode_set(mode='OBJECT')
            raise RuntimeError('Simulated entry failure')

        operation = mock.Mock(side_effect=fail)
        with self.auto_operator(operation):
            access._auto_edit_tick()
            self.assertEqual(bpy.context.object, self.obj)
            self.assertEqual(self.obj.mode, 'EDIT')
            access._auto_edit_tick()
            operation.assert_called_once()

    def test_disabling_stops_timer_and_reenabling_restarts_it(self):
        with mock.patch.object(access, '_auto_enabled', return_value=False):
            access.update_auto_edit(None, bpy.context)
            self.assertFalse(bpy.app.timers.is_registered(access._auto_edit_tick))
        access.update_auto_edit(None, bpy.context)
        self.assertTrue(bpy.app.timers.is_registered(access._auto_edit_tick))

    def test_standard_appearance_preserves_overlays_and_restores_cache_display(self):
        mod, cache = self.build()
        space = bpy.context.area.spaces.active
        original_retopology = space.overlay.show_retopology
        self.obj.color = (0.2, 0.4, 0.7, 1.0)
        self.obj.show_in_front = True
        self.obj.show_wire = True
        self.obj.show_all_edges = True
        cache.color = (0.8, 0.1, 0.2, 1.0)
        before_color = tuple(cache.color)
        before_flags = (cache.show_in_front, cache.show_wire, cache.show_all_edges)
        for retopology in (False, True):
            with self.subTest(retopology=retopology):
                space.overlay.show_retopology = retopology
                session = Session()
                try:
                    addon.EDIT_MESH_MODIFIER_OT_Edit.execute(session, self.context)
                    self.assertEqual(space.overlay.show_retopology, retopology)
                    self.assertEqual(tuple(cache.color), tuple(self.obj.color))
                    self.assertTrue(cache.show_in_front and cache.show_wire and cache.show_all_edges)
                    self.assertEqual(cache.display_type, self.obj.display_type)
                finally:
                    session._cleanup(self.context)
                self.assertEqual(tuple(cache.color), before_color)
                self.assertEqual((cache.show_in_front, cache.show_wire, cache.show_all_edges), before_flags)
                self.assertEqual(space.overlay.show_retopology, retopology)
        space.overlay.show_retopology = original_retopology

    def test_legacy_appearance_forces_retopology_then_restores_it(self):
        mod, cache = self.build()
        space = bpy.context.area.spaces.active
        original = space.overlay.show_retopology
        space.overlay.show_retopology = False
        self.obj.color = (0.2, 0.4, 0.7, 1.0)
        before_color = tuple(cache.color)
        self.context.preferences = SimpleNamespace(addons={
            'edit_mesh_modifier': SimpleNamespace(preferences=SimpleNamespace(standard_edit_appearance=False))})
        session = Session()
        try:
            addon.EDIT_MESH_MODIFIER_OT_Edit.execute(session, self.context)
            self.assertTrue(space.overlay.show_retopology)
            self.assertEqual(tuple(cache.color), before_color)
        finally:
            addon.EDIT_MESH_MODIFIER_OT_Edit.cancel(session, self.context)
        self.assertFalse(space.overlay.show_retopology)
        space.overlay.show_retopology = original

    def test_entry_failure_restores_display_settings(self):
        mod, cache = self.build()
        self.obj.color = (0.2, 0.4, 0.7, 1.0)
        original = tuple(cache.color)
        session = Session()
        session.report = mock.Mock()
        # Fail after display properties were copied, before entering Edit Mode.
        with mock.patch.object(addon, 'bpy', SimpleNamespace(
                ops=SimpleNamespace(object=SimpleNamespace(mode_set=mock.Mock(side_effect=RuntimeError('test')))),
                data=bpy.data)):
            result = addon.EDIT_MESH_MODIFIER_OT_Edit.execute(session, self.context)
        self.assertEqual(result, {'CANCELLED'})
        self.assertEqual(tuple(cache.color), original)
        self.assertFalse(self.obj.hide_get())


with RestrictBlend():
    addon.register()
area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
with bpy.context.temp_override(area=area):
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(EditAccessTests))
addon.unregister()
if not result.wasSuccessful():
    raise RuntimeError('Edit access tests failed')
