"""StreamKnife 配方库存储模块

与 config/settings.json 完全独立，默认路径：<程序目录>/config/recipes.json

文件结构::

    // 注释行会被忽略
    {
      "recipes": [
        {
          "name": "常用处理链",
          "saved_at": "2026-11-17 14:00:00",
          "items": [
            {
              "key": "case_convert",      // 插件文件名（不含 .py）
              "name": "大小写转换",        // 仅用于显示
              "enabled": true,             // false 表示临时禁用
              "config": {"mode": "转小写"} // 保存时的参数
            }
          ]
        }
      ]
    }
"""

import json
import os
import sys
from datetime import datetime

RECIPE_FILENAME = "recipes.json"

_COMMENT_HEADER = """// StreamKnife 配方库配置文件
// 可在此手动编辑，也可通过主界面的“配方库”按钮自动维护
//
// recipes[].name   : 配方名称
// recipes[].items  : 按顺序执行的插件列表
//   key            : 插件文件名（不含 .py）
//   name           : 插件显示名称
//   enabled        : false 表示临时禁用，执行配方时跳过
//   config         : 保存配方时该插件的参数
"""


def _get_config_dir() -> str:
    """可写的配置目录：exe 所在目录（frozen）或脚本工作目录"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(".")


class RecipeStore:
    """配方库文件读写。"""

    def __init__(self):
        self._filepath = os.path.join(_get_config_dir(), "config", RECIPE_FILENAME)
        self._recipes = []
        self._load()

    @property
    def filepath(self) -> str:
        return self._filepath

    # ── 读写 ──────────────────────────────────────────

    def _load(self):
        """读取配方文件，忽略 // 注释行与格式损坏的内容。"""
        try:
            with open(self._filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()

            clean = [
                line
                for line in lines
                if line.strip() and not line.strip().startswith("//")
            ]
            data = json.loads("".join(clean))
        except Exception:
            self._recipes = []
            return

        recipes = data.get("recipes", []) if isinstance(data, dict) else []
        self._recipes = [
            recipe
            for recipe in recipes
            if isinstance(recipe, dict) and isinstance(recipe.get("name"), str) and recipe["name"]
        ]

    def reload(self):
        self._load()

    def save(self):
        os.makedirs(os.path.dirname(self._filepath), exist_ok=True)
        body = json.dumps(
            {"recipes": self._recipes}, ensure_ascii=False, indent=2, default=str
        )
        with open(self._filepath, "w", encoding="utf-8") as f:
            f.write(_COMMENT_HEADER + body + "\n")

    def ensure_file(self):
        """配置文件不存在时创建空配方库。"""
        if not os.path.exists(self._filepath):
            self.save()

    # ── 配方管理 ──────────────────────────────────────

    def list_recipes(self):
        return list(self._recipes)

    def get(self, name: str):
        for recipe in self._recipes:
            if recipe["name"] == name:
                return recipe
        return None

    def save_recipe(self, name: str, items: list):
        """新增或覆盖同名配方。"""
        recipe = {
            "name": name,
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "items": items,
        }

        for index, existing in enumerate(self._recipes):
            if existing["name"] == name:
                self._recipes[index] = recipe
                break
        else:
            self._recipes.append(recipe)

        self.save()
        return recipe

    def delete_recipe(self, name: str) -> bool:
        remaining = [recipe for recipe in self._recipes if recipe["name"] != name]

        if len(remaining) == len(self._recipes):
            return False

        self._recipes = remaining
        self.save()
        return True
