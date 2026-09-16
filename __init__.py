

bl_info = {
    "name": "Edit Poly Modifier [编辑多边形修改器]",  # 编辑多边形修改器
    "author": "RARA",
    "version": (1, 0, 15),
    "blender": (4, 2, 0),
    'doc_url': 'https://github.com/tantaka-tan/edit_mesh_modifier#readme',
    "location": "Properties > Modifiers Tab",  # 属性面板 > 修改器页签
    "description": "Edit the mesh via a cache object, applied in real time",  # 通过缓存物体编辑网格，并将编辑结果实时应用到原物体
    "category": "Object",
}

import json  # noqa: E402
import os  # noqa: E402
import bpy  # noqa: E402
import uuid  # noqa: E402
from . import translation as _i18n  # noqa: E402
from . import edit_access  # noqa: E402
from . import edit_preview  # noqa: E402
from .edit_access import EDIT_MESH_MODIFIER_OT_ToggleEdit  # noqa: E402
from .shape_keys import EDIT_MESH_MODIFIER_OT_ShapeKey, EDIT_MESH_MODIFIER_MT_ShapeKey  # noqa: E402

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

# 缓存网格上的点属性（节点组烘焙写入的基础信息）
ATTR_BASE = "cache_base"     # 布尔：该点是否属于基础网格
ATTR_IDX = "cache_idx"       # 整数：基础网格的原始顶点索引
ATTR_POS = "cache_pos"       # 矢量：基础网格的原始位置
ATTR_JSON = "idx_pos_cache"  # 字符串：编辑前的 JSON 备份（编辑期间保护）

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

    temp = None
    try:
        # 临时加【保存数据】节点修改器（整个流程包进 try，任何一步失败都会走 finally 清理）
        temp = obj.modifiers.new(MOD_TEMP_NAME, 'NODES')
        temp.node_group = bpy.data.node_groups[NG_SAVE]
        if hasattr(target, "show_manage_panel"): #简化面板5.0以上才有
            temp.show_manage_panel = False
        temp.show_group_selector = False

        depsgraph = context.evaluated_depsgraph_get()
        depsgraph.update()
        eval_obj = obj.evaluated_get(depsgraph)
        eval_mesh = None
        try:
            eval_mesh = eval_obj.to_mesh()
            if eval_mesh:
                old = cache_obj.data
                new = eval_mesh.copy()
                cache_obj.data = new
                # The cache already contains evaluated coordinates. Inherited
                # shape keys may have the pre-modifier topology and deform it again.
                if new.shape_keys is not None:
                    cache_obj.shape_key_clear()
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
                # bake 后立即把关键点属性快照进字符串属性（"隐形保险柜"），
                # 编辑模式不再重复备份；SYNC 更新基准后由 SYNC 路径单独刷新
                try:
                    backup_point_attrs(new)
                except Exception:
                    pass
        finally:
            # 无论拷贝成功与否，都释放评估网格，避免泄漏
            if eval_mesh is not None:
                try:
                    eval_obj.to_mesh_clear()
                except Exception:
                    pass
    finally:
        if temp is not None and temp.name in obj.modifiers:
            obj.modifiers.remove(temp)
        for m, state in saved:
            try:
                m.show_viewport = state
            except Exception:
                pass


def backup_point_attrs(mesh):
    """编辑前把 cache_base/cache_idx/cache_pos 备份进 idx_pos_cache 字符串属性。

    字符串属性几乎不会被编辑操作触碰，作为关键属性的"隐形保险柜"。
    字符串属性的赋值类型按实际 API 处理，不依赖版本号。
    """
    base = mesh.attributes.get(ATTR_BASE)
    idx = mesh.attributes.get(ATTR_IDX)
    pos = mesh.attributes.get(ATTR_POS)
    if base is None or idx is None or pos is None:
        return
    n = len(mesh.vertices)
    sa = mesh.attributes.get(ATTR_JSON)
    if sa is not None and len(sa.data) != n:
        mesh.attributes.remove(sa)
        sa = None
    if sa is None:
        sa = mesh.attributes.new(ATTR_JSON, "STRING", "POINT")
    # Adding/removing a layer can invalidate existing Attribute RNA references.
    base = mesh.attributes[ATTR_BASE]
    idx = mesh.attributes[ATTR_IDX]
    pos = mesh.attributes[ATTR_POS]
    d = sa.data
    for i in range(n):
        payload = json.dumps({
            "base": bool(base.data[i].value),
            "idx": int(idx.data[i].value),
            "pos": [round(c, 6) for c in pos.data[i].vector],
        })
        # Some 4.2 builds already require bytes; use the runtime API contract.
        try:
            d[i].value = payload.encode()
        except TypeError:
            d[i].value = payload


