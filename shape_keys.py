"""Bake the enabled viewport stack through Edit Poly into a relative shape key."""

import math
import sys
from collections import Counter

import bpy

from . import translation as i18n


def _fail(message):
    raise ValueError(i18n.pget_tmpl(message))


def _face_cycle(vertices):
    """Ignore the starting corner, but preserve winding."""
    vertices = tuple(vertices)
    start = vertices.index(min(vertices))
    return vertices[start:] + vertices[:start]


def _check_topology(src, mesh, ids):
    if len(mesh.vertices) != len(src.vertices):
        _fail("Shape keys require the same vertex count as the source mesh.")
    source_edges = Counter(tuple(sorted(edge.vertices)) for edge in src.edges)
    cache_edges = Counter(tuple(sorted(ids[v] for v in edge.vertices)) for edge in mesh.edges)
    source_faces = Counter(_face_cycle(face.vertices) for face in src.polygons)
    cache_faces = Counter(_face_cycle(ids[v] for v in face.vertices) for face in mesh.polygons)
    if source_edges != cache_edges or source_faces != cache_faces:
        _fail("Edges or faces differ from the source mesh; only vertex position edits can be exported.")


def cache_vertex_map(obj, cache, upstream_map=None):
    """Compose cache -> preceding output -> source vertex correspondence."""
    from . import ATTR_BASE, ATTR_IDX, ATTR_POS

    if cache is None or cache.type != 'MESH' or cache.mode != 'OBJECT':
        _fail("The modifier has no valid cache object. Run Build first")
    src, mesh = obj.data, cache.data
    count = len(src.vertices)
    if not count or len(mesh.vertices) != count:
        _fail("Shape keys require the same vertex count as the source mesh.")
    attrs = [mesh.attributes.get(name) for name in (ATTR_BASE, ATTR_IDX, ATTR_POS)]
    for attr, kind in zip(attrs, ('BOOLEAN', 'INT', 'FLOAT_VECTOR')):
        if attr is None or attr.domain != 'POINT' or attr.data_type != kind or len(attr.data) != count:
            _fail("The cache has no valid vertex correspondence. Rebuild before editing.")
    base, index, _position = attrs
    ids = [item.value for item in index.data]
    if not all(item.value for item in base.data) or sorted(ids) != list(range(count)):
        _fail("The cache contains new or unmapped vertices; it cannot become a shape key.")
    if upstream_map is None:
        upstream_map = tuple(range(count))
    ids = tuple(upstream_map[index] for index in ids)

    _check_topology(src, mesh, ids)
    return ids


# These built-in modifiers preserve vertex identity. Edit Poly stages are
# checked individually; unknown Geometry Nodes and generators are still rejected.
_IDENTITY_MODIFIERS = {
    'ARMATURE', 'CAST', 'CURVE', 'DISPLACE', 'HOOK', 'LATTICE',
    'MESH_DEFORM', 'SHRINKWRAP', 'SIMPLE_DEFORM', 'SMOOTH',
    'CORRECTIVE_SMOOTH', 'LAPLACIANSMOOTH', 'LAPLACIANDEFORM',
    'SURFACE_DEFORM', 'WARP', 'WAVE', 'NORMAL_EDIT', 'WEIGHTED_NORMAL',
    'UV_PROJECT', 'UV_WARP', 'VERTEX_WEIGHT_EDIT', 'VERTEX_WEIGHT_MIX',
    'VERTEX_WEIGHT_PROXIMITY', 'DATA_TRANSFER',
}


def _enabled_prefix(obj, modifier):
    """Viewport visibility alone determines the snapshot, including its boundary."""
    enabled = []
    for stage in obj.modifiers:
        if stage.show_viewport:
            enabled.append(stage)
        if stage == modifier:
            return enabled
    _fail("Please select an Edit Poly modifier first")


