# 翻译注册模块。
# 源码为英文：英文 UI 直接显示源码，无需翻译；
# 中文 UI 通过 zh_HANS.py 的"英 → 中"字典显示中文，其它语言回落为英文源码。

import bpy

from . import zh_HANS
from . import ja_JP

TRANSLATION_DOMAIN = "edit_mesh_modifier"

# 操作符标签以 "Operator" 为 context 查找（"*" 不兜底），故都注册；
# 额外注册本插件的操作符/面板 idname 作兜底（部分场合 Blender 用 idname 查找）
_UI_CONTEXTS = ("*", "Operator",
                "edit_mesh_modifier.add", "edit_mesh_modifier.build", "edit_mesh_modifier.edit",
                "edit_mesh_modifier.shape_key", "edit_mesh_modifier.toggle_edit",
                "EDIT_MESH_MODIFIER_PT_Main")


def _build_translations(data: dict, lang: str) -> dict:
    """把 {英文: 中文} 转为 bpy.app.translations 的 {(context, msgid): 译文} 格式。"""
    out = {}
    for src, dst in data.items():
        for ctx in _UI_CONTEXTS:
            out[(ctx, src)] = dst
    return {lang: out}


def register():
    combined = {}
    if zh_HANS.data:
        for lang in ("zh_CN", "zh_HANS"):
            combined.update(_build_translations(zh_HANS.data, lang))
    combined.update(_build_translations(ja_JP.data, "ja_JP"))
    if combined:
        try:
            bpy.app.translations.register(TRANSLATION_DOMAIN, combined)
        except ValueError:
            pass


def unregister():
    try:
        bpy.app.translations.unregister(TRANSLATION_DOMAIN)
    except ValueError:
        pass


def pget_tmpl(template: str, **kwargs) -> str:
    """翻译模板字符串并插值参数后组装返回。
    用法: pget_tmpl("Build failed: {e}", e=str(e))
    """
    ctx = bpy.app.translations.pgettext
    translated_kwargs = {k: ctx(str(v)) for k, v in kwargs.items()}
    return ctx(template).format(**translated_kwargs)
