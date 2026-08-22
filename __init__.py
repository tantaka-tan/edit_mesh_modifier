
bl_info = {
    "name": "Edit Poly Modifier [编辑多边形修改器]",  # 编辑多边形修改器
    "author": "RARA",
    "version": (1, 0, 0),
    "blender": (4, 5, 0),
    'doc_url': 'https://space.bilibili.com/27284213',
    "location": "Properties > Modifiers Tab",  # 属性面板 > 修改器页签
    "description": "Edit the mesh via a cache object, applied in real time",  # 通过缓存物体编辑网格，并将编辑结果实时应用到原物体
    "category": "Object",
}

import os  # noqa: E402
import bpy  # noqa: E402
import uuid  # noqa: E402
from . import translation as _i18n  # noqa: E402

ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_PATH = os.path.join(ADDON_DIR, "lib.blend")

NG_SAVE = ".save_base_info_to_cache"
NG_EDIT = ".edit_mesh_modifier"

# 编辑多边形
MOD_EDIT_NAME = "Edit Poly"
# 保存数据
MOD_TEMP_NAME = "Save Cache"

# 物体名称_物体哈希_缓存标识（CACHE_SUFFIX）
CACHE_SUFFIX = "edit_mesh_modifier_cache"

# 几何节点修改器的输入 socket（改节点组接口时只需调整这里）
OBJ_SOCKET = "Socket_2"      # 缓存物体 Object 输入
AUTO_FIX_SOCKET = "Socket_3" # 位置自动修正开关
HASH_SOCKET = "Socket_4"     # 修改器唯一哈希（文本）

# ---------------------------------------------------------------------------
# 核心逻辑
# ---------------------------------------------------------------------------

def get_cache_name(obj_name, hash_str=""):
    return f"{obj_name}_{hash_str}_{CACHE_SUFFIX}" if hash_str else f"{obj_name}_{CACHE_SUFFIX}"

def _load_lib_node_groups(names):
    """从 lib.blend 追加指定名称的节点组。"""
    if not os.path.exists(LIB_PATH):
        return False
    with bpy.data.libraries.load(LIB_PATH, link=False) as (data_from, data_to):
        data_to.node_groups = [n for n in data_from.node_groups if n in names]
    return True


def _repoint_node_group_refs(old, new):
    """把所有引用旧节点组的修改器与 Group 节点改指向新节点组。"""
    for obj in bpy.data.objects:
        for mod in obj.modifiers:
            if mod.type == 'NODES' and mod.node_group is old:
                mod.node_group = new
    for ng in bpy.data.node_groups:
        for node in ng.nodes:
            if getattr(node, "node_tree", None) is old:
                node.node_tree = new

def refresh_node_groups():
    """从 lib.blend 热刷新两个节点组，即使被误改也不会死档。

    做法：旧节点组改名让位 -> 导入 lib 新版 -> 重指所有引用 -> 删旧。
    已实测：重指后每个修改器的 Socket_2/3/4 值均原样保留。
    """
    if not os.path.exists(LIB_PATH):
        return False
    ok = True
    for name in (NG_SAVE, NG_EDIT):
        old = bpy.data.node_groups.get(name)
        if old is not None:
            old.name = f"__em_old_{name}"
        if not _load_lib_node_groups([name]):
            if old is not None:
                old.name = name
            ok = False
            continue
        new = bpy.data.node_groups.get(name)
        if new is None:
            if old is not None:
                old.name = name
            ok = False
            continue
        if old is not None:
            _repoint_node_group_refs(old, new)
            try:
                bpy.data.node_groups.remove(old, do_unlink=True)
            except Exception:
                pass
    return ok

def ensure_node_groups():
    """确保两个节点组存在，缺少则从插件根目录的 lib.blend 加载。"""
    missing = [name for name in (NG_SAVE, NG_EDIT) if name not in bpy.data.node_groups]
    if not missing:
        return True
    return _load_lib_node_groups(missing)

def _object_alive(obj):
    """判断 bpy 数据引用是否仍有效（撤回/删除后引用会失效）。"""
    if obj is None:
        return False
    try:
        obj.name
        return True
    except ReferenceError:
        return False

def get_modifier_socket_value(mod, key):
    """读取 socket 值（5.1 用 ID 属性，5.2 用 properties.inputs 新 API）。"""
    if mod is None:
        return None
    try:
        if bpy.app.version >= (5, 2):
            sock = getattr(mod.properties.inputs, key, None)
            return sock.value if sock is not None else None
        return mod[key]
    except Exception:
        return None

