"""Temporary editable display of the downstream stack, sharing raw cache data."""

import bpy

MARKER = '_edit_poly_preview_cache'


def raw_cache(obj):
    if obj is None or obj.type != 'MESH':
        return None
    cache = obj.get(MARKER)
    return cache if isinstance(cache, bpy.types.Object) and cache.type == 'MESH' and cache.data == obj.data else None


def is_preview(obj):
    return raw_cache(obj) is not None


def create(context, source, cache, target):
    downstream = list(source.modifiers)[source.modifiers.find(target.name) + 1:]
    if not any(mod.show_viewport and mod.show_in_editmode for mod in downstream):
        return None
    preview = cache.copy()
    try:
        preview.name = cache.name + '.edit_preview'
        preview[MARKER] = cache
        preview.hide_render = True
        context.scene.collection.objects.link(preview)
        # Use Blender's native copy to preserve nested modifier settings and
        # Geometry Nodes inputs across API versions. Never modify the raw cache's
        # modifier stack: Edit Poly's Object Info must still receive raw geometry.
        with context.temp_override(object=source, active_object=source,
                                   selected_objects=[source, preview],
                                   selected_editable_objects=[source, preview]):
            for mod in downstream:
                result = bpy.ops.object.modifier_copy_to_selected(modifier=mod.name)
                if 'FINISHED' not in result:
                    raise RuntimeError('Cannot preview modifier: ' + mod.name)
        return preview
    except Exception:
        bpy.data.objects.remove(preview, do_unlink=True)
        raise


def remove(preview):
    if preview is not None:
        try:
            bpy.data.objects.remove(preview, do_unlink=True)
        except ReferenceError:
            pass