def restore_point_attrs(mesh):
    """编辑后从 idx_pos_cache 恢复 cache_base/cache_idx/cache_pos。

    仅对"非空且符合 JSON 规范"的顶点写回；其余顶点保持原值。
    """
    sa = mesh.attributes.get(ATTR_JSON)
    if sa is None or len(sa.data) != len(mesh.vertices):
        return
    base = mesh.attributes.get(ATTR_BASE)
    idx = mesh.attributes.get(ATTR_IDX)
    pos = mesh.attributes.get(ATTR_POS)
    if base is None or idx is None or pos is None:
        return
    n = len(mesh.vertices)
    bases = [False] * n
    idxs = [0] * n
    poss = [0.0] * (n * 3)
    base.data.foreach_get("value", bases)
    idx.data.foreach_get("value", idxs)
    pos.data.foreach_get("vector", poss)
    for i in range(n):
        raw = sa.data[i].value
        if not raw:
            continue
        # 4.4+ 为 bytes；4.2/4.3 为 str，统一转成 str 再解析
        if isinstance(raw, bytes):
            raw = raw.decode()
        try:
            rec = json.loads(raw)
        except Exception:
            continue
        if not isinstance(rec, dict):
            continue
        bases[i] = bool(rec.get("base", bases[i]))
        idxs[i] = int(rec.get("idx", idxs[i]))
        p = rec.get("pos")
        if isinstance(p, (list, tuple)) and len(p) == 3:
            poss[i * 3] = float(p[0])
            poss[i * 3 + 1] = float(p[1])
            poss[i * 3 + 2] = float(p[2])
    base.data.foreach_set("value", bases)
    idx.data.foreach_set("value", idxs)
    pos.data.foreach_set("vector", poss)
    mesh.update_tag()



def sync_upstream_to_cache(context, obj, cache_obj, target):
    """在上游顶点位置变化时，同步更新缓存物体，保留已有的编辑偏移。"""
    # 1. 获取上游最新网格（禁用目标及下游修改器）
    t_index = obj.modifiers.find(target.name)
    if t_index == -1:
        return False, f"Modifier '{target.name}' not found on object."
        
    saved_states = []
    for i in range(t_index, len(obj.modifiers)):
        m = obj.modifiers[i]
        saved_states.append((m, m.show_viewport))
        m.show_viewport = False

    _eval_obj = None
    upstream_mesh = None
    try:
        depsgraph = context.evaluated_depsgraph_get()
        depsgraph.update()
        _eval_obj = obj.evaluated_get(depsgraph)
        upstream_mesh = _eval_obj.to_mesh()

        if not upstream_mesh:
            return False, "Upstream mesh invalid."

        # --- 核心逻辑变更：直接获取上游所有顶点的坐标列表 ---
        num_up = len(upstream_mesh.vertices)
        up_coords = [0.0] * (num_up * 3)
        upstream_mesh.vertices.foreach_get("co", up_coords)

        # 2. 获取 Cache 物体的数据和属性
        cache_mesh = cache_obj.data
        cache_idx_attr = cache_mesh.attributes.get(ATTR_IDX)
        cache_pos_attr = cache_mesh.attributes.get(ATTR_POS)
        
        if not cache_idx_attr or not cache_pos_attr:
            return False, "Cache object is missing internal attributes (idx/pos). Please Rebuild."

        n_ca = len(cache_mesh.vertices)
        
        # 获取 Cache 记录的“原始索引”（即它对应上游哪个点）
        my_ids = [0] * n_ca
        cache_idx_attr.data.foreach_get("value", my_ids)
        
        # 获取 Cache 记录的“旧基准位置”
        old_base_poss = [0.0] * (n_ca * 3)
        cache_pos_attr.data.foreach_get("vector", old_base_poss)
        
        # 获取 Cache 当前的顶点位置（包含用户之前的编辑）
        current_cos = [0.0] * (n_ca * 3)
        cache_mesh.vertices.foreach_get("co", current_cos)

        # 3. 执行匹配同步
        new_base_poss = [0.0] * (n_ca * 3) # 用于更新 cache_pos 属性
        
        for i in range(n_ca):
            # target_idx 是这个 Cache 顶点对应的上游顶点索引
            target_idx = my_ids[i]
            idx = i * 3
            
            # 检查索引是否在上游范围内（防止上游删减了顶点导致越界）
            if 0 <= target_idx < num_up:
                # 找到上游对应点的坐标
                up_idx = target_idx * 3
                tx = up_coords[up_idx]
                ty = up_coords[up_idx + 1]
                tz = up_coords[up_idx + 2]
                
                # 计算位移增量 (当前上游位置 - 上次记录的基准位置)
                dx = tx - old_base_poss[idx]
                dy = ty - old_base_poss[idx+1]
                dz = tz - old_base_poss[idx+2]
                
                # 将增量叠加到 Cache 顶点上
                current_cos[idx]   += dx
                current_cos[idx+1] += dy
                current_cos[idx+2] += dz
                
                # 记录新的基准位置，供下次同步使用
                new_base_poss[idx]   = tx
                new_base_poss[idx+1] = ty
                new_base_poss[idx+2] = tz
            else:
                # 如果上游找不到这个索引（点被删了），保持原样
                new_base_poss[idx]   = old_base_poss[idx]
                new_base_poss[idx+1] = old_base_poss[idx+1]
                new_base_poss[idx+2] = old_base_poss[idx+2]

        # 4. 写回数据
        cache_mesh.vertices.foreach_set("co", current_cos)
        cache_pos_attr.data.foreach_set("vector", new_base_poss)
        
        cache_mesh.update()
        return True, "Sync successful (Index-Pointer mode)"

    except Exception as e:
        return False, f"Unexpected error during sync: {str(e)}"
        
    finally:
        # 释放评估网格，避免任何路径泄漏
        if upstream_mesh is not None and _eval_obj is not None:
            try:
                _eval_obj.to_mesh_clear()
            except Exception:
                pass
        # 恢复修改器状态
        for m, state in saved_states:
            try:
                m.show_viewport = state
            except Exception:
                pass

              