def set_modifier_socket_value(mod, key, value):
    """写入 socket 值（5.1 用 ID 属性，5.2 用 properties.inputs 新 API）。"""
    if mod is None:
        return False
    try:
        if bpy.app.version >= (5, 2):
            sock = getattr(mod.properties.inputs, key, None)
            if sock is None:
                return False
            sock.value = value
        else:
            mod[key] = value
        return True
    except Exception:
        return False

def get_cache_object(mod, obj, hash_str=""):
    """优先用 Socket_2 已记录的缓存；再按 名字+hash 查；没有才新建。"""
    ref = get_modifier_socket_value(mod, OBJ_SOCKET)
    
    if ref is not None and ref.type == 'MESH' and ref.name.endswith(CACHE_SUFFIX):
        return ref
    name = get_cache_name(obj.name, hash_str)
    cache = bpy.data.objects.get(name)
    if cache is None:
        mesh = bpy.data.meshes.new(name)
        cache = bpy.data.objects.new(name, mesh)
    return cache


def get_target_modifier(obj):
    """仅当当前所选修改器是几何节点修改器且节点树为 edit_mesh_modifier 时才视为找到。"""
    if not obj:
        return None
    mod = obj.modifiers.active          # 当前所选修改器（UI 里高亮那个）
    if mod is not None and mod.type == 'NODES' and mod.node_group and mod.node_group.name == NG_EDIT:
        return mod
    return None

def generate_unique_hash(obj):
    """生成不冲突的 8 位哈希。"""
    while True:
        h = uuid.uuid4().hex[:8]
        if get_cache_name(obj.name, h) not in bpy.data.objects:
            return h

