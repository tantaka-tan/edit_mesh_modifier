# 简体中文（英 → 中）翻译字典。
# 源码为英文，当 Blender UI 语言为中文时，以下条目把英文显示为中文。
# 键必须与 __init__.py 中的英文字符串完全一致；动态消息用 {placeholder}。

data = {
    # ====== bl_info ======
    "Edit Poly Modifier": "编辑多边形修改器",
    "Properties > Modifiers Tab": "属性面板 > 修改器页签",
    "Edit the mesh via a cache object, applied in real time": "通过缓存物体编辑网格，并将编辑结果实时应用到原物体",

    # ====== EDITMESH_OT_Build ======
    "Build Edit Poly Modifier": "构建【编辑多边形修改器】",
    "Mode": "模式",
    "Create": "新建",
    "Create an Edit Poly modifier and build its cache": "新建编辑多边形修改器并构建缓存",
    "Rebuild": "重建",
    "Rebuild the cache of the currently selected modifier": "重建当前选中修改器的缓存",
    "Fork": "独立化",
    "Recalculate the hash and its cache": "重新计算哈希值及缓存",
    "Build failed: {e}": "构建失败: {e}",
    "Build complete": "构建完成",

    # ====== EDITMESH_OT_Edit ======
    "Edit": "编辑",
    "Directly edit mesh data while keeping upstream modifiers intact": "在保留上游修改器的基础上，直接进行网格数据编辑",
    "The selected modifier is not an Edit Poly modifier. Run Build first": "当前所选修改器不是【编辑多边形修改器】，请先执行【构建】",
    "The modifier has no valid cache object. Run Build first": "修改器未记录有效的缓存物体，请先执行【构建】",
    "Failed to enter edit mode: {e}": "进入编辑模式失败: {e}",

    # ====== add-modifier menu ======
    "Create an Edit Poly modifier that lets you edit polygons directly without applying upstream modifiers": "创建一个【编辑多边形修改器】，你可以借助它，在不应用上游修改器的前提下，直接编辑多边形",

    # ====== MODIFIER_PT_EditMeshModifier (header & body) ======
    "Edit Polygons": "编辑多边形",
    "LMB Rebuild edits: rebuild the edited content of the current modifier\nCtrl+LMB Rehash: when you copy an object with the modifier, use this to make the modifier independent": "【左键】重建已编辑内容：重建当前修改器的的已编辑内容\n【ctrl+左键】重建修改器哈希：当你带修改器复制网格时，能帮助你将该修改器独立化",
    "Please select an Edit Poly modifier to edit": "请选择任意【编辑多边形修改器】进行编辑",
    "Instructions": "说明",
    "You can edit the mesh without applying modifiers": "你可以在不应用修改器的前提下",
    "Directly edit the mesh on top of upstream modifiers": "在上游修改器的基础上，直接对网格进行编辑",

    # ====== EditMeshModifierPreferences（偏好设置） ======
    "How to Access": "功能入口",
    "Go to the Properties Editor > Modifiers tab": "请前往【属性编辑器界面】》【修改器属性】",
    "Click Add Modifier > Edit to find the Edit Poly Modifier at the bottom of the panel": "点击【添加修改器】》【编辑】：即可在面板底部找到【编辑多边形修改器】",
    "Click Add Modifier > Generate to find the Edit Poly Modifier at the bottom of the panel": "点击【添加修改器】》【生成】：即可在面板底部找到【编辑多边形修改器】",
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

    # ====== RuntimeError messages (shown inside "Build failed: {e}") ======
    "Cannot load node groups, please check {file}": "无法加载节点组，请检查 {file}",
    "Please select an Edit Poly modifier first": "请先选中一个编辑多边形修改器",
    "Unsupported mode; this should never happen": "未受支持的模式，理论上这不该发生",
}