# ---------------------------------------------------------------------------
# 操作符
# ---------------------------------------------------------------------------
class EDIT_MESH_MODIFIER_OT_Add(bpy.types.Operator):
    bl_idname = "edit_mesh_modifier.add"
    bl_label = "Add Edit Poly Modifier"  # 新建编辑多边形修改器
    bl_options = {'REGISTER', 'UNDO'}

    data: bpy.props.StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, properties):
        return _i18n.pget_tmpl(properties.data)

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == 'MESH'

    def execute(self, context):
        """在活动修改器下方新建一个编辑多边形修改器并构建缓存。"""
        obj = context.object
        try:
            if not refresh_node_groups():
                raise RuntimeError(_i18n.pget_tmpl("Cannot load node groups, please check {file}", file=os.path.basename(LIB_PATH)))  # 无法加载节点组，请检查 {file}

            target = obj.modifiers.new(MOD_EDIT_NAME, 'NODES')
            target.node_group = bpy.data.node_groups[NG_EDIT]
            if hasattr(target, "show_manage_panel"): #简化面板5.0以上才有
                target.show_manage_panel = False  # 默认关闭简化面板
            target.show_group_selector = False  # 默认关闭避免用户误触，改为别的节点了
            target.show_in_editmode = False  # 默认关闭，否则编辑模式编辑原始网格时，会很怪异

            # 写入唯一哈希
            h = generate_unique_hash(obj)
            set_modifier_socket_value(target, HASH_SOCKET, h)

            # 新建缓存物体
            name = get_cache_name(obj.name, h)
            mesh = bpy.data.meshes.new(name)
            cache = bpy.data.objects.new(name, mesh)

            # 构建缓存
            set_modifier_socket_value(target, OBJ_SOCKET, cache)
            bake_cache(context, obj, cache, target, h)
        except Exception as e:
            self.report({'ERROR'}, _i18n.pget_tmpl("Build failed: {e}", e=str(e)))  # 构建失败: {e}
            return {'CANCELLED'}

        self.report({'INFO'}, _i18n.pget_tmpl("Build complete"))  # 构建完成
        return {'FINISHED'}