def _prefix_vertex_map(obj, enabled):
    from . import NG_EDIT, OBJ_SOCKET, get_modifier_socket_value

    mapping = tuple(range(len(obj.data.vertices)))
    for upstream in enabled:
        if upstream.type == 'NODES' and upstream.node_group and upstream.node_group.name == NG_EDIT:
            cache = get_modifier_socket_value(upstream, OBJ_SOCKET)
            mapping = cache_vertex_map(obj, cache, mapping)
        elif upstream.type not in _IDENTITY_MODIFIERS:
            raise ValueError(i18n.pget_tmpl(
                "Cannot verify vertex identity through upstream modifier: {name}", name=upstream.name))
    return mapping


def stack_offsets(obj, modifier):
    """Evaluate a temporary object; never change the live modifier stack.

    Subtract the current shape-key mix so enabling the result alongside existing
    keys reproduces the captured shape instead of adding that mix twice.
    """
    enabled = _enabled_prefix(obj, modifier)
    mapping = _prefix_vertex_map(obj, enabled)
    addon = sys.modules[__package__]
    from . import topology_guard
    for stage in enabled:
        if stage.type == 'NODES' and stage.node_group and stage.node_group.name == addon.NG_EDIT:
            reason = topology_guard.check_input(bpy.context, obj, stage)
            if reason:
                _fail(topology_guard.paused_message(reason))
    was_ready = addon._is_system_ready
    temporary = None
    try:
        addon._is_system_ready = False  # Do not fork caches for our temporary copy.
        temporary = obj.copy()
        retained = {stage.name for stage in enabled}
        for stage in list(temporary.modifiers):
            if stage.name not in retained:
                temporary.modifiers.remove(stage)
        # The shared source mesh is read-only throughout this evaluation.
        bpy.context.scene.collection.objects.link(temporary)
        temporary.hide_viewport = False
        temporary.hide_set(False)

        def read_coordinates(vertex_map):
            graph = bpy.context.evaluated_depsgraph_get()
            graph.update()
            evaluated = temporary.evaluated_get(graph)
            mesh = evaluated.to_mesh()
            try:
                if mesh is None:
                    _fail("The cache contains invalid coordinates.")
                _check_topology(obj.data, mesh, vertex_map)
                return [vertex.co.copy() for vertex in mesh.vertices]
            finally:
                evaluated.to_mesh_clear()

        result = read_coordinates(mapping)
        temporary.modifiers.clear()
        baseline = read_coordinates(tuple(range(len(obj.data.vertices))))
        offsets = [None] * len(mapping)
        for index, source_index in enumerate(mapping):
            delta = result[index] - baseline[source_index]
            if not all(math.isfinite(value) for value in delta):
                _fail("The cache contains invalid coordinates.")
            offsets[source_index] = delta
        return offsets, enabled
    finally:
        try:
            if temporary is not None:
                bpy.data.objects.remove(temporary, do_unlink=True)
        finally:
            addon._is_system_ready = was_ready


def export_shape_key(obj, modifier, name, keep_modifier=True):
    from . import NG_EDIT, OBJ_SOCKET, get_modifier_socket_value, _remove_cache_object
    from . import topology_guard

    if obj.type != 'MESH' or obj.mode != 'OBJECT':
        _fail("Switch the source mesh to Object Mode first.")
    if not obj.is_editable or not obj.data.is_editable or obj.data.users != 1:
        _fail("The source mesh must be editable and single-user.")
    if modifier is None or modifier.type != 'NODES' or not modifier.node_group or modifier.node_group.name != NG_EDIT:
        _fail("Please select an Edit Poly modifier first")
    keys = obj.data.shape_keys
    if keys and (not keys.use_relative or not keys.is_editable):
        _fail("Only editable relative shape keys are supported.")
    if not keep_modifier and obj.show_only_shape_key:
        _fail("Unpin the active shape key before applying the snapshot.")
    offsets, enabled = stack_offsets(obj, modifier)
    if keys and any(len(block.data) != len(offsets) for block in keys.key_blocks):
        _fail("Existing shape keys do not match the source vertex count.")

    old_active = obj.active_shape_key_index
    basis_created = None
    key = None
    saved_states = []
    removed_cache = None
    removed_reference = None
    try:
        if keys is None:
            basis_created = obj.shape_key_add(name="Basis", from_mix=False)
        basis = obj.data.shape_keys.reference_key
        key = obj.shape_key_add(name=name.strip() or modifier.name, from_mix=False)
        key.relative_key = basis
        coordinates = [component for point, delta in zip(basis.data, offsets) for component in point.co + delta]
        key.data.foreach_set('co', coordinates)
        key.value = 0.0 if keep_modifier else 1.0
        obj.data.update()
        # Remove the modifier only after all key writes succeeded.
        if not keep_modifier:
            for stage in enabled:
                if stage != modifier:
                    saved_states.append((stage, stage.show_viewport, stage.show_render))
                    stage.show_viewport = False
                    stage.show_render = False
            if modifier in enabled:
                removed_cache = get_modifier_socket_value(modifier, OBJ_SOCKET)
                removed_reference = topology_guard.reference(modifier)
                obj.modifiers.remove(modifier)
    except Exception:
        for stage, viewport, render in saved_states:
            stage.show_viewport = viewport
            stage.show_render = render
        if key is not None:
            obj.shape_key_remove(key)
        if basis_created is not None:
            obj.shape_key_remove(basis_created)
        obj.active_shape_key_index = old_active
        raise
    # A saved key starts at zero so saving cannot double the visible edit.
    obj.active_shape_key_index = old_active
    if removed_cache is not None:
        _remove_cache_object(removed_cache)
    topology_guard.remove_unused_reference(removed_reference)
    return key