def bake_cache(context, obj, cache_obj, target, hash_str=""):
    """屏蔽目标及下游修改器，临时加【保存数据】节点烘焙后写入缓存物体。"""
    # 清理可能残留的临时【保存数据】修改器
    for m in list(obj.modifiers):
        if m.type == 'NODES' and m.node_group and m.node_group.name == NG_SAVE:
            obj.modifiers.remove(m)

    t_index = obj.modifiers.find(target.name)
    total = len(obj.modifiers)

    saved = []
    for i in range(t_index, total):
        m = obj.modifiers[i]
        saved.append((m, m.show_viewport))
        m.show_viewport = False

    temp = obj.modifiers.new(MOD_TEMP_NAME, 'NODES')
    temp.node_group = bpy.data.node_groups[NG_SAVE]
    temp.show_manage_panel = False
    temp.show_group_selector = False

    try:
        depsgraph = context.evaluated_depsgraph_get()
        depsgraph.update()
        eval_obj = obj.evaluated_get(depsgraph)
        eval_mesh = eval_obj.to_mesh()
        if eval_mesh:
            old = cache_obj.data
            new = eval_mesh.copy()
            cache_obj.data = new
            if old is not new:
                try:
                    if old.users <= 1:
                        bpy.data.meshes.remove(old)
                except Exception:
                    pass
            try:
                new.name = get_cache_name(obj.name, hash_str)
            except Exception:
                pass
        eval_obj.to_mesh_clear()
    finally:
        if temp.name in obj.modifiers:
            obj.modifiers.remove(temp)
        for m, state in saved:
            try:
                m.show_viewport = state
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 操作符
# ---------------------------------------------------------------------------
class EDITMESH_OT_Build(bpy.types.Operator):
    bl_idname = "editmesh.build"
    bl_label = "Build Edit Poly Modifier"  # 构建【编辑多边形修改器】
    bl_options = {'REGISTER', 'UNDO'}
    
    data: bpy.props.StringProperty(options={'SKIP_SAVE'})
    mode: bpy.props.EnumProperty(
        name="Mode",  # 模式
        items=[
            ('BUILD', "Create", "Create an Edit Poly modifier and build its cache"),  # 新建 / 新建编辑多边形修改器并构建缓存
            ('REBUILD', "Rebuild", "Rebuild the cache of the currently selected modifier"),  # 重建 / 重建当前选中修改器的缓存
            ('REHASH', "Fork", "Recalculate the hash and its cache"),  # 独立化 / 重新计算哈希值及缓存
        ],default='REBUILD')

    @classmethod
    def description(cls, context, properties):
        return _i18n.pget_tmpl(properties.data)

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == 'MESH'

    def invoke(self, context, event):
        if event.ctrl or event.shift or event.alt:
            self.mode = 'REHASH'
        return self.execute(context)
        
    def execute(self, context):
        obj = context.object
        try:
            if not refresh_node_groups():
                raise RuntimeError(_i18n.pget_tmpl("Cannot load node groups, please check {file}", file=os.path.basename(LIB_PATH)))  # 无法加载节点组，请检查 {file}
            
            if self.mode == 'BUILD':
                """BUILD：在活动修改器下方新建一个编辑多边形修改器。"""
                # 新建修改器
                target = obj.modifiers.new(MOD_EDIT_NAME, 'NODES')
                target.node_group = bpy.data.node_groups[NG_EDIT]
                target.show_manage_panel = False
                target.show_group_selector = False
                
                # 写入唯一哈希
                h = generate_unique_hash(obj)
                set_modifier_socket_value(target, HASH_SOCKET, h)   # 写入唯一哈希
                
                # 新建缓存物体
                name = get_cache_name(obj.name, h)
                mesh = bpy.data.meshes.new(name)
                cache = bpy.data.objects.new(name, mesh)

                # 构建缓存
                set_modifier_socket_value(target, OBJ_SOCKET, cache)
                bake_cache(context, obj, cache, target, h)
                
            elif self.mode == 'REBUILD':
                """REBUILD：重建当前选中修改器，不改哈希。"""
                # 以选中的修改器为待操作项
                target = get_target_modifier(obj)
                if target is None:
                    raise RuntimeError(_i18n.pget_tmpl("Please select an Edit Poly modifier first"))  # 请先选中一个编辑多边形修改器
                
                # 旧修改器如果缺失哈希时，自动补哈希
                h = get_modifier_socket_value(target, HASH_SOCKET)
                if not h:
                    h = generate_unique_hash(obj)
                    set_modifier_socket_value(target, HASH_SOCKET, h)
                
                # 尝试获取 Socket_2
                name = get_cache_name(obj.name, h)
                socket_obj = get_modifier_socket_value(target, OBJ_SOCKET)
                # 尝试获取 满足哈希的物体
                hash_obj = bpy.data.objects.get(name)
                if socket_obj is not None and socket_obj.type == 'MESH' and socket_obj.name.endswith(CACHE_SUFFIX):
                    # 优先获取插槽物体
                    cache = socket_obj
                elif hash_obj is not None:
                    # 次选满足哈希的物体
                    cache = hash_obj
                else:
                    # 最终保底新建
                    mesh = bpy.data.meshes.new(name)
                    cache = bpy.data.objects.new(name, mesh)
                
                # 构建缓存
                set_modifier_socket_value(target, OBJ_SOCKET, cache)
                bake_cache(context, obj, cache, target, h)

            elif self.mode == 'REHASH':
                """REHASH：重建当前哈希，不改网格"""
                # 以选中的修改器为待操作项
                target = get_target_modifier(obj)
                if target is None:
                    raise RuntimeError(_i18n.pget_tmpl("Please select an Edit Poly modifier first"))  # 请先选中一个编辑多边形修改器

                # 重新生成唯一哈希
                h = generate_unique_hash(obj)
                set_modifier_socket_value(target, HASH_SOCKET, h)
                
                # 重新获取缓存物体名称
                new_name = get_cache_name(obj.name, h)
                socket_obj = get_modifier_socket_value(target, OBJ_SOCKET)

                if socket_obj is not None and socket_obj.type == 'MESH' and socket_obj.name.endswith(CACHE_SUFFIX):
                    # 优先获取插槽物体
                    new_mesh = socket_obj.data.copy()
                    new_mesh.name = new_name
                    cache = bpy.data.objects.new(new_name, new_mesh)
                    set_modifier_socket_value(target, OBJ_SOCKET, cache)

                else:
                    # 保底新建
                    mesh = bpy.data.meshes.new(new_name)
                    cache = bpy.data.objects.new(new_name, mesh)
                    # 构建缓存
                    set_modifier_socket_value(target, OBJ_SOCKET, cache)
                    bake_cache(context, obj, cache, target, h)
                
            else:
                raise RuntimeError(_i18n.pget_tmpl("Unsupported mode; this should never happen"))  # 未受支持的模式，理论上这不该发生

        except Exception as e:
            self.report({'ERROR'}, _i18n.pget_tmpl("Build failed: {e}", e=str(e)))  # 构建失败: {e}
            return {'CANCELLED'}
        
        self.report({'INFO'}, _i18n.pget_tmpl("Build complete"))  # 构建完成
        return {'FINISHED'}