class EDIT_MESH_MODIFIER_OT_Build(bpy.types.Operator):
    bl_idname = "edit_mesh_modifier.build"
    bl_label = "Build Edit Poly Modifier"  # 构建【编辑多边形修改器】
    bl_options = {'REGISTER', 'UNDO'}
    
    data: bpy.props.StringProperty(options={'SKIP_SAVE'})
    mode: bpy.props.EnumProperty(
        name="Mode",  # 模式
        items=[
            ('REBUILD', "Rebuild", "Rebuild the cache of the currently selected modifier"),  # 重建 / 重建当前选中修改器的缓存
            ('REHASH', "Fork", "Recalculate the hash and its cache"),  # 独立化 / 重新计算哈希值及缓存
            ('SYNC', "Sync Upstream", "Sync upstream vertex position changes to cache while keeping edits"),
        ], default='REBUILD')

    @classmethod
    def description(cls, context, properties):
        return _i18n.pget_tmpl(properties.data)

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == 'MESH'

    def invoke(self, context, event):
        if event.shift:
            self.mode = 'REHASH'
        elif event.ctrl:
            self.mode = 'REBUILD'
        else:
            self.mode = 'SYNC'
        return self.execute(context)
        
    def execute(self, context):
        obj = context.object
        target = None
        
        try:
            if not refresh_node_groups():
                raise RuntimeError(_i18n.pget_tmpl("Cannot load node groups, please check {file}", file=os.path.basename(LIB_PATH)))  # 无法加载节点组，请检查 {file}
            
            if self.mode == 'REBUILD':
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
                    # 绑定新缓存后再清理旧缓存，避免孤儿物体/网格泄漏
                    _remove_cache_object(socket_obj)

                else:
                    # 保底新建
                    mesh = bpy.data.meshes.new(new_name)
                    cache = bpy.data.objects.new(new_name, mesh)
                    # 构建缓存
                    set_modifier_socket_value(target, OBJ_SOCKET, cache)
                    bake_cache(context, obj, cache, target, h)

            elif self.mode == 'SYNC':
                target = get_target_modifier(obj)
                if target is None:
                    raise RuntimeError(_i18n.pget_tmpl("Please select an Edit Poly modifier first"))  # 请先选中一个编辑多边形修改器

                cache = get_modifier_socket_value(target, OBJ_SOCKET)
                if cache is None or cache.type != 'MESH':
                    raise RuntimeError("No valid cache object found to sync")
                
                # 执行同步
                success, message = sync_upstream_to_cache(context, obj, cache, target)
                
                if success:
                    # SYNC 更新了 cache_pos 基准，必须刷新字符串快照，
                    # 否则下次编辑恢复时会回退到 bake 时的旧基准
                    backup_point_attrs(cache.data)
                    self.report({'INFO'}, f"Edit Poly: {message}")
                else:
                    raise RuntimeError(f"Sync failed: {message}")
                    
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

def _mesh_geom_snapshot(mesh):
    """返回网格几何的轻量指纹，用于判断编辑期间是否产生了实际改动。"""
    n_vert = len(mesh.vertices)
    co = [0.0] * (n_vert * 3)
    mesh.vertices.foreach_get("co", co)
    return (n_vert, len(mesh.edges), len(mesh.polygons), round(sum(co), 3))

def _sync_new_vertex_groups_to_source(cache_obj, src_obj):
    """把 cache 上有而原始网格没有的顶点组，以同名空组补到原始网格。

    仅在退出编辑时按组名求差集，不迁移权重（新建的是空组）；
    原始网格已有同名组时跳过，避免覆盖原有权重。
    返回 True 表示至少补建了一个组。
    """
    if cache_obj is None or src_obj is None:
        return False
    try:
        if cache_obj.type != 'MESH' or src_obj.type != 'MESH':
            return False
        src_names = {vg.name for vg in src_obj.vertex_groups}
        added = False
        for vg in cache_obj.vertex_groups:
            if vg.name not in src_names:
                src_obj.vertex_groups.new(name=vg.name)
                src_names.add(vg.name)
                added = True
        return added
    except Exception:
        return False

_EDIT_SYMMETRY_PROPERTIES = ('use_mirror_x', 'use_mirror_y', 'use_mirror_z', 'use_mirror_topology')


def _get_edit_symmetry(obj):
    return {name: getattr(obj.data, name) for name in _EDIT_SYMMETRY_PROPERTIES}


def _set_edit_symmetry(obj, settings):
    for name, value in settings.items():
        setattr(obj.data, name, value)


