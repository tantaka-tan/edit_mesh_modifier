"""Undo-restorable edit ownership. Persistent records contain no Python RNA refs."""

import json
import sys
import uuid

import bpy

RECORD = '_edit_poly_session'
TOKEN = '_edit_poly_session_token'
ARCHIVE = '_edit_poly_session_archive'
OWNER = '_edit_poly_session_owner'
_paused = False
_registered = False
_busy = False
_epoch = 0
_started = {}


def _addon():
    return sys.modules[__package__]


def capture(session, context):
    token = uuid.uuid4().hex
    source, edit = session._src_obj, session._cache_obj
    if OWNER not in source:
        source[OWNER] = uuid.uuid4().hex
    overlays = []
    for space, value in session._overlay_states:
        for screen in bpy.data.screens:
            for index, area in enumerate(screen.areas):
                if area.spaces.active == space:
                    overlays.append((screen.name, index, value))
    record = dict(token=token, owner=source[OWNER], scene=context.scene.name, layer=context.view_layer.name,
                  hidden=session._src_hidden, display=session._cache_display_state,
                  render=edit.hide_render,
                  symmetry=session._cache_symmetry_state, overlays=overlays,
                  snapshot=session._snapshot, preview=session._preview_obj is not None)
    edit[TOKEN] = token
    encoded = json.dumps(record)
    source[RECORD] = encoded
    edit[ARCHIVE] = encoded
    raw = _addon().edit_preview.raw_cache(edit) or edit
    raw[ARCHIVE] = encoded
    session._session_token = token
    _started[token] = _epoch
    return token


def records():
    for source in bpy.data.objects:
        value = source.get(RECORD)
        if isinstance(value, str):
            try:
                record = json.loads(value)
                if isinstance(record, dict) and record.get('token'):
                    yield source, record
            except (ValueError, TypeError):
                pass


def resolve(token):
    owners = [(source, record) for source, record in records() if record['token'] == token]
    if len(owners) != 1:
        return None
    edits = [obj for obj in bpy.data.objects if obj.get(TOKEN) == token]
    if len(edits) > 1:
        return None
    return (*owners[0], edits[0] if edits else None)


class _RecoveredSession:
    def _restore_source_visibility(self):
        # All references are freshly resolved within this single synchronous call.
        self._src_obj.hide_set(self._src_hidden, view_layer=self._src_view_layer)


def _restore_edit_record(context):
    """Mesh-only undo may restore Edit Mode without restoring source ID props."""
    edit = context.object
    if context.mode != 'EDIT_MESH' or edit is None:
        return
    token = edit.get(TOKEN)
    if token and resolve(token) is not None:
        return
    addon = _addon()
    raw = addon.edit_preview.raw_cache(edit) or edit
    encoded = edit.get(ARCHIVE) or raw.get(ARCHIVE)
    if not isinstance(encoded, str):
        return
    record = json.loads(encoded)
    owners = []
    for source in bpy.data.objects:
        if source.get(OWNER) != record['owner']:
            continue
        if any(mod.type == 'NODES' and mod.node_group and mod.node_group.name == addon.NG_EDIT
               and addon.get_modifier_socket_value(mod, addon.OBJ_SOCKET) == raw
               for mod in source.modifiers):
            owners.append(source)
    if len(owners) == 1 and RECORD not in owners[0]:
        owners[0][RECORD] = encoded
        edit[TOKEN] = record['token']


