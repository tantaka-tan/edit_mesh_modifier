# Edit Poly Modifier — 开发笔记与避坑指南

本文档记录本插件开发过程中踩过的坑、Blender 5.x 的 API 差异与调试技巧，供后续维护参考。

> 环境：Blender 5.1.0（便携版，build 2026-03-17）· Windows x64 · Blender 内置 Python 3.11.x
> 辅助：本机独立 Python 3.11.8 用于离线语法/脚本检查（Blender 无头时验证文件）

---

## 一、Blender 5.x API 差异（最容易踩）

### 1. `DepsgraphUpdate` 没有 `id_type` 属性 ⚠️ 静默失效
- **现象**：`depsgraph_handler` 里 `update.id_type != 'OBJECT'` 永远抛 `AttributeError`；因外层有 `try/except: return`，**不报错但功能完全失效**——自动独立化不工作，且无任何提示。
- **原因**：Blender 5.1 起 `DepsgraphUpdate` 只有 `id`、`is_updated_geometry`、`is_updated_shading`、`is_updated_transform`。
- **正确写法**：
  ```python
  for update in depsgraph.updates:
      id_data = update.id
      if not isinstance(id_data, bpy.types.Object):
          continue
      obj = getattr(id_data, "original", id_data)  # updates 里是 evaluated 对象
  ```
- **教训**：`try/except: return` 会吞掉 API 失效。新写 handler 时先去掉 try 验证一次真实触发。

### 2. 字符串属性 `.value` 是 bytes，不是 str
- `Mesh.attributes["xxx"].data[i].value` 在 5.x 返回 `bytes`，写入要 `.encode()`，读取要 `.decode()`。
- 例：`idx_pos_cache` 字符串属性（见 `backup_point_attrs` / `restore_point_attrs`）。

### 3. `bpy.app.timers` 是 module，不是 list
- 只有 `is_registered / register / unregister` 方法，**不能 `len()`、不能枚举**。调试时不要试图遍历它。

### 4. `bpy.app.translations` 没有 `domains` 属性
- 判断翻译域是否注册不能靠 `domains`。验证翻译用 `pget_tmpl(...)`（会真实走翻译）；直接调 `pgettext(msgid, domain)` 在 zh_CN 下可能返回英文，**不要用它判断**。

### 5. `SimpleDeformModifier` 属性名变化
- `mode` → `deform_method`（`'TWIST'` 等枚举值不变），`angle`、`deform_axis` 保留。测试其他修改器同理：先 `dir(mod)` 确认。

### 6. 检查类是否注册：`dir(bpy.types)` 不可靠
- **现象**：`getattr(bpy.types, "EDITMESH_OT_Build")` 返回 `None`、`"EDITMESH_OT_Build" in dir(bpy.types)` 为 False，但 `bpy.ops.editmesh.build` 实际可用、`preferences` 实例也正常。
- **正确验证**：
  ```python
  hasattr(bpy.ops.edit_mesh_modifier, "add")          # 操作符
  bpy.context.preferences.addons["edit_mesh_modifier"].preferences  # 偏好设置
  ```

---

## 二、注册 / 重载类残留（Blender 5.x 特有）

### 7. 反复 disable/enable + 磁盘自动重载会弄脏注册表
- Blender 检测到 `__init__.py` 磁盘变更会自动 "reloading..." 并重新 `register`，**不会先 unregister 旧类**。
- 症状：
  - `bpy.utils.register_class(cls)` → `ValueError("already registered as a subclass '...'")`
  - `bpy.utils.unregister_class(cls)` → `RuntimeError("...missing bl_rna attribute ... may not be registered")`
  - `bpy.ops.xxx` 与 `dir(bpy.types)` 结果不一致
- **规避**：改完代码不要依赖自动重载，走标准流程：
  ```python
  bpy.ops.preferences.addon_disable(module="edit_mesh_modifier")
  # 清 sys.modules 与 __pycache__（见下）
  bpy.ops.preferences.addon_enable(module="edit_mesh_modifier")
  ```
