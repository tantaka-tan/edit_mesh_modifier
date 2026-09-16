"""Experimental, synchronous topology validation before indexed cache edits."""

from contextlib import contextmanager
import sys

import bpy

ORIGIN_ID = '.edit_poly_origin_id'
REFERENCE = 'Protection Reference'
ENABLED = 'Topology Protection (Experimental)'
MARKER = '_edit_poly_guard_version'


def _addon():
    return sys.modules[__package__]


def paused_message(reason):
    return _addon()._i18n.pget_tmpl('Edit Poly paused: {reason}', reason=reason)


def _socket(mod, name):
    group = mod.node_group
    return next((item.identifier for item in group.interface.items_tree
                 if item.item_type == 'SOCKET' and item.in_out == 'INPUT' and item.name == name), None)


def reference(mod):
    key = _socket(mod, REFERENCE)
    return _addon().get_modifier_socket_value(mod, key) if key else None


def enabled(mod):
    key = _socket(mod, ENABLED)
    return bool(key and _addon().get_modifier_socket_value(mod, key))


def install_nodes(group):
    """Wrap the original output; old stages remain opt-in until bound."""
    if group.get(MARKER) == 1:
        return
    output = next(n for n in group.nodes if n.type == 'GROUP_OUTPUT' and n.is_active_output)
    original = output.inputs['Geometry'].links[0].from_socket
    ref_socket = group.interface.new_socket(name=REFERENCE, in_out='INPUT', socket_type='NodeSocketObject')
    ref_socket.hide_in_modifier = True
    flag = group.interface.new_socket(name=ENABLED, in_out='INPUT', socket_type='NodeSocketBool')
    flag.default_value = False
    frame = group.nodes.new('NodeFrame')
    frame.label = 'Experimental topology protection'

    def node(kind):
        n = group.nodes.new(kind)
        n.parent = frame
        return n

    link = group.links.new
    inp = node('NodeGroupInput')
    incoming = inp.outputs['Geometry']
    obj = node('GeometryNodeObjectInfo')
    link(inp.outputs[REFERENCE], obj.inputs['Object'])
    baseline = obj.outputs['Geometry']
    index = node('GeometryNodeInputIndex').outputs['Index']

    def different(a, b):
        n = node('FunctionNodeCompare')
        n.data_type = 'INT'
        n.operation = 'NOT_EQUAL'
        link(a, next(s for s in n.inputs if s.name == 'A' and s.type == 'INT'))
        link(b, next(s for s in n.inputs if s.name == 'B' and s.type == 'INT'))
        return n.outputs['Result']

    def combine(values, operation='OR'):
        result = values[0]
        for value in values[1:]:
            n = node('FunctionNodeBooleanMath')
            n.operation = operation
            link(result, n.inputs[0])
            link(value, n.inputs[1])
            result = n.outputs[0]
        return result

    def sample(field, domain):
        n = node('GeometryNodeSampleIndex')
        n.data_type = 'INT'
        n.domain = domain
        n.clamp = False
        link(baseline, n.inputs['Geometry'])
        link(field, n.inputs['Value'])
        link(index, n.inputs['Index'])
        return n.outputs['Value']

    def any_mismatch(fields, domain):
        n = node('GeometryNodeAttributeStatistic')
        n.data_type = 'FLOAT'
        n.domain = domain
        link(incoming, n.inputs['Geometry'])
        link(combine([different(f, sample(f, domain)) for f in fields]), n.inputs['Attribute'])
        return n.outputs['Max']

    sizes = []
    for geometry in (incoming, baseline):
        n = node('GeometryNodeAttributeDomainSize')
        n.component = 'MESH'
        link(geometry, n.inputs['Geometry'])
        sizes.append(n)
    checks = [different(sizes[0].outputs[name], sizes[1].outputs[name])
              for name in ('Point Count', 'Edge Count', 'Face Count', 'Face Corner Count')]
    scale = node('ShaderNodeVectorMath')
    scale.operation = 'LENGTH'
    link(obj.outputs['Scale'], scale.inputs[0])
    missing = node('FunctionNodeBooleanMath')
    missing.operation = 'NOT'
    link(scale.outputs['Value'], missing.inputs[0])
    checks.append(missing.outputs[0])
    ids = node('GeometryNodeInputNamedAttribute')
    ids.data_type = 'INT'
    ids.inputs['Name'].default_value = ORIGIN_ID
    checks.append(any_mismatch([ids.outputs['Attribute']], 'POINT'))
    # Zero means missing/invalid origin data. Generated/interpolated IDs are
    # additional evidence, not a universal identity guarantee (see README).
    valid_id = node('FunctionNodeCompare')
    valid_id.data_type = 'INT'
    valid_id.operation = 'LESS_EQUAL'
    link(ids.outputs['Attribute'], next(s for s in valid_id.inputs if s.name == 'A' and s.type == 'INT'))
    invalid = node('GeometryNodeAttributeStatistic')
    invalid.domain = 'POINT'
    link(incoming, invalid.inputs['Geometry'])
    link(valid_id.outputs['Result'], invalid.inputs['Attribute'])
    checks.append(invalid.outputs['Max'])
    edges = node('GeometryNodeInputMeshEdgeVertices')
    checks.append(any_mismatch([edges.outputs['Vertex Index 1'], edges.outputs['Vertex Index 2']], 'EDGE'))
    vertex = node('GeometryNodeVertexOfCorner')
    face = node('GeometryNodeFaceOfCorner')
    link(index, vertex.inputs['Corner Index'])
    link(index, face.inputs['Corner Index'])
    checks.append(any_mismatch([vertex.outputs['Vertex Index'], face.outputs['Face Index']], 'CORNER'))
    switch = node('GeometryNodeSwitch')
    switch.input_type = 'GEOMETRY'
    link(combine([inp.outputs[ENABLED], combine(checks)], 'AND'), switch.inputs['Switch'])
    link(original, switch.inputs['False'])
    link(incoming, switch.inputs['True'])
    link(switch.outputs['Output'], output.inputs['Geometry'])
    group[MARKER] = 1


