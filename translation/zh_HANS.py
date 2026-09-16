# 简体中文（zh_HANS）翻译字典。
# 源码为英文，当 Blender UI 语言为中文时，以下条目把英文显示为中文。
# 键必须与 __init__.py 中的英文字符串完全一致；动态消息用 {placeholder}。
data = {
    "Save the evaluated viewport result through this Edit Poly as a shape key; disabled modifiers are ignored": "将当前编辑多边形之前的最终视口结果保存为形态键，忽略已禁用的修改器",
    "Saves the final viewport shape through the selected Edit Poly.": "保存到当前编辑多边形为止的最终视口形状。",
    "Disabled modifiers are ignored. Topology changes are not supported.": "忽略视口中禁用的修改器，不支持拓扑变更。",
    "The key starts at 0. Disable the captured modifiers before using it.": "形态键初始值为0，使用前请禁用已烘焙的修改器。",
    "Apply disables captured upstream modifiers and removes the selected enabled stage.": "应用时禁用已烘焙的上游修改器，并移除当前选中的已启用修改器。",
    "Unpin the active shape key before applying the snapshot.": "应用前请取消形态键的显示固定。",
    "Viewport and render have different vertex correspondence upstream.": "上游在视口与渲染中的顶点对应关系不同。",
    "Enable Passing upstream data on earlier Edit Poly modifiers before applying as a shape key.": "应用为形态键前，请开启上游编辑多边形修改器的位置自动修正。",
    "Only the selected Edit Poly's edits are saved; earlier stages remain separate.": "仅保存当前编辑多边形的编辑偏移，不包含上游阶段的编辑。",
    "Edit Poly to Shape Key": "将编辑多边形转为形态键",
    "Shape Keys": "形态键",
    "Save as Shape Key": "保存为形态键",
    "Apply as Shape Key": "应用为形态键",
    "Keep Modifier": "保留修改器",
    "Store local Edit Poly offsets as a relative shape key; upstream deformation is not baked or inverted": "将编辑多边形的局部顶点偏移保存为相对形态键，不烘焙或反向计算上游形变",
    "Exports local vertex edits only; topology changes are not supported.": "仅导出局部顶点位置编辑，不支持拓扑变更。",
    "Upstream deformation is not inverted; posed results may differ.": "不会反向计算上游形变，姿态下的显示结果可能不同。",
    "The key starts at 0. Disable Edit Poly before using the key.": "形态键初始值为0，使用前请禁用编辑多边形修改器。",
    "Created shape key: {name}": "已创建形态键：{name}",
    "Shape keys require the same vertex count as the source mesh.": "形态键要求顶点数量与原始网格一致。",
    "The cache has no valid vertex correspondence. Rebuild before editing.": "缓存缺少有效顶点对应信息，请在开始编辑前重建。",
    "The cache contains new or unmapped vertices; it cannot become a shape key.": "缓存包含新增或无法对应的顶点，无法转换为形态键。",
    "Edges or faces differ from the source mesh; only vertex position edits can be exported.": "边或面的结构与原始网格不同，仅支持导出顶点位置编辑。",
    "The cache contains invalid coordinates.": "缓存包含无效坐标。",
    "Switch the source mesh to Object Mode first.": "请先将原始网格切换到物体模式。",
    "The source mesh must be editable and single-user.": "原始网格必须可编辑且为单用户数据。",
    "Cannot verify vertex identity through upstream modifier: {name}": "无法确认经过上游修改器后的顶点对应：{name}",
    "Only editable relative shape keys are supported.": "仅支持可编辑的相对形态键。",
    "Existing shape keys do not match the source vertex count.": "现有形态键的顶点数量与原始网格不一致。",
    # ====== bl_info ======
    "Edit Poly Modifier": "编辑多边形修改器",
    "Properties > Modifiers Tab": "属性面板 > 修改器页签",
    "Edit the mesh via a cache object, applied in real time": "通过缓存物体编辑网格，并将编辑结果实时应用到原物体",

    # ====== EDIT_MESH_MODIFIER_OT_Add ======
    "Add Edit Poly Modifier": "新建编辑多边形修改器",

    # ====== EDIT_MESH_MODIFIER_OT_Build ======
    "Build Edit Poly Modifier": "构建【编辑多边形修改器】",
    "Mode": "模式",
    "Create": "新建",
    "Create an Edit Poly modifier and build its cache": "新建编辑多边形修改器并构建缓存",
    "Rebuild": "重建",
    "Rebuild the cache of the currently selected modifier": "重建当前选中修改器的缓存",
    "Fork": "独立化",
    "Recalculate the hash and its cache": "重新计算哈希值及缓存",
    "Sync Upstream": "同步上游",
    "Sync upstream vertex position changes to cache while keeping edits": "将上游顶点位置的变化同步到缓存，同时保留你的编辑",
    "Build failed: {e}": "构建失败: {e}",
    "Build complete": "构建完成",

    # ====== EDIT_MESH_MODIFIER_OT_Edit ======
    "Edit": "编辑",
    "Directly edit mesh data while keeping upstream modifiers intact": "在保留上游修改器的基础上，直接进行网格数据编辑",
    "The selected modifier is not an Edit Poly modifier. Run Build first": "当前所选修改器不是【编辑多边形修改器】，请先执行【构建】",
    "The modifier has no valid cache object. Run Build first": "修改器未记录有效的缓存物体，请先执行【构建】",
    "Failed to enter edit mode: {e}": "进入编辑模式失败: {e}",

    # ====== add-modifier menu ======
    "Create an Edit Poly modifier that lets you edit polygons directly without applying upstream modifiers": "创建一个【编辑多边形修改器】，你可以借助它，在不应用上游修改器的前提下，直接编辑多边形",

    # ====== EDIT_MESH_MODIFIER_PT_Main (header & body) ======
    "Edit Polygons": "编辑多边形",
    "LMB Sync Upstream: sync upstream modifier changes into the cache while keeping edits\nCtrl+LMB Rebuild: rebuild the edited content of the current modifier\nShift+LMB Rehash: generate a new hash to fork the modifier, e.g. after duplicating": "【左键】同步上游：将上游修改器的变化同步进缓存，同时保留你的编辑\n【ctrl+左键】重建：重建当前修改器的已编辑内容\n【shift+左键】独立化：生成新哈希以独立化该修改器，例如复制物体后",
    "Please select an Edit Poly modifier to edit": "请选择任意【编辑多边形修改器】进行编辑",
    "Instructions": "说明",
    "You can edit the mesh without applying modifiers": "你可以在不应用修改器的前提下",
    "Directly edit the mesh on top of upstream modifiers": "在上游修改器的基础上，直接对网格进行编辑",
    "Select an Edit Poly modifier, then click Edit Polygons in the header": "选中任一【编辑多边形修改器】后、点击标题栏的【编辑多边形】即可",
    "Build Cache": "构建缓存",
    "Auto Position Fix": "位置自动修正",
    "Note: buttons are only visible when an Edit Poly modifier is selected": "注意，按钮仅当选中【编辑多边形修改器】后可见",
    "When Auto Position Fix is enabled and upstream modifiers keep the vertex count,": "【位置自动修正】启用时，如果上游修改器没有增减顶点数量",
    "upstream edits are still applied perfectly after Edit Polygons, for example:": "【编辑多边形】后，仍能完美传递上游修改内容，例如：",
    "Shrinkwrap Modifier": "缩裹修改器",
    "Solidify Modifier": "实体化修改器",
    "Bevel Modifier": "倒角修改器",
    "Subdivision Modifier": "细分修改器",
    "Even after editing with Edit Polygons, you can still:": "哪怕【编辑多边形】编辑后，你仍可以：",
    "Adjust parameters such as the Shrinkwrap offset": "修改缩裹的偏移量等参数",
    "Adjust parameters such as the Solidify thickness": "修改实体化的厚度等参数",
    "Adjust parameters such as the Bevel radius": "修改倒角的半径等参数",
    "All of these changes are picked up by downstream modifiers": "以上的所有修改都会让下游识别",

    # ====== EDIT_MESH_MODIFIER_Preferences（偏好设置） ======
    "Auto Rehash on Duplicate": "复制时自动独立化",
    "Automatically generate a new hash and cache when an object is duplicated (Shift+D)": "当物体被复制（Shift+D）时，自动为其生成新哈希与缓存",
    "Auto Sync Upstream": "自动同步上游",
    "Automatically sync upstream modifier changes into the cache before entering Edit Polygons": "进入【编辑多边形】前，自动把上游修改器的变化同步进缓存",
    "Automation & Performance": "自动化与性能",
    "How to Access": "功能入口",
    "Go to the Properties Editor > Modifiers tab": "请前往【属性编辑器界面】》【修改器属性】",
    "Click Add Modifier > Edit to find the Edit Poly Modifier at the bottom of the panel": "点击【添加修改器】》【编辑】：即可在面板底部找到【编辑多边形修改器】",
    "Click Add Modifier > Generate to find the Edit Poly Modifier at the bottom of the panel": "点击【添加修改器】》【生成】：即可在面板底部找到【编辑多边形修改器】",

    # ====== RuntimeError messages (shown inside "Build failed: {e}") ======
    "Cannot load node groups, please check {file}": "无法加载节点组，请检查 {file}",
    "Please select an Edit Poly modifier first": "请先选中一个编辑多边形修改器",
    "Unsupported mode; this should never happen": "未受支持的模式，理论上这不该发生",
}