class EDIT_MESH_MODIFIER_OT_Edit(bpy.types.Operator):
    bl_idname = "edit_mesh_modifier.edit"
    bl_label = "Edit"  # 编辑
    bl_description = "Directly edit mesh data while keeping upstream modifiers intact"  # 在保留上游修改器的基础上，直接进行网格数据编辑
    bl_options = {'REGISTER'}

    _timer = None
    _src_obj = None
    _cache_obj = None
    _overlay_states = []
    _cache_display_state = None
    _cache_symmetry_state = None
    _symmetry_started = False
    _preview_obj = None
    _snapshot = None
    _src_hidden = None
    _src_view_layer = None

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
        self._src_hidden = None
        self._src_view_layer = context.view_layer
        
        
        # Standard appearance preserves the user's existing viewport settings.
        self._overlay_states = []
        self._cache_display_state = None
        self._cache_symmetry_state = None
        self._symmetry_started = False
        self._preview_obj = None

        try:
            bpy.ops.object.mode_set(mode='OBJECT')
            self._preview_obj = edit_preview.create(context, src, cache, target)
            if self._preview_obj is not None:
                cache = self._preview_obj
                self._cache_obj = cache
            entry = context.preferences.addons.get(__name__)
            standard_appearance = entry is None or entry.preferences.standard_edit_appearance
            if standard_appearance:
                properties = ('color', 'display_type', 'show_in_front', 'show_wire', 'show_all_edges')
                self._cache_display_state = {
                    name: tuple(cache.color) if name == 'color' else getattr(cache, name)
                    for name in properties
                }
                for name in properties:
                    setattr(cache, name, getattr(src, name))
            else:
                for sp in _get_view3d_spaces(context):
                    self._overlay_states.append((sp, sp.overlay.show_retopology))
                    sp.overlay.show_retopology = True

            for coll in list(cache.users_collection):
                coll.objects.unlink(cache)
            if context.scene:
                context.scene.collection.objects.link(cache)
            for o in list(context.selected_objects):
                o.select_set(False)

            cache.select_set(True)
            context.view_layer.objects.active = cache

            cache.matrix_world = src.matrix_world.copy()

            # 【自动同步上游】勾选后，进入编辑前先把上游修改器的变化同步进缓存
            try:
                pref = bpy.context.preferences.addons[__name__].preferences
                auto_sync = pref.auto_sync_upstream
            except Exception:
                auto_sync = False
            if auto_sync:
                success, message = sync_upstream_to_cache(context, src, cache, target)
                if success:
                    # 同步改变了 cache_pos 基准，刷新字符串快照
                    try:
                        backup_point_attrs(cache.data)
                    except Exception:
                        pass
                else:
                    self.report({'INFO'}, f"Edit Poly: Auto sync skipped - {message}")

            # 记录几何快照（同步之后的坐标作为编辑前基准），用于退出时判断是否真的发生了编辑
            try:
                self._snapshot = _mesh_geom_snapshot(cache.data)
            except Exception:
                self._snapshot = None

            # Hide only in the editing view layer; keep render visibility intact.
            self._src_hidden = src.hide_get(view_layer=self._src_view_layer)
            src.hide_set(True, view_layer=self._src_view_layer)
            # Mesh symmetry is an editing setting, independent of appearance.
            self._cache_symmetry_state = _get_edit_symmetry(cache)
            _set_edit_symmetry(cache, _get_edit_symmetry(src))
            bpy.ops.object.mode_set(mode='EDIT')
            self._symmetry_started = True

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

    def cancel(self, context):
        self._cleanup(context)

    def _restore_source_visibility(self):
        if self._src_hidden is not None and _object_alive(self._src_obj):
            try:
                self._src_obj.hide_set(self._src_hidden, view_layer=self._src_view_layer)
            except (ReferenceError, RuntimeError):
                pass
        self._src_hidden = None
        self._src_view_layer = None

    def _cleanup(self, context):
        """清理退出：回物体模式、unlink 缓存、恢复原物体为活动。"""
        # Restore before other cleanup steps, including error/cancellation paths.
        self._restore_source_visibility()
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
            try:
                if getattr(self, '_symmetry_started', False) and _object_alive(self._src_obj):
                    # Keep header/Topology Mirror changes for normal editing and
                    # the next Edit Poly stage, without copying mesh geometry.
                    _set_edit_symmetry(self._src_obj, _get_edit_symmetry(cache))
                elif getattr(self, '_cache_symmetry_state', None) is not None:
                    _set_edit_symmetry(cache, self._cache_symmetry_state)
            except (ReferenceError, RuntimeError):
                pass
        self._cache_symmetry_state = None
        self._symmetry_started = False
        if _object_alive(cache) and self._cache_display_state is not None:
            for name, value in self._cache_display_state.items():
                try:
                    setattr(cache, name, value)
                except (ReferenceError, RuntimeError):
                    pass
        self._cache_display_state = None
        if _object_alive(cache):
            # 退出编辑后从字符串备份恢复关键点属性（尽力而为）
            try:
                restore_point_attrs(cache.data)
            except Exception:
                pass
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

        # 退出编辑后：若用户在编辑中给缓存新增了顶点组，则以同名空组补到原始网格
        groups_added = False
        if _object_alive(cache) and _object_alive(src):
            groups_added = _sync_new_vertex_groups_to_source(cache, src)
            raw = edit_preview.raw_cache(cache)
            if raw is not None:
                _sync_new_vertex_groups_to_source(cache, raw)

        # 仅当编辑期间产生了实际几何改动或新增了顶点组时才推撤销点，避免污染撤销栈
        snapshot = getattr(self, '_snapshot', None)
        if snapshot is not None and _object_alive(cache):
            try:
                changed = _mesh_geom_snapshot(cache.data) != snapshot
            except Exception:
                changed = False
        else:
            changed = False
        edit_preview.remove(getattr(self, '_preview_obj', None))
        if getattr(self, '_preview_obj', None) is not None:
            self._cache_obj = None
        self._preview_obj = None
        if changed or groups_added:
            bpy.ops.ed.undo_push(message="Exit Edit Poly")

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
        op = layout.operator(EDIT_MESH_MODIFIER_OT_Add.bl_idname, text="Edit Poly Modifier", icon='EDITMODE_HLT')
        # 创建一个【编辑多边形修改器】，你可以借助它，在不应用上游修改器的前提下，直接编辑多边形
        op.data = "Create an Edit Poly modifier that lets you edit polygons directly without applying upstream modifiers"

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