def ensure_origin_ids(obj):
    attr = obj.data.attributes.get(ORIGIN_ID)
    if attr is None:
        attr = obj.data.attributes.new(ORIGIN_ID, 'INT', 'POINT')
        attr.data.foreach_set('value', range(1, len(obj.data.vertices) + 1))
        obj.data.update()
    elif attr.domain != 'POINT' or attr.data_type != 'INT':
        raise ValueError('The Edit Poly origin ID attribute has an incompatible type.')
    else:
        next_id = max((item.value for item in attr.data), default=0) + 1
        for item in attr.data:
            if item.value <= 0:
                item.value = next_id
                next_id += 1


@contextmanager
def upstream_mesh(context, source, modifier):
    addon = _addon()
    ready = addon._is_system_ready
    clone = evaluated = mesh = None
    try:
        addon._is_system_ready = False
        index = source.modifiers.find(modifier.name)
        if index < 0:
            raise ValueError('Edit Poly modifier does not belong to this object')
        clone = source.copy()
        for stage in list(clone.modifiers)[index:]:
            clone.modifiers.remove(stage)
        context.scene.collection.objects.link(clone)
        clone.hide_viewport = False
        clone.hide_set(False)
        graph = context.evaluated_depsgraph_get()
        graph.update()
        evaluated = clone.evaluated_get(graph)
        mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=graph)
        yield mesh
    finally:
        if evaluated is not None:
            evaluated.to_mesh_clear()
        if clone is not None:
            bpy.data.objects.remove(clone, do_unlink=True)
        addon._is_system_ready = ready


def bind_mesh(modifier, mesh):
    install_nodes(modifier.node_group)
    copied = mesh.copy()
    ref = bpy.data.objects.new('.Edit Poly Protection Reference', copied)
    if copied.shape_keys:
        ref.shape_key_clear()
    old = reference(modifier)
    addon = _addon()
    addon.set_modifier_socket_value(modifier, _socket(modifier, REFERENCE), ref)
    addon.set_modifier_socket_value(modifier, _socket(modifier, ENABLED), True)
    remove_unused_reference(old)


def remove_unused_reference(old):
    if old is not None and old.users == 0:
        old_mesh = old.data
        bpy.data.objects.remove(old)
        if old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)


