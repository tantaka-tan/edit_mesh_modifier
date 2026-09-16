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

## Automatic Edit Polygons, mode pie and shortcut (1.0.10)

**Edit Poly** をモディファイアータブで選択した状態で **Tab**、またはモード選択
メニューから編集モードに入ると、自動的に **Edit Polygons** の編集を開始します。
複数段ある場合は選択中の段を対象とし、編集中は元オブジェクトを非表示にします。
**Tab** で終了すると元オブジェクトへ戻ります。

**プリファレンス → アドオン → Edit Poly Modifier → 編集モードへのアクセス**
に、次の独立した設定があります。初期状態は両方オンです。

- **モード切替パイにEdit Polyを表示**：標準パイへの専用項目の追加を切り替えます。
- **編集モードで自動的にEdit Polygonsを開始**：通常の編集モードからの自動切り替えを制御します。オフなら元メッシュの編集になります。

設定変更は次に編集モードへ入るときから有効です。編集中の切り替え、ファイル読込、
Undo/Redoによる編集モードの復元では、自動で編集先を変更しません。
自動切り替えはUIタイマーで検出するため、開始まで最大約0.05秒（処理が重い場合は
それ以上）かかります。Tabやカスタムキー設定自体は書き換えません。

モディファイアータブで編集したい **Edit Poly** を選択し、3Dビューポートで
**Ctrl+Tab → Edit Poly** を選ぶと、Edit Polygonsボタンと同じ編集を開始します。
編集中は **Ctrl+Tab → Edit Polyを終了** または **Tab** で終了できます。
複数のEdit Polyがある場合は、モディファイアータブで選択中の段を編集します。
元オブジェクトはオブジェクトモードにしてから開始してください。

**プリファレンス → アドオン → Edit Poly Modifier → Edit Polyのショートカット**
で、編集開始・終了のキーを自由に割り当てられます。初期状態は未割り当てです。
専用ショートカットは、パイ表示・自動切り替えの両方をオフにしても使用できます。

The standard Blender **Mode** pie gains an **Edit Poly** entry for the active
Edit Poly modifier in Object Mode, and **Finish Edit Poly** while editing its
cache. Assign a separate toggle key in add-on preferences, or find **Edit Poly:
Toggle Edit Mode** with F3 in the 3D Viewport. The shortcut starts unassigned.
Custom pies (including Pie Menu Editor) can invoke the same operator:

```python
bpy.ops.edit_mesh_modifier.toggle_edit('INVOKE_DEFAULT')
```

Automatic entry also covers ordinary Edit Mode commands (Tab, mode dropdown,
and the native pie's Edit Mode). **Show Edit Poly in Mode Pie** and
**Automatically Enter Edit Polygons** are independent preferences, both on by
default. Disable automatic entry to edit the source mesh normally. The toggle
shortcut remains usable with both preferences off. A 50 ms UI timer detects new
mode entries without replacing keymaps; it may take longer while Blender is busy.
Existing editing sessions and mode restoration on load or Undo/Redo are ignored.

The integration targets Blender's standard `VIEW3D_MT_object_mode_pie`.
A custom mode pie supplied by another add-on needs the operator added to it.

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
blender --background --factory-startup --python-exit-code 1 --python tests/test_edit_access.py
```