class EDIT_MESH_MODIFIER_PT_Main(bpy.types.Panel):
    bl_label = ""
    bl_idname = "EDIT_MESH_MODIFIER_PT_Main"
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
            
            op = row.operator(EDIT_MESH_MODIFIER_OT_Build.bl_idname, text="", icon='FILE_REFRESH')
            # 【左键】同步上游 / 【ctrl+左键】重建已编辑内容 / 【shift+左键】独立化（复制物体后换新哈希）
            op.data = "LMB Sync Upstream: sync upstream modifier changes into the cache while keeping edits\nCtrl+LMB Rebuild: rebuild the edited content of the current modifier\nShift+LMB Rehash: generate a new hash to fork the modifier, e.g. after duplicating"
            op.mode = 'REBUILD'
            
            red_row = row.row()
            red_row.alert = True
            # 编辑多边形
            red_row.operator(EDIT_MESH_MODIFIER_OT_Edit.bl_idname, text="Edit Polygons", icon='EDITMODE_HLT')
            row.menu("EDIT_MESH_MODIFIER_MT_ShapeKey", text="", icon='SHAPEKEY_DATA')
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
            op = row.operator(EDIT_MESH_MODIFIER_OT_Build.bl_idname, text="Build Cache", icon='FILE_REFRESH')  # 构建缓存
            # 【左键】同步上游 / 【ctrl+左键】重建已编辑内容 / 【shift+左键】独立化（复制物体后换新哈希）
            op.data = "LMB Sync Upstream: sync upstream modifier changes into the cache while keeping edits\nCtrl+LMB Rebuild: rebuild the edited content of the current modifier\nShift+LMB Rehash: generate a new hash to fork the modifier, e.g. after duplicating"
            op.mode = 'REBUILD'
            
            # 编辑多边形
            row.operator(EDIT_MESH_MODIFIER_OT_Edit.bl_idname, text="Edit Polygons", icon='EDITMODE_HLT')
            socket_icon = 'UV_SYNC_SELECT' if get_modifier_socket_value(mod, AUTO_FIX_SOCKET) else 'FREEZE'
            draw_socket_input(row, mod, AUTO_FIX_SOCKET, text="Auto Position Fix", icon=socket_icon)  # 位置自动修正
            col.menu("EDIT_MESH_MODIFIER_MT_ShapeKey", text="Shape Keys", icon='SHAPEKEY_DATA')
        else:
            col.label(text="Note: buttons are only visible when an Edit Poly modifier is selected",icon="QUESTION")  # 注意，按钮仅当选中【编辑多边形修改器】后可见
            
        draw_example(layout.box())

