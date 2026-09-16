# Edit Poly Modifier

This fork is maintained at [tantaka-tan/edit_mesh_modifier](https://github.com/tantaka-tan/edit_mesh_modifier).
It is based on [RARA's original add-on](https://github.com/raracannot/edit_mesh_modifier)
and retains its GPL-3.0-or-later license and original author attribution.

このフォークでは、シェイプキー変換、複数Edit Polyの最終形状の保存、
編集中の元オブジェクト非表示などの改修を管理しています。

For development, use this fork as `origin` and the original repository as
`upstream`. Push changes to this fork's `main` branch; fetch upstream updates
with `git fetch upstream` and review them before merging.

While Edit Polygons is active, the source object is hidden in the current view
layer. Its previous visibility is restored on exit or cancellation; render
visibility is unchanged.

## Shape-key export (1.0.8)

Select an Edit Poly modifier. In its dedicated panel, open the **Shape Keys**
menu (also available as the shape-key icon beside **Edit Polygons**).
The Geometry Nodes modifier's built-in drop-down is unchanged.

- **Save as Shape Key** creates a relative key at value **0** and preserves the
  entire stack. Disable all captured modifiers before activating the saved key.
- **Apply as Shape Key** creates a relative key at value **1**, disables captured
  upstream modifiers in the viewport and render, and removes the selected Edit
  Poly only if it was enabled. Previously disabled stages are left unchanged.
  Cache data still referenced by another modifier is retained.

The result captures the **evaluated viewport shape through the selected stage**.
Choose the last Edit Poly to combine all its enabled preceding stages. Disabled
viewport modifiers are ignored, including a disabled selected stage, even when
their render visibility is enabled. Downstream modifiers are not captured.

`new key = Basis + (captured shape - current shape-key mix without modifiers)`

Existing keys, their values, animation, and Basis are preserved. Subtracting their
current mix avoids double application. Enabled upstream deformations (Armature,
Curve, etc.) are baked at the current frame, not inverted. This captures positions
only, not animation, UV changes, or custom normals. Apply requires shape-key
display pinning to be off. Evaluation uses a temporary object and leaves the
live modifier stack untouched until a successful Apply.

The source must use an editable, single-user mesh with relative shape keys.
Vertex IDs must form a one-to-one mapping to the source, and mapped edges and
oriented faces must match. Extrusions, deletions and topology edits are rejected.
Stacked Edit Poly stages are supported when each preserves topology. Vertex
correspondence is traced through every enabled stage. Passing upstream data may
be on or off: the actual evaluated result is captured rather than summing offsets.
Enabled upstream generators and unknown Geometry Nodes groups are still rejected
because their source-vertex identity is not guaranteed.

Newly baked caches no longer inherit shape keys: the cache already stores their
evaluated result, and inherited keys can have incompatible topology. Existing
caches are not automatically modified. Rebuild still replaces manual edits.

## Tests

Run in a separate Blender process:

```powershell
blender --background --factory-startup --python-exit-code 1 --python tests/test_shape_keys.py
```
