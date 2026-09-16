"""Mode pie integration and a separately assignable cache-edit toggle."""

import bpy

_keymaps = []
_pie_hook = None


def _addon():
    import sys
    return sys.modules[__package__]


def editing_cache(context):
    """Recognize the cache even though the source is hidden during editing."""
    obj = context.object
    if context.mode != 'EDIT_MESH' or obj is None:
        return False
    addon = _addon()
    for source in bpy.data.objects:
        for mod in source.modifiers:
            if (mod.type == 'NODES' and mod.node_group
                    and mod.node_group.name == addon.NG_EDIT
                    and addon.get_modifier_socket_value(mod, addon.OBJ_SOCKET) == obj):
                return True
    return False


class EDIT_MESH_MODIFIER_OT_ToggleEdit(bpy.types.Operator):
    bl_idname = "edit_mesh_modifier.toggle_edit"
    bl_label = "Edit Poly: Toggle Edit Mode"
    bl_description = "Edit the selected Edit Poly modifier, or finish editing its cache"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        if not context.area or context.area.type != 'VIEW_3D':
            cls.poll_message_set("Use this command in the 3D Viewport")
            return False
        if editing_cache(context):
            return True
        addon = _addon()
        obj = context.object
        mod = addon.get_target_modifier(obj) if obj and obj.type == 'MESH' else None
        cache = addon.get_modifier_socket_value(mod, addon.OBJ_SOCKET) if mod else None
        if context.mode != 'OBJECT' or cache is None or cache.type != 'MESH':
            cls.poll_message_set("Select an Edit Poly modifier in Object Mode first")
            return False
        return True

    def execute(self, context):
        if editing_cache(context):
            # The existing Edit operator's timer restores attributes, visibility,
            # and selection. Keep one owner of the edit-session cleanup.
            return bpy.ops.object.mode_set(mode='OBJECT')
        result = bpy.ops.edit_mesh_modifier.edit('INVOKE_DEFAULT')
        return {'CANCELLED'} if 'CANCELLED' in result else {'FINISHED'}


class _LayoutProxy:
    def __init__(self, layout):
        self._layout = layout
        self.pies = []

    def __getattr__(self, name):
        return getattr(self._layout, name)

    def menu_pie(self):
        pie = self._layout.menu_pie()
        self.pies.append(pie)
        return pie


class _MenuProxy:
    def __init__(self, menu):
        self._menu = menu
        self.layout = _LayoutProxy(menu.layout)

    def __getattr__(self, name):
        return getattr(self._menu, name)


def _placeholder(self, context):
    pass


def register():
    global _pie_hook
    menu = bpy.types.VIEW3D_MT_object_mode_pie
    # append initializes Blender's shared callback list. A second menu_pie()
    # would overlap the existing radial buttons, so wrap only the native draw
    # and append to its actual pie. Other add-ons' callbacks remain untouched.
    menu.append(_placeholder)
    menu.remove(_placeholder)
    draw_funcs = menu.draw._draw_funcs
    for index, original in enumerate(draw_funcs):
        if original.__qualname__ != 'VIEW3D_MT_object_mode_pie.draw':
            continue

        def draw_with_edit_poly(self, context):
            proxy = _MenuProxy(self)
            original(proxy, context)
            entry = context.preferences.addons.get(__package__)
            enabled = entry is None or entry.preferences.show_in_mode_pie
            if enabled and proxy.layout.pies and EDIT_MESH_MODIFIER_OT_ToggleEdit.poll(context):
                proxy.layout.pies[0].operator(
                    EDIT_MESH_MODIFIER_OT_ToggleEdit.bl_idname,
                    text="Finish Edit Poly" if editing_cache(context) else "Edit Poly",
                    icon='EDITMODE_HLT')

        draw_funcs[index] = draw_with_edit_poly
        _pie_hook = (draw_funcs, draw_with_edit_poly, original)
        break

    kc = bpy.context.window_manager.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
        kmi = km.keymap_items.new(EDIT_MESH_MODIFIER_OT_ToggleEdit.bl_idname, 'NONE', 'PRESS')
        _keymaps.append((km, kmi))


def unregister():
    global _pie_hook
    if _pie_hook:
        draw_funcs, wrapper, original = _pie_hook
        if wrapper in draw_funcs:
            draw_funcs[draw_funcs.index(wrapper)] = original
        _pie_hook = None
    for km, kmi in _keymaps:
        km.keymap_items.remove(kmi)
    _keymaps.clear()


def draw_preferences(layout, context):
    import rna_keymap_ui
    box = layout.box()
    box.label(text="Edit Poly Shortcut", icon='KEYINGSET')
    box.label(text="Assign a key to start or finish Edit Poly editing")
    # Display the user override so Blender persists customized key assignments.
    for kc in (context.window_manager.keyconfigs.user, context.window_manager.keyconfigs.addon):
        if kc is None:
            continue
        km = kc.keymaps.get('3D View')
        if km:
            for kmi in km.keymap_items:
                if kmi.idname == EDIT_MESH_MODIFIER_OT_ToggleEdit.bl_idname:
                    rna_keymap_ui.draw_kmi([], kc, km, kmi, box, 0)
                    return
