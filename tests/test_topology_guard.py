"""Blender integration tests for the experimental topology guard."""

import pathlib
import sys
import unittest

import bpy

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import edit_mesh_modifier as addon
from edit_mesh_modifier import topology_guard as guard


class TopologyGuardTests(unittest.TestCase):
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.ops.mesh.primitive_cube_add()
        self.obj = bpy.context.object

    def build(self):
        self.assertEqual(bpy.ops.edit_mesh_modifier.add(), {'FINISHED'})
        mod = self.obj.modifiers[-1]
        cache = addon.get_modifier_socket_value(mod, addon.OBJ_SOCKET)
        self.assertTrue(guard.enabled(mod))
        self.assertIsNotNone(guard.reference(mod))
        return mod, cache

    def geometry(self):
        self.obj.update_tag()
        bpy.context.view_layer.update()
        graph = bpy.context.evaluated_depsgraph_get()
        obj = self.obj.evaluated_get(graph)
        mesh = obj.to_mesh()
        try:
            return ([tuple(v.co) for v in mesh.vertices],
                    [tuple(e.vertices) for e in mesh.edges],
                    [tuple(p.vertices) for p in mesh.polygons])
        finally:
            obj.to_mesh_clear()

    def expected_prefix(self, mod):
        with guard.upstream_mesh(bpy.context, self.obj, mod) as mesh:
            return ([tuple(v.co) for v in mesh.vertices],
                    [tuple(e.vertices) for e in mesh.edges],
                    [tuple(p.vertices) for p in mesh.polygons])

    def move(self, cache):
        cache.data.vertices[0].co.z += 0.3
        cache.data.update()

    def sort_modifier(self):
        mod = self.obj.modifiers.new('Reorder points', 'NODES')
        ng = bpy.data.node_groups.new('Reverse point order', 'GeometryNodeTree')
        ng.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
        ng.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
        inp = ng.nodes.new('NodeGroupInput')
        out = ng.nodes.new('NodeGroupOutput')
        sort = ng.nodes.new('GeometryNodeSortElements')
        sort.domain = 'POINT'
        index = ng.nodes.new('GeometryNodeInputIndex')
        negative = ng.nodes.new('ShaderNodeMath')
        negative.operation = 'MULTIPLY'
        negative.inputs[1].default_value = -1
        ng.links.new(index.outputs[0], negative.inputs[0])
        ng.links.new(negative.outputs[0], sort.inputs['Sort Weight'])
        ng.links.new(inp.outputs['Geometry'], sort.inputs['Geometry'])
        ng.links.new(sort.outputs['Geometry'], out.inputs['Geometry'])
        mod.node_group = ng
        return mod

    def test_subdivision_off_bypasses_and_on_restores_edits(self):
        self.build()
        sub = self.obj.modifiers.new('Intermediate Subdivision', 'SUBSURF')
        sub.levels = 1
        mod, cache = self.build()
        self.move(cache)
        original = self.geometry()
        saved_cache = [tuple(v.co) for v in cache.data.vertices]
        for _ in range(3):
            sub.show_viewport = False
            self.assertEqual(self.geometry(), self.expected_prefix(mod))
            self.assertIsNotNone(guard.check_input(bpy.context, self.obj, mod))
            sub.show_viewport = True
            self.assertEqual(self.geometry(), original)
            self.assertIsNone(guard.check_input(bpy.context, self.obj, mod))
        self.assertEqual(saved_cache, [tuple(v.co) for v in cache.data.vertices])
        self.assertTrue(mod.show_viewport and mod.show_render)

    def test_same_count_reorder_is_detected(self):
        self.build()
        sort = self.sort_modifier()
        sort.show_viewport = False
        mod, cache = self.build()
        self.move(cache)
        original = self.geometry()
        sort.show_viewport = True
        result = self.geometry()
        self.assertEqual(len(result[0]), len(original[0]))
        self.assertEqual(result, self.expected_prefix(mod))
        self.assertIn('order changed', guard.check_input(bpy.context, self.obj, mod))
        sort.show_viewport = False
        self.assertEqual(self.geometry(), original)

    def test_loose_vertex_reorder_uses_origin_ids(self):
        mesh = bpy.data.meshes.new('Loose points')
        mesh.from_pydata([(0, 0, 0), (1, 0, 0), (3, 0, 0)], [], [])
        self.obj.data = mesh
        self.test_same_count_reorder_is_detected()

    def test_array_count_change_bypasses(self):
        array = self.obj.modifiers.new('Array', 'ARRAY')
        array.count = 2
        mod, cache = self.build()
        self.move(cache)
        original = self.geometry()
        array.count = 3
        self.assertEqual(self.geometry(), self.expected_prefix(mod))
        array.count = 2
        self.assertEqual(self.geometry(), original)

    def test_downstream_stages_also_pause(self):
        self.build()
        sub = self.obj.modifiers.new('Intermediate Subdivision', 'SUBSURF')
        sub.levels = 1
        middle, cache = self.build()
        self.move(cache)
        last, cache = self.build()
        self.move(cache)
        original = self.geometry()
        sub.show_viewport = False
        self.assertEqual(self.geometry(), self.expected_prefix(middle))
        self.assertIsNotNone(guard.check_input(bpy.context, self.obj, last))
        sub.show_viewport = True
        self.assertEqual(self.geometry(), original)

    def test_position_only_deformation_still_follows_upstream(self):
        deform = self.obj.modifiers.new('Deform', 'SIMPLE_DEFORM')
        deform.deform_method = 'TWIST'
        deform.angle = 0.0
        mod, cache = self.build()
        self.move(cache)
        deform.angle = 0.5
        self.assertIsNone(guard.check_input(bpy.context, self.obj, mod))
        expected = self.expected_prefix(mod)
        actual = self.geometry()
        for i, (a, b) in enumerate(zip(actual[0], expected[0])):
            self.assertAlmostEqual(a[2] - b[2], 0.3 if i == 0 else 0, places=5)
        self.assertEqual(actual[1:], expected[1:])

    def test_guard_works_without_addon_or_timer(self):
        sub = self.obj.modifiers.new('Subdivision', 'SUBSURF')
        sub.levels = 1
        mod, cache = self.build()
        self.move(cache)
        original = self.geometry()
        addon.unregister()
        try:
            sub.show_viewport = False
            self.assertEqual(len(self.geometry()[0]), 8)
            sub.show_viewport = True
            self.assertEqual(self.geometry(), original)
        finally:
            addon.register()

    def test_sync_does_not_write_to_cache_while_paused(self):
        sub = self.obj.modifiers.new('Subdivision', 'SUBSURF')
        sub.levels = 1
        mod, cache = self.build()
        self.move(cache)
        before = [tuple(v.co) for v in cache.data.vertices]
        sub.show_viewport = False
        success, message = addon.sync_upstream_to_cache(bpy.context, self.obj, cache, mod)
        self.assertFalse(success)
        self.assertIn('paused', message)
        self.assertEqual(before, [tuple(v.co) for v in cache.data.vertices])

    def test_disabling_guard_is_explicit(self):
        sub = self.obj.modifiers.new('Subdivision', 'SUBSURF')
        sub.levels = 1
        mod, cache = self.build()
        sub.show_viewport = False
        self.assertEqual(len(self.geometry()[0]), 8)
        addon.set_modifier_socket_value(mod, guard._socket(mod, guard.ENABLED), False)
        self.assertEqual(len(self.geometry()[0]), 26)
        self.assertIsNone(guard.check_input(bpy.context, self.obj, mod))

    def test_reference_is_independent_of_cache_edits(self):
        mod, cache = self.build()
        ref = guard.reference(mod)
        baseline = [tuple(v.co) for v in ref.data.vertices]
        self.move(cache)
        self.assertEqual([tuple(v.co) for v in ref.data.vertices], baseline)
        self.assertNotEqual(ref.data, cache.data)

    def test_mirror_toggle_restores(self):
        mirror = self.obj.modifiers.new('Mirror', 'MIRROR')
        mirror.use_mirror_merge = False
        mod, cache = self.build()
        self.move(cache)
        original = self.geometry()
        mirror.show_viewport = False
        self.assertEqual(self.geometry(), self.expected_prefix(mod))
        mirror.show_viewport = True
        self.assertEqual(self.geometry(), original)

    def test_missing_ids_and_reference_fail_closed(self):
        mod, cache = self.build()
        self.move(cache)
        self.obj.data.attributes.remove(self.obj.data.attributes[guard.ORIGIN_ID])
        self.assertEqual(self.geometry(), self.expected_prefix(mod))
        self.assertIn('missing', guard.check_input(bpy.context, self.obj, mod))
        guard.ensure_origin_ids(self.obj)
        addon.set_modifier_socket_value(mod, guard._socket(mod, guard.REFERENCE), None)
        self.assertEqual(self.geometry(), self.expected_prefix(mod))

    def test_empty_input_and_missing_reference_fail_closed(self):
        mod, cache = self.build()
        self.obj.data = bpy.data.meshes.new('Empty source')
        addon.set_modifier_socket_value(mod, guard._socket(mod, guard.REFERENCE), None)
        self.assertEqual(len(self.geometry()[0]), 0)

    def test_legacy_reference_registration_preserves_edit_geometry(self):
        mod, cache = self.build()
        self.move(cache)
        addon.set_modifier_socket_value(mod, guard._socket(mod, guard.ENABLED), False)
        self.obj.data.attributes.remove(self.obj.data.attributes[guard.ORIGIN_ID])
        cache.data.attributes.remove(cache.data.attributes[guard.ORIGIN_ID])
        before = [tuple(v.co) for v in cache.data.vertices]
        self.assertEqual(bpy.ops.edit_mesh_modifier.protect_topology(), {'FINISHED'})
        self.assertEqual(before, [tuple(v.co) for v in cache.data.vertices])
        self.assertIsNone(guard.check_input(bpy.context, self.obj, mod))
        self.assertEqual(self.geometry()[0], before)

    def test_paused_stage_cannot_be_exported_as_shape_key(self):
        from edit_mesh_modifier.shape_keys import export_shape_key
        mod, cache = self.build()
        ids = self.obj.data.attributes[guard.ORIGIN_ID]
        a, b = ids.data[0].value, ids.data[1].value
        ids.data[0].value, ids.data[1].value = b, a
        self.obj.data.update()
        with self.assertRaisesRegex(ValueError, 'paused'):
            export_shape_key(self.obj, mod, 'Invalid')
        self.assertIsNone(self.obj.data.shape_keys)


addon.register()
result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TopologyGuardTests))
addon.unregister()
if not result.wasSuccessful():
    raise RuntimeError('Topology protection tests failed')
