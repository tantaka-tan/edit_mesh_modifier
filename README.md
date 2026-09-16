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

## Topology protection trial (1.0.12)

**トポロジー保護（試験版）**を追加しました。入力の頂点識別情報、頂点・辺・面の数、
番号順の接続を基準と比較し、不一致ならそのEdit Polyを一時停止して入力を素通しに
します。基準と一致する構成に戻すと編集が復帰します。再投影は行いません。
判定はGeometry Nodes内で評価ごとに行い、モディファイアーの表示スイッチは変更しません。

- **新しく作成・再構築したEdit Poly**：その時点の入力を基準に保護を有効化します。
- **既存のEdit Poly**：正常な上流構成に戻し、専用パネルの **保護基準を登録** を押してください。
  頂点位置は保持しますが、識別用の内部属性を追加します。既に壊れた対応を修復する操作ではありません。
- **入力の互換性を確認**：有効か一時停止中かと、その理由を表示します。
- **トポロジー保護を有効化**：段ごとにオフにして従来の動作へ戻せます。

一時停止中はキャッシュへの編集開始・上流同期、およびその段を含むシェイプキー変換も
中断し、編集データを守ります。上流の頂点位置だけを変える変形は引き続き追従します。
動作例は `dist/topology-protection-demo.blend`（Blender 5.2用）の **Toggle this Subdivision** を
オン・オフして確認できます（デモ生成スクリプトは `tests/create_topology_demo.py`）。

**試験版の範囲**：Subdivision、Mirror、Array、Geometry Nodesの頂点ソートをテストしています。
識別属性を失うRemeshや独自ノードなどでは、正常に見える入力でも一時停止する場合があります。
識別情報の複製・再生成によって番号順と接続まで同じになった場合は区別できず、あらゆる
モディファイアーへの完全な対応保証ではありません。構造が同じでも属性だけの変更は検査しません。
また各段に基準メッシュを保持するため、メモリー使用量と評価コストが増えます。

The experimental guard stores an independent upstream reference per stage. It
compares counts, ordered origin IDs, edge endpoints and polygon corner mappings
inside Geometry Nodes, then passes the input through on mismatch. It works
without a Python polling timer, including when the add-on is disabled. Cache
coordinates and modifier visibility flags are preserved. New/Rebuilt stages bind
automatically; legacy stages require explicit registration in a known-good state.
An internal `.edit_poly_origin_id` point attribute is added to the source mesh.
Zero/missing IDs conservatively pause evaluation. Topology-generating operations
may duplicate/interpolate IDs, so this is not a universal persistent-ID system.
Equal IDs and equal indexed topology cannot distinguish all semantic changes.
The baseline is the viewport input at registration; a different render topology
also pauses the stage. Disable protection explicitly to use legacy behavior.

## Edit Mode appearance (1.0.11)

**プリファレンス → アドオン → Edit Poly Modifier → 編集モードへのアクセス** に
**通常の編集モードの表示設定を使う** を追加しました。初期状態はオンです。
Edit Polygonsに入ってもリトポロジー表示を強制せず、普段のオーバーレイ・透過・
シェーディング設定を保ちます。元オブジェクトの表示色、表示方法、最前面表示、
ワイヤー表示設定も編集中のキャッシュへ引き継ぎます。
オフにすると従来のリトポロジー表示になります。変更は次回の編集開始から有効です。

**Use Standard Edit Mode Appearance** keeps existing viewport settings and
temporarily copies the source object's color, display type, in-front and wire
display settings to the cache. It does not change the Blender theme or materials.
Previously enabled retopology remains enabled, just as in ordinary Edit Mode.
Random object colors can differ because the cache is a separate object.
Disable the preference to force the previous retopology overlay during editing.
Cache display settings are restored on exit, cancellation and entry failure.

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
blender --background --factory-startup --python-exit-code 1 --python tests/test_topology_guard.py
```