def _get_view3d_spaces(context):
    """获取屏幕上所有 3D 视图空间。"""
    spaces = []
    if context.screen:
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                spaces.append(area.spaces.active)
    return spaces

class EDITMESH_OT_Edit(bpy.types.Operator):
    bl_idname = "editmesh.edit"
    bl_label = "Edit"  # 编辑
    bl_description = "Directly edit mesh data while keeping upstream modifiers intact"  # 在保留上游修改器的基础上，直接进行网格数据编辑
    bl_options = {'REGISTER'}

    _timer = None
    _src_obj = None
    _cache_obj = None
    _overlay_states = []

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == 'MESH'

    def execute(self, context):
        src = context.object

        target = get_target_modifier(src)
        if target is None:
            self.report({'ERROR'}, _i18n.pget_tmpl("The selected modifier is not an Edit Poly modifier. Run Build first"))  # 当前所选修改器不是【编辑多边形修改器】，请先执行【构建】
            return {'CANCELLED'}

        cache = get_modifier_socket_value(target, OBJ_SOCKET)
        if cache is None or cache.type != 'MESH':
            self.report({'ERROR'}, _i18n.pget_tmpl("The modifier has no valid cache object. Run Build first"))  # 修改器未记录有效的缓存物体，请先执行【构建】
            return {'CANCELLED'}

        self._src_obj = src
        self._cache_obj = cache
        # 记录并打开所有 3D 视图的重拓扑覆盖
        self._overlay_states = []
        for sp in _get_view3d_spaces(context):
            self._overlay_states.append((sp, sp.overlay.show_retopology))
            sp.overlay.show_retopology = True

        try:
            bpy.ops.object.mode_set(mode='OBJECT')
            for coll in list(cache.users_collection):
                coll.objects.unlink(cache)
            if context.scene:
                context.scene.collection.objects.link(cache)
            for o in list(context.selected_objects):
                o.select_set(False)

            cache.select_set(True)
            context.view_layer.objects.active = cache

            cache.matrix_world = src.matrix_world.copy()

            bpy.ops.object.mode_set(mode='EDIT')

            wm = context.window_manager
            if context.window:
                self._timer = wm.event_timer_add(0.1, window=context.window)
                wm.modal_handler_add(self)
            if context.area:
                context.area.tag_redraw()
        except Exception as e:
            self._cleanup(context)
            self.report({'ERROR'}, _i18n.pget_tmpl("Failed to enter edit mode: {e}", e=str(e)))  # 进入编辑模式失败: {e}
            return {'CANCELLED'}
        if self._timer is not None:
            return {'RUNNING_MODAL'}
        return {'FINISHED'}

    def modal(self, context, event):
        try:
            if event.type == 'TIMER':
                if context.mode != 'EDIT_MESH' or context.object is not self._cache_obj:
                    self._cleanup(context)
                    return {'FINISHED'}
        except Exception:
            self._cleanup(context)
            return {'FINISHED'}
        return {'PASS_THROUGH'}

    def _cleanup(self, context):
        """清理退出：回物体模式、unlink 缓存、恢复原物体为活动。"""
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

        for sp, state in getattr(self, '_overlay_states', []):
            try:
                sp.overlay.show_retopology = state
            except Exception:
                pass
        self._overlay_states = []

        cache = self._cache_obj
        if _object_alive(cache):
            for coll in list(cache.users_collection):
                try:
                    coll.objects.unlink(cache)
                except Exception:
                    pass
            cache.location = (0.0, 0.0, 0.0)
            cache.rotation_euler = (0.0, 0.0, 0.0)
            cache.scale = (1.0, 1.0, 1.0)

        src = self._src_obj
        if _object_alive(src):
            for o in list(context.selected_objects):
                try:
                    o.select_set(False)
                except Exception:
                    pass
            src.select_set(True)
            if context.view_layer:
                context.view_layer.objects.active = src

        if self._timer is not None:
            wm = context.window_manager
            try:
                wm.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
def modifier_add_menu_draw(self, context):
    layout = self.layout
    obj = context.object
    if obj and obj.type == 'MESH':
        layout.separator()
        # 编辑多边形修改器
        op = layout.operator(EDITMESH_OT_Build.bl_idname, text="Edit Poly Modifier", icon='EDITMODE_HLT')
        # 创建一个【编辑多边形修改器】，你可以借助它，在不应用上游修改器的前提下，直接编辑多边形
        op.data = "Create an Edit Poly modifier that lets you edit polygons directly without applying upstream modifiers"
        op.mode = 'BUILD'