class EDIT_MESH_MODIFIER_Preferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    standard_edit_appearance: bpy.props.BoolProperty(
        name="Use Standard Edit Mode Appearance",
        description="Keep normal viewport overlays and use the source object's display color and settings; disable for the previous retopology display",
        default=True,
    )

    show_in_mode_pie: bpy.props.BoolProperty(
        name="Show Edit Poly in Mode Pie",
        description="Add Edit Poly to the standard mode-switch pie menu (Ctrl+Tab)",
        default=True,
    )

    auto_edit_polygons: bpy.props.BoolProperty(
        name="Automatically Enter Edit Polygons",
        description="Entering Edit Mode with an Edit Poly modifier selected opens its cache instead of the source mesh",
        default=True,
        update=edit_access.update_auto_edit,
    )

    auto_rehash: bpy.props.BoolProperty(
        name="Auto Rehash on Duplicate",
        description="Automatically generate a new hash and cache when an object is duplicated (Shift+D)",
        default=True
    )

    auto_sync_upstream: bpy.props.BoolProperty(
        name="Auto Sync Upstream",
        description="Automatically sync upstream modifier changes into the cache before entering Edit Polygons",
        default=False
    )
    
    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        # 性能与自动化设置
        box = col.box()
        box.label(text="Automation & Performance", icon='SETTINGS')
        box.prop(self, "auto_rehash")
        box.prop(self, "auto_sync_upstream")
        box = col.box()
        box.label(text="Edit Mode Access", icon='EDITMODE_HLT')
        box.prop(self, "show_in_mode_pie")
        box.prop(self, "auto_edit_polygons")
        box.prop(self, "standard_edit_appearance")
        edit_access.draw_preferences(col, context)
        
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


# 自动独立化
_is_system_ready = True
_known_objects = {}   # {obj.as_pointer(): obj.name}，识别"自上次更新以来新增"的物体

@bpy.app.handlers.persistent
def on_load_pre(dummy):
    """当点击‘打开文件’的一瞬间，立即锁定系统"""
    global _is_system_ready
    _is_system_ready = False

@bpy.app.handlers.persistent
def on_load_post(dummy):
    """文件加载完成后，开启定时器准备解锁"""
    # 延迟时间建议 0.5 ~ 1.0 秒即可，3秒太久了
    bpy.app.timers.register(enable_sync_after_load, first_interval=1.0)

def enable_sync_after_load():
    global _is_system_ready
    global _known_objects
    # 新文件环境：重置已登记物体表，防止旧文件残留导致误判
    _known_objects = {}
    _is_system_ready = True
    return None

def _is_new_object(obj):
    """判断 obj 是否为自上次 depsgraph 更新以来新出现的物体。"""
    ptr = obj.as_pointer()
    if _known_objects.get(ptr) == obj.name:
        return False
    _known_objects[ptr] = obj.name
    return True

def _cache_referenced_by_other(cache_obj):
    """检查缓存物体是否仍被其他【编辑多边形】修改器引用（复制场景会共享）。"""
    if cache_obj is None:
        return False
    for o in bpy.data.objects:
        if o is cache_obj:
            continue
        for mod in o.modifiers:
            if mod.type == 'NODES' and mod.node_group and mod.node_group.name == NG_EDIT:
                ref = get_modifier_socket_value(mod, OBJ_SOCKET)
                if ref is not None and ref.name == cache_obj.name:
                    return True
    return False

def _remove_cache_object(cache_obj):
    """安全删除缓存物体及其独占的网格。

    仅当旧缓存不再被任何修改器引用时才删除，避免复制共享场景下破坏原物体。
    """
    if cache_obj is None:
        return
    if _cache_referenced_by_other(cache_obj):
        return
    try:
        mesh = cache_obj.data
        bpy.data.objects.remove(cache_obj, do_unlink=True)
        if mesh is not None and mesh.users <= 0:
            bpy.data.meshes.remove(mesh, do_unlink=True)
    except Exception:
        pass

def rehash_modifier_instance(obj, mod, old_hash):
    """执行具体的独立化逻辑：换哈希、拷数据"""
    new_h = generate_unique_hash(obj)
    set_modifier_socket_value(mod, HASH_SOCKET, new_h)

    # 获取旧的缓存物体（副本目前还指向它）
    old_cache = get_modifier_socket_value(mod, OBJ_SOCKET)

    new_name = get_cache_name(obj.name, new_h)

    if old_cache and old_cache.type == 'MESH':
        # 重要：克隆原有的编辑数据，而不是新建空的
        new_mesh = old_cache.data.copy()
        new_mesh.name = new_name
        new_cache = bpy.data.objects.new(new_name, new_mesh)
    else:
        # 如果没找到旧缓存，则新建空的
        new_mesh = bpy.data.meshes.new(new_name)
        new_cache = bpy.data.objects.new(new_name, new_mesh)

    set_modifier_socket_value(mod, OBJ_SOCKET, new_cache)
    # 绑定新缓存后再清理旧缓存，避免孤儿物体/网格泄漏
    _remove_cache_object(old_cache)
    print(f"Edit Poly: Object '{obj.name}' has been automatically rehashed.")