class EDIT_MESH_MODIFIER_OT_ShapeKey(bpy.types.Operator):
    bl_idname = "edit_mesh_modifier.shape_key"
    bl_label = "Edit Poly to Shape Key"
    bl_description = "Save the evaluated viewport result through this Edit Poly as a shape key; disabled modifiers are ignored"
    bl_options = {'REGISTER', 'UNDO'}

    modifier_name: bpy.props.StringProperty(options={'HIDDEN'})
    key_name: bpy.props.StringProperty(name="Name", default="Edit Poly")
    keep_modifier: bpy.props.BoolProperty(name="Keep Modifier", default=True)

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == 'MESH' and context.object.mode == 'OBJECT'

    def invoke(self, context, event):
        from . import get_target_modifier
        modifier = context.object.modifiers.get(self.modifier_name) if self.modifier_name else get_target_modifier(context.object)
        if modifier is None:
            self.report({'ERROR'}, i18n.pget_tmpl("Please select an Edit Poly modifier first"))
            return {'CANCELLED'}
        self.modifier_name = modifier.name
        self.key_name = modifier.name
        return context.window_manager.invoke_props_dialog(self, width=520)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, 'key_name')
        layout.prop(self, 'keep_modifier')
        layout.label(text=i18n.pget_tmpl("Saves the final viewport shape through the selected Edit Poly."), translate=False)
        layout.label(text=i18n.pget_tmpl("Disabled modifiers are ignored. Topology changes are not supported."), translate=False)
        if self.keep_modifier:
            layout.label(text=i18n.pget_tmpl("The key starts at 0. Disable the captured modifiers before using it."), translate=False)
        else:
            layout.label(text=i18n.pget_tmpl("Apply disables captured upstream modifiers and removes the selected enabled stage."), translate=False)

    def execute(self, context):
        from . import get_target_modifier
        obj = context.object
        modifier = obj.modifiers.get(self.modifier_name) if self.modifier_name else get_target_modifier(obj)
        try:
            key = export_shape_key(obj, modifier, self.key_name, self.keep_modifier)
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        self.report({'INFO'}, i18n.pget_tmpl("Created shape key: {name}", name=key.name))
        return {'FINISHED'}


def draw_shape_key_actions(layout, modifier):
    for keep, label in ((True, "Save as Shape Key"), (False, "Apply as Shape Key")):
        op = layout.operator(EDIT_MESH_MODIFIER_OT_ShapeKey.bl_idname, text=label, icon='SHAPEKEY_DATA')
        op.modifier_name = modifier.name
        op.keep_modifier = keep


class EDIT_MESH_MODIFIER_MT_ShapeKey(bpy.types.Menu):
    bl_label = "Shape Keys"

    def draw(self, context):
        from . import get_target_modifier
        modifier = get_target_modifier(context.object)
        if modifier:
            draw_shape_key_actions(self.layout, modifier)
