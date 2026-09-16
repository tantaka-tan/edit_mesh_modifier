"""Mode pie integration and a separately assignable cache-edit toggle."""

import bpy

_keymaps = []
_pie_hook = None
_registered = False
_auto_paused = False
_mode_states = {}


def _auto_enabled(context):
    entry = context.preferences.addons.get(__package__)
    return entry is None or entry.preferences.auto_edit_polygons


def _mode_state(context):
    obj = context.view_layer.objects.active
    return (context.scene.as_pointer(), context.view_layer.as_pointer(),
            obj.as_pointer() if obj else 0, obj.mode if obj else 'OBJECT')


def _remember_modes():
    _mode_states.clear()
    for window in bpy.context.window_manager.windows:
        with bpy.context.temp_override(window=window):
            _mode_states[window.as_pointer()] = _mode_state(bpy.context)


@bpy.app.handlers.persistent
def _pause_auto_edit(*args):
    global _auto_paused
    _auto_paused = True
    _mode_states.clear()


@bpy.app.handlers.persistent
def _resume_auto_edit(*args):
    global _auto_paused
    _remember_modes()
    _auto_paused = False


def _redirect_edit_entry(context, previous, current):
    # Only a newly entered Edit Mode in the same scene/view layer is eligible.
    # Cache editing, loading a scene in Edit Mode and undo restoration are not.
    if (previous is None or previous[:2] != current[:2]
            or previous[3] == 'EDIT' or current[3] != 'EDIT'
            or not _auto_enabled(context)):
        return False
    addon = _addon()
    source = context.object
    if (source is None or source.type != 'MESH' or editing_cache(context)
            or not addon._is_system_ready):
        return False
    mod = addon.get_target_modifier(source)
    cache = addon.get_modifier_socket_value(mod, addon.OBJ_SOCKET) if mod else None
    if cache is None or cache.type != 'MESH' or cache == source:
        return False
    # The existing edit operator exits source Edit Mode itself and owns the
    # whole cache session, including hiding/restoring the source and undo.
    try:
        result = bpy.ops.edit_mesh_modifier.edit('INVOKE_DEFAULT')
        if 'CANCELLED' not in result:
            return True
    except RuntimeError as error:
        print(f"Edit Poly: automatic edit entry failed: {error}")
    # Leave a failed attempt in the original edit mode, without retrying on
    # every tick. The caller records the resulting mode even after failure.
    if context.object == source and source.mode == 'OBJECT':
        bpy.ops.object.mode_set(mode='EDIT')
    return False


def _auto_edit_tick():
    if not _registered or not _auto_enabled(bpy.context):
        return None
    if _auto_paused:
        return 0.05
    windows = bpy.context.window_manager.windows
    live_windows = {window.as_pointer() for window in windows}
    for key in tuple(_mode_states):
        if key not in live_windows:
            del _mode_states[key]
    for window in windows:
        key = window.as_pointer()
        area = next((area for area in window.screen.areas if area.type == 'VIEW_3D'), None)
        if area is None:
            _mode_states.pop(key, None)
            continue
        region = next((region for region in area.regions if region.type == 'WINDOW'), None)
        if region is None:
            continue
        with bpy.context.temp_override(window=window, area=area, region=region):
            context = bpy.context
            previous = _mode_states.get(key)
            current = _mode_state(context)
            _mode_states[key] = current
            try:
                _redirect_edit_entry(context, previous, current)
            except (ReferenceError, RuntimeError) as error:
                print(f"Edit Poly: automatic edit entry skipped: {error}")
            finally:
                _mode_states[key] = _mode_state(context)
    return 0.05


def update_auto_edit(self, context):
    """Preference changes take effect at the next mode entry, not mid-edit."""
    if not _registered:
        return
    _remember_modes()
    active = bpy.app.timers.is_registered(_auto_edit_tick)
    if _auto_enabled(context):
        if not active:
            bpy.app.timers.register(_auto_edit_tick, first_interval=0.05, persistent=True)
    elif active:
        bpy.app.timers.unregister(_auto_edit_tick)


_auto_handlers = (
    (bpy.app.handlers.load_pre, _pause_auto_edit),
    (bpy.app.handlers.load_post, _resume_auto_edit),
    (bpy.app.handlers.undo_pre, _pause_auto_edit),
    (bpy.app.handlers.undo_post, _resume_auto_edit),
    (bpy.app.handlers.redo_pre, _pause_auto_edit),
    (bpy.app.handlers.redo_post, _resume_auto_edit),
)


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
    global _pie_hook, _registered, _auto_paused
    _registered = True
    _auto_paused = False
    for handlers, callback in _auto_handlers:
        if callback not in handlers:
            handlers.append(callback)
    # Add-on registration runs with Blender's restricted context. Establish
    # the baseline on the first UI tick, once normal scene access is available.
    _mode_states.clear()
    if not bpy.app.timers.is_registered(_auto_edit_tick):
        bpy.app.timers.register(_auto_edit_tick, first_interval=0.05, persistent=True)
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
    global _pie_hook, _registered
    _registered = False
    if bpy.app.timers.is_registered(_auto_edit_tick):
        bpy.app.timers.unregister(_auto_edit_tick)
    for handlers, callback in _auto_handlers:
        if callback in handlers:
            handlers.remove(callback)
    _mode_states.clear()
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