def draw_socket_input(layout, mod, key, text="", icon='NONE'):
    """按版本绘制 socket 输入控件（5.1 用 ID 属性路径，5.2 用新 API）。"""
    if mod is None:
        return None
    if bpy.app.version >= (5, 2):
        sock = getattr(mod.properties.inputs, key, None)
        if sock is not None:
            return layout.prop(sock, "value", text=text, icon=icon)
        return None
    return layout.prop(mod, f'["{key}"]', text=text, icon=icon)

def draw_example(layout):
    """绘制"位置自动修正"原理说明（面板与偏好设置共用）。"""
    col = layout.column(align=True)

    col.label(text="When Auto Position Fix is enabled and upstream modifiers keep the vertex count,")  # 【位置自动修正】启用时，如果上游修改器没有增减顶点数量
    col.label(text="upstream edits are still applied perfectly after Edit Polygons, for example:")  # 【编辑多边形】后，仍能完美传递上游修改内容，例如：

    minibox = col.box()
    minicol = minibox.column(align=True)
    minirow = minicol.row(align=True)
    minirow.label(text="Shrinkwrap Modifier", icon="MOD_SHRINKWRAP")  # 缩裹修改器
    minirow.label(text="", icon="GRIP")
    minirow = minicol.row(align=True)
    minirow.label(text="Solidify Modifier", icon="MOD_SOLIDIFY")  # 实体化修改器
    minirow.label(text="", icon="GRIP")
    minirow = minicol.row(align=True)
    minirow.label(text="Bevel Modifier", icon="MOD_BEVEL")  # 倒角修改器
    minirow.label(text="", icon="GRIP")
    minirow = minicol.row(align=True)
    minirow.label(text="Edit Poly Modifier", icon="STRIP_COLOR_01")  # 编辑多边形修改器
    minirow.label(text="", icon="GRIP")
    minirow = minicol.row(align=True)
    minirow.label(text="Subdivision Modifier", icon="MOD_SUBSURF")  # 细分修改器
    minirow.label(text="", icon="GRIP")

    col.label(text="Even after editing with Edit Polygons, you can still:")  # 哪怕【编辑多边形】编辑后，你仍可以：

    minibox = col.box()
    minicol = minibox.column(align=True)
    minicol.label(text="Adjust parameters such as the Shrinkwrap offset", icon="MOD_SHRINKWRAP")  # 修改缩裹的偏移量等参数
    minicol.label(text="Adjust parameters such as the Solidify thickness", icon="MOD_SOLIDIFY")  # 修改实体化的厚度等参数
    minicol.label(text="Adjust parameters such as the Bevel radius", icon="MOD_BEVEL")  # 修改倒角的半径等参数
    minicol.label(text="Edit Poly Modifier", icon="STRIP_COLOR_01")  # 编辑多边形修改器
    minicol.label(text="All of these changes are picked up by downstream modifiers", icon="MOD_SUBSURF")  # 以上的所有修改都会让下游识别