def auto_rehash_duplicates(candidates):
    """对候选新增物体做哈希冲突检查，冲突则自动独立化。"""
    if not candidates:
        return

    # 建立当前场景的哈希索引（仅在新物体出现时执行，低频）
    seen_hashes = {}
    for obj in bpy.context.view_layer.objects:
        if obj.type != 'MESH' or edit_preview.is_preview(obj):
            continue
        for mod in obj.modifiers:
            if mod.type == 'NODES' and mod.node_group and mod.node_group.name == NG_EDIT:
                h = get_modifier_socket_value(mod, HASH_SOCKET)
                if h and h not in seen_hashes:
                    seen_hashes[h] = obj

    # 逐个检查候选，仅处理哈希冲突的副本
    for obj in candidates:
        try:
            if obj.name not in bpy.data.objects or obj.type != 'MESH' or edit_preview.is_preview(obj):
                continue
        except ReferenceError:
            continue
        for mod in obj.modifiers:
            if mod.type == 'NODES' and mod.node_group and mod.node_group.name == NG_EDIT:
                h = get_modifier_socket_value(mod, HASH_SOCKET)
                if not h:
                    continue
                if h in seen_hashes:
                    if seen_hashes[h] is not obj:
                        rehash_modifier_instance(obj, mod, h)
                else:
                    seen_hashes[h] = obj

@bpy.app.handlers.persistent
def depsgraph_handler(scene, depsgraph):
    """依赖图句柄：只关注新增物体，避免每帧全量扫描。"""
    global _is_system_ready
    if not _is_system_ready:
        return
    # 确保 context 可用后再读取偏好设置
    try:
        pref = bpy.context.preferences.addons[__name__].preferences
    except Exception:
        return
    if not pref.auto_rehash:
        return

    candidates = []
    seen_ptrs = set()
    try:
        for update in depsgraph.updates:
            id_data = update.id
            # 5.1 起 DepsgraphUpdate 不再提供 id_type，直接用 rna 类型判断
            if not isinstance(id_data, bpy.types.Object):
                continue
            obj = getattr(id_data, "original", id_data)
            if obj is None or obj.type != 'MESH' or edit_preview.is_preview(obj):
                continue
            ptr = obj.as_pointer()
            if ptr in seen_ptrs:
                continue
            seen_ptrs.add(ptr)
            if _is_new_object(obj):
                candidates.append(obj)
    except Exception:
        return
    if candidates:
        # 用 Timer 延迟执行，避开 depsgraph 锁定状态
        bpy.app.timers.register(
            lambda: auto_rehash_duplicates(candidates),
            first_interval=0.01)

    
    
    
    
    
    

# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------
CLASSES = (
    EDIT_MESH_MODIFIER_OT_Add,
    EDIT_MESH_MODIFIER_OT_Build,
    EDIT_MESH_MODIFIER_OT_Edit,
    EDIT_MESH_MODIFIER_OT_ToggleEdit,
    EDIT_MESH_MODIFIER_OT_ShapeKey,
    EDIT_MESH_MODIFIER_MT_ShapeKey,
    EDIT_MESH_MODIFIER_PT_Main,
    EDIT_MESH_MODIFIER_Preferences,
)


def register():
    _i18n.register()
    
    for cls in CLASSES:
        bpy.utils.register_class(cls)

    edit_access.register()

    bpy.types.OBJECT_MT_modifier_add_edit.append(modifier_add_menu_draw)
    bpy.types.OBJECT_MT_modifier_add_generate.append(modifier_add_menu_draw)

    # 绑定加载前后的句柄
    if on_load_pre not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(on_load_pre)
    if on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(on_load_post)
    # 注册句柄
    if depsgraph_handler not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(depsgraph_handler)
    # 初始化物体计数

    
def unregister():
    edit_access.unregister()
    _i18n.unregister()

    bpy.types.OBJECT_MT_modifier_add_edit.remove(modifier_add_menu_draw)
    bpy.types.OBJECT_MT_modifier_add_generate.remove(modifier_add_menu_draw)

    if on_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(on_load_pre)
    if on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(on_load_post)
    # 移除句柄
    if depsgraph_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(depsgraph_handler)
        
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