def finish(token, context, push_undo=False):
    if _paused:
        return False
    resolved = resolve(token)
    if resolved is None:
        return False
    source, record, edit = resolved
    scene = bpy.data.scenes.get(record['scene'])
    layer = scene.view_layers.get(record['layer']) if scene else None
    if layer is None or source.name not in layer.objects:
        return False  # Keep ownership/visibility information until recovery succeeds.
    if _started.get(token) != _epoch:
        # Mesh undo steps can refer to a linked object from an earlier memfile
        # step. Deleting/unlinking it during history traversal breaks later redo.
        # Park it invisibly until Blender restores a completed state, or a new
        # explicit edit entry starts a new history branch.
        if edit is not None and edit.mode == 'EDIT':
            return False
        if source.hide_get(view_layer=layer) != record['hidden']:
            source.hide_set(record['hidden'], view_layer=layer)
        if edit is not None and edit.name in layer.objects:
            if not edit.hide_get(view_layer=layer):
                edit.hide_set(True, view_layer=layer)
            if not edit.hide_render:
                edit.hide_render = True
            if layer.objects.active == edit:
                layer.objects.active = source
                source.select_set(True, view_layer=layer)
        if not record.get('parked'):
            addon = _addon()
            if edit is not None:
                addon._set_edit_symmetry(source, addon._get_edit_symmetry(edit))
            for screen_name, index, value in record['overlays']:
                screen = bpy.data.screens.get(screen_name)
                if screen and index < len(screen.areas) and screen.areas[index].type == 'VIEW_3D':
                    screen.areas[index].spaces.active.overlay.show_retopology = value
            record['parked'] = True
            source[RECORD] = json.dumps(record)
        return True
    addon = _addon()
    session = _RecoveredSession()
    session._src_obj, session._cache_obj = source, edit
    session._src_hidden, session._src_view_layer = record['hidden'], layer
    session._cache_display_state = record['display']
    session._cache_symmetry_state = record['symmetry']
    session._symmetry_started = True
    session._preview_obj = edit if record['preview'] else None
    session._snapshot = tuple(record['snapshot']) if record['snapshot'] else None
    session._suppress_undo = True
    session._timer = None
    session._overlay_states = []
    for screen_name, index, value in record['overlays']:
        screen = bpy.data.screens.get(screen_name)
        if screen and index < len(screen.areas) and screen.areas[index].type == 'VIEW_3D':
            session._overlay_states.append((screen.areas[index].spaces.active, value))
    # Do not let a late session completion end another object's edit session.
    if context.mode != 'OBJECT' and context.object != edit:
        return False
    with context.temp_override(scene=scene, view_layer=layer):
        if edit is not None:
            edit.hide_render = record['render']
            if edit.name in layer.objects:
                edit.hide_set(False, view_layer=layer)
        addon.EDIT_MESH_MODIFIER_OT_Edit._cleanup_data(session, bpy.context)
    if source.hide_get(view_layer=layer) != record['hidden']:
        return False
    if edit is not None and not record['preview'] and TOKEN in edit:
        del edit[TOKEN]
    del source[RECORD]
    can_push = push_undo and _started.get(token) == _epoch
    _started.pop(token, None)
    if can_push:
        bpy.ops.ed.undo_push(message='Exit Edit Poly')
    return True


def prepare(context, source):
    """Explicit new entry starts a new history branch; discard parked displays."""
    value = source.get(RECORD)
    if isinstance(value, str):
        record = json.loads(value)
        _started[record['token']] = _epoch
        if not finish(record['token'], context):
            raise RuntimeError('Previous Edit Poly session could not be closed')


def reconcile(context=None):
    global _busy
    if _paused or _busy:
        return
    context = context or bpy.context
    _busy = True
    try:
        _restore_edit_record(context)
        for token in [r['token'] for _, r in records()]:
            resolved = resolve(token)
            if resolved is None:
                continue
            source, record, edit = resolved
            if context.scene.name != record['scene'] or context.view_layer.name != record['layer']:
                continue
            if edit is not None and edit.mode == 'EDIT' and context.object == edit:
                # An undo-restored edit session is owned by the persistent timer,
                # even when its original modal operator has already finished.
                if not source.hide_get(view_layer=context.view_layer):
                    source.hide_set(True, view_layer=context.view_layer)
                if edit.hide_get(view_layer=context.view_layer):
                    edit.hide_set(False, view_layer=context.view_layer)
                if edit.hide_render != record['render']:
                    edit.hide_render = record['render']
                if record.pop('parked', False):
                    source[RECORD] = json.dumps(record)
            else:
                finish(token, context, push_undo=True)
    finally:
        _busy = False


def _tick():
    if not _registered:
        return None
    if not _paused:
        for window in bpy.context.window_manager.windows:
            with bpy.context.temp_override(window=window):
                try:
                    reconcile(bpy.context)
                except (ReferenceError, RuntimeError) as error:
                    print('Edit Poly session recovery deferred:', error)
    return 0.05


@bpy.app.handlers.persistent
def history_pre(*args):
    global _paused, _epoch
    _paused = True
    _epoch += 1
    _started.clear()


@bpy.app.handlers.persistent
def history_post(*args):
    global _paused
    _paused = False
    # Undo-restored objects are not new user duplicates.
    _addon()._known_objects = {obj.as_pointer(): obj.name for obj in bpy.data.objects}
    # Resolve on the next UI tick, after all undo/load handlers have completed.


_handlers = (
    (bpy.app.handlers.undo_pre, history_pre),
    (bpy.app.handlers.undo_post, history_post),
    (bpy.app.handlers.redo_pre, history_pre),
    (bpy.app.handlers.redo_post, history_post),
    (bpy.app.handlers.load_pre, history_pre),
    (bpy.app.handlers.load_post, history_post),
)


def register():
    global _registered, _paused
    _registered, _paused = True, False
    for handlers, fn in _handlers:
        if fn not in handlers:
            handlers.append(fn)
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=0.05, persistent=True)


def unregister():
    global _registered
    _registered = False
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    for handlers, fn in _handlers:
        if fn in handlers:
            handlers.remove(fn)
    if not _paused and hasattr(bpy.context, 'scene'):
        for source, record in list(records()):
            try:
                _started[record['token']] = _epoch
                finish(record['token'], bpy.context)
            except (ReferenceError, RuntimeError) as error:
                print('Edit Poly session cleanup deferred:', error)
    _started.clear()