- 彻底清理残留：
  ```python
  import sys, shutil, os
  for k in [k for k in sys.modules if k.startswith("edit_mesh_modifier")]:
      del sys.modules[k]
  pypath = r"...\edit_mesh_modifier\__pycache__"
  if os.path.isdir(pypath):
      shutil.rmtree(pypath)
  ```

### 8. 已注册类被 GC 后无法卸载（重启才干净）
- 旧 bl_idname（如改名前 `editmesh.add`）残留在 `bpy.ops` 里，遍历 `bpy_struct.__subclasses__()` 找到的类对象已无 `bl_rna`，`unregister_class` 必然失败。
- **结论**：当前会话清不掉，**重启 Blender 即消失**。这不是代码问题，勿过度处理。

### 9. `register_class` / `unregister_class` 的返回行为
- `register_class` 对"已注册"返回 `False`（仅信息提示，不抛异常）；`unregister_class` 对"未注册"**抛异常**。判断用返回值，别用 try 猜。

### 10. AddonPreferences 的 `bl_idname` 必须等于模块名
- 类名随便改，`bl_idname = __name__` 不能动，否则偏好设置加载失败。

---

## 三、数据安全 / 资源泄漏（功能正确性）

### 11. 复制共享缓存 → 清理旧缓存会破坏原物体
- 复制带修改器的物体时，副本的 `OBJ_SOCKET` 指向**同一个缓存物体**。REHASH / 自动独立化后若直接删除旧缓存，会把原物体的引用一并删掉。
- 删除前必须检查是否仍被其他修改器引用（`_cache_referenced_by_other`）。

### 12. `eval_obj.to_mesh()` 必须配对 `to_mesh_clear()`
- 中间抛异常会泄漏评估网格。正确姿势（`bake_cache` / `sync_upstream_to_cache` 已统一）：
  ```python
  eval_mesh = None
  try:
      eval_mesh = eval_obj.to_mesh()
      ...
  finally:
      if eval_mesh is not None:
          try: eval_obj.to_mesh_clear()
          except Exception: pass
  ```

### 13. 无条件 `undo_push` 污染撤销栈
- 每次退出编辑都 `undo_push`，即使没编辑也会多一个撤销点。用几何指纹（顶点/边/面数 + 坐标和，见 `_mesh_geom_snapshot`）比对，有改动才 push。

### 14. `backup_point_attrs` 的备份时机
- 备份（全顶点 JSON 序列化）不要放在"每次进入编辑前"——高模卡顿且数据与 bake 后一致（期间无合法变更）。放在 **bake 写入后** + **SYNC 基准刷新后** 即可。

### 15. `_is_new_object` 用 `obj.as_pointer()` 作 key
- 对象删除后指针可能被复用（低概率误判漏检一次复制）。用 `{ptr: name}` 并在 name 不匹配时视为新对象，可缓解。

---

## 四、翻译与编码

### 16. zh_HANS.py 曾被永久损坏
- 症状：文件是合法 UTF-8（严格解码不报错），但每个中文串末字符变 `�?` 且右引号丢失——是**语法错误级损坏**，`ast.parse` 直接失败，翻译整体失效。
- 判断文件是否真的损坏：**不要看 PowerShell 控制台**（GBK 显示 UTF-8 必乱码）。用 `ast.parse` + `json.dumps(v, ensure_ascii=True)` 看真实内容。

### 17. 翻译键必须与源码字符串逐字一致
- 改 bl_idname / bl_label 后，同步更新 `translation/__init__.py` 的 `_UI_CONTEXTS` 与 `zh_HANS.py` 键。核对脚本：用 ast 提取 `__init__.py` 所有字符串字面量，与字典键比对。

---

## 五、Git / 行尾

