"""Run with Blender --background --factory-startup --python this_file.py."""

import pathlib
import sys
import unittest
from unittest import mock

import bpy

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import edit_mesh_modifier as addon
from edit_mesh_modifier.shape_keys import export_shape_key


class ShapeKeyExportTests(unittest.TestCase):
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.ops.mesh.primitive_cube_add()
        self.obj = bpy.context.object

    def build(self):
        result = bpy.ops.edit_mesh_modifier.add('EXEC_DEFAULT')
        self.assertEqual(result, {'FINISHED'})
        self.mod = self.obj.modifiers[-1]
        self.cache = addon.get_modifier_socket_value(self.mod, addon.OBJ_SOCKET)
        self.cache.data.vertices[0].co.x += 0.25
        return self.cache

    def test_save_then_apply(self):
        self.build()
        original = self.obj.data.vertices[0].co.copy()
        key = export_shape_key(self.obj, self.mod, 'Saved')
        self.assertAlmostEqual(key.data[0].co.x, original.x + 0.25)
        self.assertEqual(key.value, 0)
        self.assertEqual(len(self.obj.modifiers), 1)
        self.assertEqual(self.obj.data.vertices[0].co, original)
        cache_name = self.cache.name
        applied = export_shape_key(self.obj, self.mod, 'Applied', False)
        self.assertEqual(applied.value, 1)
        self.assertEqual(len(self.obj.modifiers), 0)
        self.assertNotIn(cache_name, bpy.data.objects)
        self.assertEqual(key.value, 0)

    def test_existing_shape_keys_and_uvs_preserved(self):
        basis = self.obj.shape_key_add(name='Basis')
        existing = self.obj.shape_key_add(name='Existing')
        existing.data[0].co.z += 0.6
        existing.value = 0.5
        self.obj.active_shape_key_index = 1
        expected = [tuple(point.co) for point in existing.data]
        self.build()
        self.assertIsNone(self.cache.data.shape_keys)
        self.assertIn('UVMap', self.cache.data.uv_layers)
        self.assertTrue(all(item.value for item in self.cache.data.attributes[addon.ATTR_JSON].data))
        key = export_shape_key(self.obj, self.mod, 'Only Edit')
        delta = key.data[0].co - basis.data[0].co
        self.assertAlmostEqual(delta.x, 0.25, places=5)
        self.assertAlmostEqual(delta.z, 0, places=5)
        self.assertEqual(existing.value, 0.5)
        self.assertEqual([tuple(point.co) for point in existing.data], expected)
        self.assertEqual(self.obj.active_shape_key_index, 1)

    def test_upstream_deformation_is_baked_and_disabled_on_apply(self):
        deform = self.obj.modifiers.new('Twist', 'SIMPLE_DEFORM')
        deform.deform_method = 'TWIST'
        deform.angle = 0.8
        self.build()
        expected = self.evaluated_coordinates()
        key = export_shape_key(self.obj, self.mod, 'Final Shape', False)
        self.assert_coordinates_close(expected, [tuple(p.co) for p in key.data])
        self.assert_coordinates_close(expected, self.evaluated_coordinates())
        self.assertFalse(deform.show_viewport)
        self.assertFalse(deform.show_render)
        self.assertAlmostEqual(deform.angle, 0.8)

    def test_upstream_generators_rejected_without_changes(self):
        self.obj.modifiers.new('Subdivision', 'SUBSURF')
        self.build()
        with self.assertRaisesRegex(ValueError, 'vertex identity'):
            export_shape_key(self.obj, self.mod, 'Invalid')
        self.assertIsNone(self.obj.data.shape_keys)
        self.assertEqual(len(self.obj.modifiers), 2)

    def test_changed_vertex_count_rejected(self):
        self.build()
        self.cache.data.vertices.add(1)
        with self.assertRaisesRegex(ValueError, 'vertex count'):
            export_shape_key(self.obj, self.mod, 'Invalid')
        self.assertIsNone(self.obj.data.shape_keys)

    def test_changed_faces_rejected_even_with_same_vertex_count(self):
        self.build()
        face = self.cache.data.polygons[0]
        loop_indices = list(face.loop_indices)
        first, second = [self.cache.data.loops[i].vertex_index for i in loop_indices[:2]]
        self.cache.data.loops[loop_indices[0]].vertex_index = second
        self.cache.data.loops[loop_indices[1]].vertex_index = first
        with self.assertRaisesRegex(ValueError, 'Edges or faces'):
            export_shape_key(self.obj, self.mod, 'Invalid')
        self.assertIsNone(self.obj.data.shape_keys)

    def test_duplicate_indices_rejected(self):
        self.build()
        self.cache.data.attributes[addon.ATTR_IDX].data[1].value = 0
        with self.assertRaisesRegex(ValueError, 'unmapped vertices'):
            export_shape_key(self.obj, self.mod, 'Invalid')
        self.assertIsNone(self.obj.data.shape_keys)

    def test_new_vertex_marker_rejected(self):
        self.build()
        self.cache.data.attributes[addon.ATTR_BASE].data[0].value = False
        with self.assertRaisesRegex(ValueError, 'unmapped vertices'):
            export_shape_key(self.obj, self.mod, 'Invalid')

    def test_missing_attributes_rejected(self):
        self.build()
        self.cache.data.attributes.remove(self.cache.data.attributes[addon.ATTR_POS])
        with self.assertRaisesRegex(ValueError, 'correspondence'):
            export_shape_key(self.obj, self.mod, 'Invalid')

    def test_shared_source_mesh_rejected(self):
        self.build()
        other = bpy.data.objects.new('Shared', self.obj.data)
        with self.assertRaisesRegex(ValueError, 'single-user'):
            export_shape_key(self.obj, self.mod, 'Invalid')
        self.assertIsNone(other.data.shape_keys)

    def test_shared_cache_preserved_on_apply(self):
        self.build()
        other = self.obj.copy()
        bpy.context.collection.objects.link(other)
        other.data = self.obj.data.copy()
        cache_name = self.cache.name
        export_shape_key(self.obj, self.mod, 'Applied', False)
        self.assertIn(cache_name, bpy.data.objects)
        self.assertEqual(addon.get_modifier_socket_value(other.modifiers[0], addon.OBJ_SOCKET), self.cache)

    def test_absolute_shape_keys_rejected(self):
        self.obj.shape_key_add(name='Basis')
        self.obj.data.shape_keys.use_relative = False
        self.build()
        with self.assertRaisesRegex(ValueError, 'relative shape keys'):
            export_shape_key(self.obj, self.mod, 'Invalid')
        self.assertEqual(len(self.obj.data.shape_keys.key_blocks), 1)

    def test_operator_targets_named_modifier_and_unique_key_names(self):
        self.build()
        wrong = self.obj.modifiers.new('Downstream', 'SUBSURF')
        self.obj.modifiers.active = wrong
        for _ in range(2):
            result = bpy.ops.edit_mesh_modifier.shape_key('EXEC_DEFAULT', modifier_name=self.mod.name, key_name='Edit', keep_modifier=True)
            self.assertEqual(result, {'FINISHED'})
        self.assertEqual([key.name for key in self.obj.data.shape_keys.key_blocks], ['Basis', 'Edit', 'Edit.001'])
        self.assertEqual(len(self.obj.modifiers), 2)

    def evaluated_coordinates(self):
        self.obj.update_tag()
        graph = bpy.context.evaluated_depsgraph_get()
        graph.update()
        evaluated = self.obj.evaluated_get(graph)
        mesh = evaluated.to_mesh()
        try:
            return [tuple(vertex.co) for vertex in mesh.vertices]
        finally:
            evaluated.to_mesh_clear()

    def assert_coordinates_close(self, expected, actual):
        self.assertEqual(len(expected), len(actual))
        for first, second in zip(expected, actual):
            for a, b in zip(first, second):
                self.assertAlmostEqual(a, b, places=5)

    def test_stacked_save_exports_combined_result(self):
        self.build()
        first = self.mod
        self.build()
        self.build()
        key = export_shape_key(self.obj, self.mod, 'Third Stage')
        basis = self.obj.data.shape_keys.reference_key
        self.assertAlmostEqual(key.data[0].co.x - basis.data[0].co.x, 0.75, places=5)
        self.assertEqual(len(self.obj.modifiers), 3)
        self.assertEqual(self.obj.modifiers[0], first)
        self.assertTrue(all(m.show_viewport for m in self.obj.modifiers))
        self.assertEqual(key.value, 0)

    def test_stacked_apply_keeps_first_stage_and_visible_result(self):
        self.build()
        first = self.mod
        first_cache = self.cache
        self.build()
        expected = self.evaluated_coordinates()
        key = export_shape_key(self.obj, self.mod, 'Second Stage', False)
        self.assertEqual(key.value, 1)
        self.assertEqual(list(self.obj.modifiers), [first])
        self.assertFalse(first.show_viewport)
        self.assertFalse(first.show_render)
        self.assertEqual(addon.get_modifier_socket_value(first, addon.OBJ_SOCKET), first_cache)
        self.assert_coordinates_close(expected, self.evaluated_coordinates())

    def reorder_cache(self, order):
        old = self.cache.data
        inverse = {previous: current for current, previous in enumerate(order)}
        mesh = bpy.data.meshes.new('Reordered cache')
        mesh.from_pydata(
            [tuple(old.vertices[i].co) for i in order],
            [tuple(inverse[i] for i in edge.vertices) for edge in old.edges],
            [tuple(inverse[i] for i in face.vertices) for face in old.polygons])
        for name, kind in ((addon.ATTR_IDX, 'INT'), (addon.ATTR_BASE, 'BOOLEAN'), (addon.ATTR_POS, 'FLOAT_VECTOR')):
            mesh.attributes.new(name, kind, 'POINT')
        for current, previous in enumerate(order):
            mesh.attributes[addon.ATTR_IDX].data[current].value = previous
            mesh.attributes[addon.ATTR_BASE].data[current].value = True
            mesh.attributes[addon.ATTR_POS].data[current].vector = old.attributes[addon.ATTR_POS].data[previous].vector
        self.cache.data = mesh
        mesh.update()
        self.obj.update_tag()

    def test_stacked_vertex_maps_are_composed(self):
        self.build()
        self.reorder_cache([1, 0, 2, 3, 4, 5, 6, 7])
        self.build()
        key = export_shape_key(self.obj, self.mod, 'Mapped Second')
        basis = self.obj.data.shape_keys.reference_key
        self.assertAlmostEqual(key.data[1].co.x - basis.data[1].co.x, 0.25, places=5)
        self.assertAlmostEqual(key.data[0].co.x - basis.data[0].co.x, 0.25, places=5)

    def test_invalid_upstream_stage_is_not_hidden_by_rebake(self):
        self.build()
        first_cache = self.cache
        self.build()
        first_cache.data.attributes[addon.ATTR_IDX].data[1].value = 0
        with self.assertRaisesRegex(ValueError, 'unmapped vertices'):
            export_shape_key(self.obj, self.mod, 'Invalid')
        self.assertIsNone(self.obj.data.shape_keys)
        self.assertEqual(len(self.obj.modifiers), 2)

    def test_frozen_upstream_snapshot_can_be_applied(self):
        self.build()
        addon.set_modifier_socket_value(self.mod, addon.AUTO_FIX_SOCKET, False)
        self.build()
        expected = self.evaluated_coordinates()
        export_shape_key(self.obj, self.mod, 'Saved')
        export_shape_key(self.obj, self.mod, 'Applied', False)
        self.assertEqual(len(self.obj.data.shape_keys.key_blocks), 3)
        self.assertEqual(len(self.obj.modifiers), 1)
        self.assert_coordinates_close(expected, self.evaluated_coordinates())

    def test_render_flags_do_not_change_viewport_snapshot(self):
        self.build()
        self.reorder_cache([1, 0, 2, 3, 4, 5, 6, 7])
        self.mod.show_render = False
        self.build()
        key = export_shape_key(self.obj, self.mod, 'Viewport')
        basis = self.obj.data.shape_keys.reference_key
        for index in (0, 1):
            self.assertAlmostEqual(key.data[index].co.x - basis.data[index].co.x, 0.25, places=5)

    def test_disabled_upstream_is_ignored_even_if_render_enabled_and_cache_invalid(self):
        self.build()
        first = self.mod
        first_cache = self.cache
        self.build()
        first.show_viewport = False
        first.show_render = True
        addon.set_modifier_socket_value(first, addon.OBJ_SOCKET, None)
        key = export_shape_key(self.obj, self.mod, 'Only Enabled')
        basis = self.obj.data.shape_keys.reference_key
        self.assertAlmostEqual(key.data[0].co.x - basis.data[0].co.x, 0.25, places=5)
        self.assertFalse(first.show_viewport)
        self.assertTrue(first.show_render)
        self.assertIn(first_cache.name, bpy.data.objects)

    def test_disabled_selected_stage_is_ignored_and_preserved_on_apply(self):
        self.build()
        first = self.mod
        self.build()
        selected = self.mod
        selected.show_viewport = False
        addon.set_modifier_socket_value(selected, addon.OBJ_SOCKET, None)
        expected = self.evaluated_coordinates()
        key = export_shape_key(self.obj, selected, 'Through Disabled', False)
        self.assertEqual(list(self.obj.modifiers), [first, selected])
        self.assertFalse(first.show_viewport)
        self.assertFalse(selected.show_viewport)
        self.assertTrue(selected.show_render)
        self.assertEqual(key.value, 1)
        self.assert_coordinates_close(expected, self.evaluated_coordinates())

    def test_disabled_generator_is_ignored(self):
        disabled = self.obj.modifiers.new('Disabled Subdivision', 'SUBSURF')
        disabled.show_viewport = False
        disabled.show_render = True
        self.build()
        key = export_shape_key(self.obj, self.mod, 'Visible Only', False)
        self.assertAlmostEqual(key.data[0].co.x-self.obj.data.shape_keys.reference_key.data[0].co.x, 0.25)
        self.assertFalse(disabled.show_viewport)
        self.assertTrue(disabled.show_render)

    def test_all_stages_disabled_produces_neutral_key(self):
        self.build()
        self.mod.show_viewport = False
        key = export_shape_key(self.obj, self.mod, 'Neutral')
        self.assert_coordinates_close([tuple(v.co) for v in self.obj.data.vertices], [tuple(p.co) for p in key.data])

    def test_downstream_is_not_included(self):
        self.build()
        downstream = self.obj.modifiers.new('Later Twist', 'SIMPLE_DEFORM')
        downstream.angle = 1.0
        key = export_shape_key(self.obj, self.mod, 'Before Twist')
        basis = self.obj.data.shape_keys.reference_key
        for index in range(len(basis.data)):
            delta = key.data[index].co - basis.data[index].co
            self.assertAlmostEqual(delta.x, 0.25 if index == 0 else 0)
            self.assertAlmostEqual(delta.y, 0)
            self.assertAlmostEqual(delta.z, 0)
        self.assertTrue(downstream.show_viewport)

    def test_temporary_evaluation_does_not_leak_or_change_source_stack(self):
        self.build()
        self.build()
        before = (len(bpy.data.objects), self.obj.data.users, addon._is_system_ready)
        states = [(m.name, m.show_viewport, m.show_render) for m in self.obj.modifiers]
        export_shape_key(self.obj, self.mod, 'Saved')
        self.assertEqual(before, (len(bpy.data.objects), self.obj.data.users, addon._is_system_ready))
        self.assertEqual(states, [(m.name, m.show_viewport, m.show_render) for m in self.obj.modifiers])

    def test_applying_middle_stage_preserves_downstream_result(self):
        self.build()
        self.build()
        middle = self.mod
        self.build()
        downstream = self.mod
        expected = self.evaluated_coordinates()
        export_shape_key(self.obj, middle, 'First Two', False)
        self.assertTrue(downstream.show_viewport)
        self.assertEqual(len(self.obj.modifiers), 2)
        self.assert_coordinates_close(expected, self.evaluated_coordinates())

    def test_failed_evaluation_cleans_up_without_creating_key(self):
        self.build()
        import edit_mesh_modifier.shape_keys as module
        original = module._check_topology
        calls = 0

        def fail_on_evaluated_mesh(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError('simulated evaluation failure')
            return original(*args)

        before = (len(bpy.data.objects), self.obj.data.users, addon._is_system_ready)
        with mock.patch.object(module, '_check_topology', side_effect=fail_on_evaluated_mesh):
            with self.assertRaisesRegex(RuntimeError, 'simulated evaluation failure'):
                export_shape_key(self.obj, self.mod, 'Invalid')
        self.assertEqual(before, (len(bpy.data.objects), self.obj.data.users, addon._is_system_ready))
        self.assertIsNone(self.obj.data.shape_keys)
        self.assertTrue(self.mod.show_viewport)


addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(ShapeKeyExportTests)
result = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not result.wasSuccessful():
    raise RuntimeError('Shape key export tests failed')
