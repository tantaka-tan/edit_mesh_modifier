V1.0.10 Update Notes

- With an Edit Poly modifier selected, entering ordinary Edit Mode now opens Edit Polygons automatically (enabled by default).
- Add an independent automatic-entry preference beside the existing mode-pie visibility preference; the dedicated shortcut remains available with either feature disabled.
- Detect mode entry on the UI timer without replacing Tab or custom keymaps. Reuse the existing cache editor and its exit/visibility cleanup.
- Do not redirect an existing edit session on preference changes, file loading, or Undo/Redo restoration. Stop monitoring when the preference or add-on is disabled.

V1.0.9 Update Notes

- Add Edit Poly to Blender's standard mode-switch pie (Ctrl+Tab) when the selected modifier has a mesh cache.
- Use the same entry to finish cache editing and restore the source object.
- Add an independently assignable Edit Poly toggle shortcut in add-on preferences, initially unassigned.
- Expose the toggle as an operator for F3 search and custom pie menus. Normal Tab behavior is unchanged.

V1.0.8 Update Notes

- Shape-key export now captures the final viewport result through the selected Edit Poly, including all enabled preceding stages.
- Ignore modifiers disabled in the viewport, regardless of their render visibility.
- Save keeps the stack intact at key value 0. Apply activates the key, disables captured upstream stages, and removes the selected stage only if it was enabled.
- Evaluate on a temporary object and subtract the existing shape-key mix to prevent double application.

V1.0.7 Update Notes

- Allow shape-key export from stacked Edit Poly stages when every upstream stage preserves topology.
- Compose vertex correspondence through the stack and export only the selected stage's offsets.
- Prevent applying a shape key beneath a frozen upstream Edit Poly that would suppress it.

V1.0.6 Update Notes

- Hide the source object in the current view layer while editing the Edit Poly cache.
- Restore its previous visibility on edit exit, cancellation, or failure to enter Edit Mode.

V1.0.5 Update Notes

- Added Save as Shape Key and Apply as Shape Key in the Edit Poly panel.
- Export local edit offsets with vertex identity and topology checks; preserve existing relative shape keys.
- Added Japanese translations for shape-key export.
- New and rebuilt caches no longer inherit incompatible shape keys from evaluated meshes.
- Fixed point-attribute backups on Blender 4.2 builds that require bytes.
- Added Blender integration tests for export, existing keys, and incompatible data.

V1.0.2 Update Notes

Added:
- Added an "Auto Sync Upstream" preference: when enabled, upstream modifier changes are automatically synced into the cache before entering Edit Polygons.
- Split the build operator into two: "Add Edit Poly Modifier" (create) and "Build" (Rebuild / Fork / Sync Upstream), making the UI entries clearer.

Improved:
- Renamed all operator bl_idnames and class names with a longer, collision-free prefix (edit_mesh_modifier.*) to avoid conflicts with other add-ons.
- Rewrote auto-independence detection: now tracks newly added objects via the depsgraph instead of counting objects, fixing the feature silently failing on Blender 5.1 (DepsgraphUpdate no longer exposes id_type).
- Point-attribute backups are now written once at bake time instead of before every edit session, reducing lag when entering Edit Mode on dense meshes.
- The undo step is only pushed when the mesh actually changed, keeping the undo stack clean.
- Orphaned cache objects are cleaned up after Rehash, with protection against deleting a cache still shared by other modifiers.

Fixed:
- Fixed a potential evaluated-mesh leak in the bake/sync paths when an error occurred mid-baking.
- Fixed the corrupted simplified-Chinese translation dictionary and backfilled missing translation entries.


V1.0.2更新内容

新增:
- 新增偏好设置【自动同步上游】：勾选后，进入【编辑多边形】前会自动把上游修改器的变化同步进缓存。
- 将构建操作符拆分为两个：【新建编辑多边形修改器】与【构建】（重建 / 独立化 / 同步上游），功能入口更清晰。

改进:
- 将所有操作符的 bl_idname 与类名统一加长为不易撞名的前缀（edit_mesh_modifier.*），避免与其他插件冲突。
- 重写自动独立化检测：改为通过 depsgraph 追踪新增物体，修复了该功能在 Blender 5.1 上静默失效的问题（DepsgraphUpdate 不再提供 id_type）。
- 点属性备份改为在烘焙阶段一次性写入，替代每次进入编辑前备份，降低高模进入编辑模式时的卡顿。
- 仅在实际改动网格时才产生撤销点，保持撤销栈干净。
- 独立化（Rehash）后会清理无引用的孤儿缓存物体，并保护仍被其他修改器共享的缓存不被误删。

修复:
- 修复了烘焙 / 同步流程中途出错时可能泄漏评估网格的问题。
- 修复了损坏的简中翻译字典，并补齐缺失的翻译词条。