class MODIFIER_PT_EditMeshModifier(bpy.types.Panel):
    bl_label = ""
    bl_idname = "MODIFIER_PT_EditMeshModifier"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "modifier"
    bl_options = {'HEADER_LAYOUT_EXPAND','DEFAULT_CLOSED'} # 默认闭合
    
    @classmethod
    def poll(cls, context):
        # 在物体上查找节点组为 "edit_mesh_modifier" 的几何节点修改器
        obj = context.object
        if not obj:
            return False
        for mod in obj.modifiers:
            if mod.type == 'NODES' and mod.node_group and mod.node_group.name == NG_EDIT:
                return mod
        return False

    def draw_header(self, context):
        layout = self.layout
        row = layout.row()#align=True

        mod = get_target_modifier(context.object)
        if  mod:
            row.label(text="", icon='EDITMODE_HLT')
            row.label(text = f"【{mod.name}】")
            
            op = row.operator(EDITMESH_OT_Build.bl_idname, text="", icon='FILE_REFRESH')
            # 【左键】重建已编辑内容：重建当前修改器的的已编辑内容 / 【ctrl+左键】重建修改器哈希：当你带修改器复制网格时，能帮助你将该修改器独立化
            op.data = "LMB Rebuild edits: rebuild the edited content of the current modifier\nCtrl+LMB Rehash: when you copy an object with the modifier, use this to make the modifier independent"
            op.mode = 'REBUILD'
            
            red_row = row.row()
            red_row.alert = True
            # 编辑多边形
            red_row.operator(EDITMESH_OT_Edit.bl_idname, text="Edit Polygons", icon='EDITMODE_HLT')
            socket_icon = 'UV_SYNC_SELECT' if get_modifier_socket_value(mod, AUTO_FIX_SOCKET) else 'FREEZE'
            draw_socket_input(row, mod, AUTO_FIX_SOCKET, text="", icon=socket_icon)
            row.label(text="", icon='BLANK1') #icon
        else:
            row.label(text="", icon='EDITMODE_HLT')
            gray_row = row.row()
            # 请选择任意【编辑多边形修改器】进行编辑
            gray_row.label(text="Please select an Edit Poly modifier to edit")
            gray_row.active = False
            
    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.label(text="Instructions", icon='INFO')  # 说明
        col.label(text="You can edit the mesh without applying modifiers")  # 你可以在不应用修改器的前提下
        col.label(text="Directly edit the mesh on top of upstream modifiers")  # 在上游修改器的基础上，直接对网格进行编辑
        col.separator(type="LINE")
        col.label(text="Select an Edit Poly modifier, then click Edit Polygons in the header")  # 选中任一【编辑多边形修改器】后、点击标题栏的【编辑多边形】即可

        mod = get_target_modifier(context.object)
        if  mod:
            row = col.row(align=True)
            op = row.operator(EDITMESH_OT_Build.bl_idname, text="Build Cache", icon='FILE_REFRESH')  # 构建缓存
            # 【左键】重建已编辑内容：重建当前修改器的的已编辑内容 / 【ctrl+左键】重建修改器哈希：当你带修改器复制网格时，能帮助你将该修改器独立化
            op.data = "LMB Rebuild edits: rebuild the edited content of the current modifier\nCtrl+LMB Rehash: when you copy an object with the modifier, use this to make the modifier independent"
            op.mode = 'REBUILD'
            
            # 编辑多边形
            row.operator(EDITMESH_OT_Edit.bl_idname, text="Edit Polygons", icon='EDITMODE_HLT')
            socket_icon = 'UV_SYNC_SELECT' if get_modifier_socket_value(mod, AUTO_FIX_SOCKET) else 'FREEZE'
            draw_socket_input(row, mod, AUTO_FIX_SOCKET, text="Auto Position Fix", icon=socket_icon)  # 位置自动修正
        else:
            col.label(text="Note: buttons are only visible when an Edit Poly modifier is selected",icon="QUESTION")  # 注意，按钮仅当选中【编辑多边形修改器】后可见
            
        draw_example(layout.box())

class EditMeshModifierPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.label(text="Instructions", icon='INFO')  # 说明
        col.label(text="You can edit the mesh without applying modifiers")  # 你可以在不应用修改器的前提下
        col.label(text="Directly edit the mesh on top of upstream modifiers")  # 在上游修改器的基础上，直接对网格进行编辑
        col.separator(type="LINE")
        
        col.label(text="How to Access", icon='RESTRICT_VIEW_OFF')  # 功能入口
        col.label(text="Go to the Properties Editor > Modifiers tab")  # 请前往【属性编辑器界面】》【修改器属性】
        col.label(text="Click Add Modifier > Edit to find the Edit Poly Modifier at the bottom of the panel")  # 点击【添加修改器】》【编辑】：即可在面板底部找到【编辑多边形修改器】
        col.label(text="Click Add Modifier > Generate to find the Edit Poly Modifier at the bottom of the panel")  # 点击【添加修改器】》【生成】：即可在面板底部找到【编辑多边形修改器】
        col.separator(type="LINE")

        draw_example(layout)


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------
CLASSES = (
    EDITMESH_OT_Build,
    EDITMESH_OT_Edit,
    MODIFIER_PT_EditMeshModifier,
    EditMeshModifierPreferences,
)


def register():
    _i18n.register()
    
    for cls in CLASSES:
        bpy.utils.register_class(cls)

    bpy.types.OBJECT_MT_modifier_add_edit.append(modifier_add_menu_draw)
    bpy.types.OBJECT_MT_modifier_add_generate.append(modifier_add_menu_draw)


def unregister():
    _i18n.unregister()

    bpy.types.OBJECT_MT_modifier_add_edit.remove(modifier_add_menu_draw)
    bpy.types.OBJECT_MT_modifier_add_generate.remove(modifier_add_menu_draw)
    
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
