"""Real Undo/Redo with modal and recovery ticks scheduled around history steps."""

import pathlib
import json
import sys
import unittest
from types import SimpleNamespace

import bpy
import bmesh

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import edit_mesh_modifier as addon
from edit_mesh_modifier import edit_session as lifecycle


class Context:
    window = None
    def __getattr__(self, name):
        return getattr(bpy.context, name)


class Session:
    _timer = None
    _cleanup = addon.EDIT_MESH_MODIFIER_OT_Edit._cleanup
    _restore_source_visibility = addon.EDIT_MESH_MODIFIER_OT_Edit._restore_source_visibility
    def report(self, level, text):
        raise AssertionError(text)


class EditUndoTests(unittest.TestCase):
    def setUp(self):
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        lifecycle.reconcile()
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.context.preferences.edit.use_global_undo = True
        bpy.ops.mesh.primitive_cube_add()
        bpy.context.object.name = 'UndoSource'
        self.context = Context()

    def source(self):
        return bpy.data.objects['UndoSource']

    def raw(self):
        source = self.source()
        return addon.get_modifier_socket_value(source.modifiers[0], addon.OBJ_SOCKET)

    def build(self, mirror):
        bpy.ops.edit_mesh_modifier.add()
        source = self.source()
        edit = source.modifiers[0]
        if mirror:
            mod = source.modifiers.new('Mirror', 'MIRROR')
            mod.show_in_editmode = True
        source.modifiers.active = edit
        bpy.ops.ed.undo_push(message='Baseline')

    def enter(self):
        session = Session()
        addon.EDIT_MESH_MODIFIER_OT_Edit.execute(session, self.context)
        bpy.ops.ed.undo_push(message='UI entered Edit Mode')
        return session

    def move(self):
        mesh = bpy.context.object.data
        bm = bmesh.from_edit_mesh(mesh)
        for v in bm.verts:
            v.co.z += 0.25
        bmesh.update_edit_mesh(mesh)
        bpy.ops.ed.undo_push(message='UI vertex move')

    def healthy(self):
        lifecycle.reconcile()
        source = self.source()
        if bpy.context.mode == 'EDIT_MESH':
            self.assertTrue(addon.edit_access.editing_cache(bpy.context))
            self.assertTrue(source.hide_get())
            self.assertIn(lifecycle.RECORD, source)
        else:
            self.assertFalse(source.hide_get())
            if lifecycle.RECORD in source:
                self.assertTrue(json.loads(source[lifecycle.RECORD])['parked'])
            self.assertFalse(any(o.get(addon.edit_preview.MARKER) and not o.hide_get()
                                 for o in bpy.context.scene.objects))
            if self.raw().users_collection:
                self.assertTrue(self.raw().hide_get())
                self.assertTrue(self.raw().hide_render)
        self.assertEqual(len(source.data.vertices), 8)
        self.assertAlmostEqual(min(v.co.z for v in source.data.vertices), -1.0)

    def height(self):
        mesh = self.raw().data
        vertices = bmesh.from_edit_mesh(mesh).verts if mesh.is_editmode else mesh.vertices
        return min(v.co.z for v in vertices) + 1.0

    def test_finished_session_undo_redo_each_tick(self):
        for mirror in (False, True):
            with self.subTest(mirror=mirror):
                self.setUp()
                self.build(mirror)
                session = self.enter()
                self.move()
                self.move()
                bpy.ops.object.mode_set(mode='OBJECT')
                bpy.ops.ed.undo_push(message='UI exit mode before TIMER')
                session._cleanup(self.context)
                self.healthy()
                for expected in (0.5, 0.5, 0.25, 0.0, 0.0, 0.0):
                    self.assertEqual(bpy.ops.ed.undo(), {'FINISHED'})
                    self.healthy()
                    self.assertAlmostEqual(self.height(), expected)
                    self.assertTrue(bpy.ops.ed.redo.poll(), 'Recovery destroyed redo history')
                for expected in (0.0, 0.0, 0.25, 0.5, 0.5, 0.5):
                    self.assertEqual(bpy.ops.ed.redo(), {'FINISHED'})
                    self.healthy()
                    self.assertAlmostEqual(self.height(), expected)
                self.assertAlmostEqual(min(v.co.z for v in self.raw().data.vertices), -0.5)

    def test_fast_undo_before_old_modal_tick(self):
        for mirror in (False, True):
            with self.subTest(mirror=mirror):
                self.setUp()
                self.build(mirror)
                session = self.enter()
                self.move()
                bpy.ops.object.mode_set(mode='OBJECT')
                bpy.ops.ed.undo_push(message='UI exit mode before TIMER')
                bpy.ops.ed.undo()
                addon.EDIT_MESH_MODIFIER_OT_Edit.modal(session, self.context, SimpleNamespace(type='TIMER'))
                self.healthy()
                self.assertEqual(bpy.context.mode, 'EDIT_MESH')
                bpy.ops.object.mode_set(mode='OBJECT')
                session._cleanup(self.context)
                self.healthy()
                self.assertTrue(bpy.ops.ed.redo.poll())

    def test_burst_undo_redo_without_recovery_ticks(self):
        self.build(True)
        session = self.enter()
        self.move()
        self.move()
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.ed.undo_push(message='UI exit')
        session._cleanup(self.context)
        for i in range(4):
            bpy.ops.ed.undo()
        self.healthy()
        for i in range(4):
            bpy.ops.ed.redo()
        self.healthy()

    def test_new_entry_discards_parked_preview_and_old_callback(self):
        self.build(True)
        old = self.enter()
        self.move()
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.ed.undo_push(message='UI exit')
        old._cleanup(self.context)
        bpy.ops.ed.undo()
        self.healthy()
        self.assertTrue(any(addon.edit_preview.is_preview(o) for o in bpy.data.objects))
        new = self.enter()
        self.assertEqual(sum(addon.edit_preview.is_preview(o) for o in bpy.data.objects), 1)
        active = bpy.context.object
        old._cleanup(self.context)
        self.assertEqual(bpy.context.object, active)
        self.assertEqual(bpy.context.mode, 'EDIT_MESH')
        new._cleanup(self.context)
        self.healthy()
        self.assertFalse(any(addon.edit_preview.is_preview(o) for o in bpy.data.objects))

    def test_renaming_edit_object_and_source_keeps_recovery_identity(self):
        self.build(True)
        session = self.enter()
        source = self.source()
        source.name = 'Renamed source'
        bpy.context.object.name = 'Renamed editor'
        token = session._session_token
        self.assertEqual(lifecycle.resolve(token)[0], source)
        bpy.ops.object.mode_set(mode='OBJECT')
        session._cleanup(self.context)
        self.assertFalse(source.hide_get())
        self.assertNotIn(lifecycle.RECORD, source)
        self.assertIsNone(bpy.data.objects.get('Renamed editor'))

    def test_no_change_entry_exit_and_undo_redo(self):
        self.build(True)
        session = self.enter()
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.ed.undo_push(message='UI exit without geometry changes')
        session._cleanup(self.context)
        for _ in range(4):
            bpy.ops.ed.undo()
            self.healthy()
            self.assertAlmostEqual(self.height(), 0.0)
        for _ in range(4):
            bpy.ops.ed.redo()
            self.healthy()
            self.assertAlmostEqual(self.height(), 0.0)

    def test_recovery_independent_of_auto_edit_and_preserves_other_visibility(self):
        bpy.ops.mesh.primitive_cube_add()
        other = bpy.context.object
        other.name = 'Unrelated hidden mesh'
        other.hide_set(True)
        bpy.context.view_layer.objects.active = self.source()
        self.build(True)
        session = self.enter()
        self.move()
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.ed.undo_push(message='UI exit')
        session._cleanup(self.context)
        bpy.ops.ed.undo()
        addon.edit_access.unregister()
        try:
            lifecycle._tick()
            self.healthy()
            self.assertTrue(bpy.data.objects['Unrelated hidden mesh'].hide_get())
            self.assertTrue(bpy.ops.ed.redo.poll())
        finally:
            addon.edit_access.register()


addon.register()
area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
region = next(r for r in area.regions if r.type == 'WINDOW')
with bpy.context.temp_override(area=area, region=region):
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(EditUndoTests))
addon.unregister()
if not result.wasSuccessful():
    raise RuntimeError('Undo recovery tests failed')