### 18. 插件源码是 CRLF，写回必须保持
- 本仓库文件为 CRLF。用 Python `open(path, "w", newline="\n")` 写回会把**整个文件**变成 LF，git diff 显示数百行假变化。
- 转换回 CRLF：
  ```python
  d = open(p, "rb").read()
  d = d.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
  open(p, "wb").write(d)
  ```
- git 提示 "LF will be replaced by CRLF" 时先检查行尾是否被改过。

### 19. git diff 里混着历史未提交改动
- 工作区可能带用户之前的未提交改动（如 version 1.0.1→1.0.2），`git diff` 会一起显示。审查自己改动时按 hunk 定位，别把历史改动当自己引入的。

---

## 六、测试与调试（Blender MCP）

### 20. 不能直接 `MyOperator()` 实例化操作符
- 报 `bpy_struct.__new__(struct): expected a single argument`。测试操作符要走 `bpy.ops.*`。

### 21. `bpy.ops.xxx.build(mode='...')` 会被 invoke 覆盖 mode
- 定义了 `invoke` 的操作符，脚本调用也会走 invoke，无修饰键时按 invoke 逻辑重设 mode（本插件默认变 SYNC）。测试指定模式需 monkeypatch：
  ```python
  orig = m.EDIT_MESH_MODIFIER_OT_Build.invoke
  def fake(self, context, event):
      return self.execute(context)
  m.EDIT_MESH_MODIFIER_OT_Build.invoke = fake
  try: bpy.ops.edit_mesh_modifier.build(mode='REBUILD')
  finally: m.EDIT_MESH_MODIFIER_OT_Build.invoke = orig
  ```

### 22. `context.evaluated_depsgraph_get().update()` 会消费 updates
- 同步脚本里手动 `update()` 后 `depsgraph.updates` 为空，且 handler 收到的 depsgraph 是另一实例。验证 handler 收集逻辑用真实操作（`duplicate_move` 等）触发，或直接构造 fake depsgraph 单测。

### 23. Timer 只在事件循环跑
- 同步 `execute_blender_code` 里注册的 timer 不会立刻执行。验证"复制→自动独立化"完整链路，要操作后等真实事件循环跑完再查结果。

### 24. blender-mcp 通道
- 现象：Blender 进程 CPU 很低 ≠ 没卡；MCP 请求超时可能只是 server 连接断了。
- `blender-mcp.exe --help` 启动时会打印 `Connected to Blender at localhost:9876`，可用来自检 Blender 侧是否在监听。
- 杀掉 blender-mcp 进程后 **opencode 不会自动重建**，需用户重启 opencode（或重启 Blender）。判断端口：`Get-NetTCPConnection -State Listen | ? LocalPort -eq 9876`。

### 25. 避免在 depsgraph handler 的调试 spy 里做重操作
- 在 `depsgraph_update_post` 的 spy 中循环 `dg.update()` 曾把 Blender MCP 通道搞挂。spy 只记录，不要嵌套触发评估。

---

## 七、命名约定

### 26. bl_idname 前缀必须足够长，避免撞名
- 早期 `editmesh.*`（`editmesh.add/build/edit`）太通用。统一改为插件 id 前缀：
  - `edit_mesh_modifier.add` / `.build` / `.edit`
  - 类名 `EDIT_MESH_MODIFIER_OT_*`、面板 `EDIT_MESH_MODIFIER_PT_Main`
- bl_idname 变更会让 `.blend` 里已绑定的自定义快捷键失效（插件内部调用已同步更新，无影响）。

---

## 快速核对清单（改动后必查）

1. `ast.parse` 三个文件：`__init__.py`、`translation/__init__.py`、`translation/zh_HANS.py`
2. 行尾保持 CRLF（`d.count(b'\r\n') == d.count(b'\n')`）
3. 翻译键与源码字符串逐字一致（用 ast 提取核对）
4. 改名后全局搜索旧标识符，确认无残留
5. Blender 里走标准 disable/enable（非自动重载），用 `bpy.ops.*` 验证而非 `dir(bpy.types)`