def mismatch(mesh, baseline):
    if (len(mesh.vertices), len(mesh.edges), len(mesh.polygons), len(mesh.loops)) != (
            len(baseline.vertices), len(baseline.edges), len(baseline.polygons), len(baseline.loops)):
        return 'Vertex, edge or face counts changed'
    a, b = mesh.attributes.get(ORIGIN_ID), baseline.attributes.get(ORIGIN_ID)
    if len(mesh.vertices) and (a is None or b is None or a.data_type != 'INT' or b.data_type != 'INT'
                              or a.domain != 'POINT' or b.domain != 'POINT'):
        return 'Vertex origin IDs are missing'
    if a and b and any(x.value <= 0 or x.value != y.value for x, y in zip(a.data, b.data)):
        return 'Vertex origin IDs or their order changed'
    if any(tuple(a.vertices) != tuple(b.vertices) for a, b in zip(mesh.edges, baseline.edges)):
        return 'Edge connectivity or order changed'
    if any(tuple(a.vertices) != tuple(b.vertices) for a, b in zip(mesh.polygons, baseline.polygons)):
        return 'Face connectivity or order changed'
    return None


def check_input(context, source, modifier):
    if not enabled(modifier):
        return None
    ref = reference(modifier)
    if ref is None or ref.type != 'MESH':
        return 'Protection reference is missing'
    with upstream_mesh(context, source, modifier) as mesh:
        return mismatch(mesh, ref.data)


class EDIT_MESH_MODIFIER_OT_ProtectTopology(bpy.types.Operator):
    bl_idname = 'edit_mesh_modifier.protect_topology'
    bl_label = 'Register Protection Reference'
    bl_description = 'Record the current upstream topology as correct without rebuilding or changing your edit cache'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and _addon().get_target_modifier(context.object) is not None

    def execute(self, context):
        addon = _addon()
        source = context.object
        mod = addon.get_target_modifier(source)
        try:
            ensure_origin_ids(source)
            with upstream_mesh(context, source, mod) as mesh:
                cache = addon.get_modifier_socket_value(mod, addon.OBJ_SOCKET)
                # Legacy caches predate origin IDs. Seed them using their saved
                # correspondence, only on this explicit registration operation.
                if cache and ORIGIN_ID not in cache.data.attributes:
                    upstream_ids = mesh.attributes.get(ORIGIN_ID)
                    index = cache.data.attributes.get(addon.ATTR_IDX)
                    base = cache.data.attributes.get(addon.ATTR_BASE)
                    values = [item.value for item in upstream_ids.data] if upstream_ids else []
                    mapped = [item.value for item in index.data] if index else []
                    bases = [item.value for item in base.data] if base else []
                    ensure_origin_ids(cache)
                    ids = cache.data.attributes[ORIGIN_ID]
                    for i, target in enumerate(mapped):
                        if bases[i] and 0 <= target < len(values):
                            ids.data[i].value = values[target]
                bind_mesh(mod, mesh)
            self.report({'INFO'}, addon._i18n.pget_tmpl('Protection reference registered; edit cache preserved'))
            return {'FINISHED'}
        except (ValueError, RuntimeError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}


class EDIT_MESH_MODIFIER_OT_CheckTopology(bpy.types.Operator):
    bl_idname = 'edit_mesh_modifier.check_topology'
    bl_label = 'Check Input Compatibility'
    bl_description = 'Check whether this Edit Poly is currently passing its input through'

    @classmethod
    def poll(cls, context):
        return EDIT_MESH_MODIFIER_OT_ProtectTopology.poll(context)

    def execute(self, context):
        mod = _addon().get_target_modifier(context.object)
        if not enabled(mod):
            self.report({'INFO'}, _addon()._i18n.pget_tmpl('Topology protection is not enabled'))
        else:
            error = check_input(context, context.object, mod)
            self.report({'WARNING'} if error else {'INFO'},
                        paused_message(error) if error else _addon()._i18n.pget_tmpl('Edit Poly input matches the protection reference'))
        return {'FINISHED'}


def draw(layout, context, modifier):
    box = layout.box()
    box.label(text='Topology Protection (Experimental)', icon='SHIELD')
    if reference(modifier):
        _addon().draw_socket_input(box, modifier, _socket(modifier, ENABLED), text='Enable Topology Protection')
        box.operator(EDIT_MESH_MODIFIER_OT_CheckTopology.bl_idname)
    else:
        box.label(text='No protection reference registered', icon='INFO')
    box.operator(EDIT_MESH_MODIFIER_OT_ProtectTopology.bl_idname)
    box.label(text='Register only while the upstream configuration is correct')
