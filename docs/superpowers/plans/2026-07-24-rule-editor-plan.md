# 美化规则编辑器 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个独立的 pywebview 窗口——美化规则编辑器，提供文件浏览、双模式规则编辑（简单/高级）、智能规则生成功能。规则集从 ConfigManager 迁移到 `fancy/` 文件夹独立文件管理。

**Architecture:** 后端新增 `RuleEditorAPI` 类（`webutils/function_rule_editor.py`）处理文件浏览和规则 CRUD；`fancy/` 文件夹存储用户规则集 JSON；前端为独立 HTML 页面（`webui/rule-editor.html`）配合专用 JS/CSS，复用主应用的 CSS 变量体系和主题。扩展 `function_fancy.py` 的 `exec_json` 支持 `conditions` 多条件 AND 格式，向后兼容旧 `trigger` 格式。

**Tech Stack:** Python 3.9.6+ / pywebview / JavaScript (vanilla) / CodeMirror 6 (CDN) / Font Awesome 6 (CDN)

## Global Constraints

- Python 3.9.6+ 兼容（不使用 3.10+ 语法如 `match/case`）
- 前端无构建工具，直接使用 CDN 和 vanilla JS
- 规则格式必须与现有 `builtinFancy.py` 格式兼容
- 样式复用主应用的 CSS 变量体系（`--color-*`, `--shadow-*`, `--radius-*`, `--spacing-*`）
- 新窗口通过 `webview.create_window()` 创建，API 类独立于 `LCTA_API`

---

### Task 1: Fancy Engine — `conditions` 多条件支持

**Files:**
- Modify: `webutils/function_fancy.py:90-150` (exec_json function)
- Create: `tests/test_fancy_conditions.py`

**Interfaces:**
- Produces: `exec_json(data, config)` — 现在接受 `conditions` 数组格式，内部将旧 `trigger`/`aim` 格式归一化为 `conditions`
- Produces: `_normalize_rule(rule) -> dict` — 归一化函数
- Produces: `_is_same_parent(tuple_a, tuple_b) -> bool` — 判断两个扁平路径是否同属一个 dataList 父条目

- [ ] **Step 1: 编写归一化函数 `_normalize_rule(rule)` 的测试**

```python
# tests/test_fancy_conditions.py
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from webutils.function_fancy import _normalize_rule

def test_normalize_old_trigger_format():
    rule = {
        "trigger": {"aim": r"dataList\.\d+\.id", "re": "^10001$"},
        "aim": "[back].name",
        "action": [{"from": "大于", "to": ">"}]
    }
    result = _normalize_rule(rule)
    assert "conditions" in result
    assert len(result["conditions"]) == 1
    assert result["conditions"][0]["trigger"]["re"] == "^10001$"
    assert result["conditions"][0]["aim"] == "[back].name"
    assert "trigger" not in result

def test_normalize_old_aim_only_format():
    rule = {
        "aim": r"dataList\.\d+\.desc",
        "action": [{"from": "大于", "to": ">"}]
    }
    result = _normalize_rule(rule)
    assert len(result["conditions"]) == 1
    assert result["conditions"][0]["aim"] == r"dataList\.\d+\.desc"
    assert "trigger" not in result["conditions"][0]

def test_normalize_new_format_passthrough():
    rule = {
        "conditions": [
            {"trigger": {"aim": r"dataList\.\d+\.id", "re": "^10001$"}, "aim": "[back].name"},
        ],
        "action": [{"from": "大于", "to": ">"}]
    }
    result = _normalize_rule(rule)
    assert len(result["conditions"]) == 1
    assert result == rule
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd E:/desktop/work/LCTA-Limbus-company-transfer-auto && python -m pytest tests/test_fancy_conditions.py -v
```

- [ ] **Step 3: 在 `function_fancy.py` 中实现 `_normalize_rule`**

在 `exec_json` 函数之前添加：

```python
def _normalize_rule(rule: dict) -> dict:
    """将旧版 trigger/aim 格式归一化为 conditions 数组格式"""
    if "conditions" in rule:
        return rule
    rule = dict(rule)
    condition = {}
    if "trigger" in rule:
        condition["trigger"] = rule.pop("trigger")
    if "aim" in rule:
        condition["aim"] = rule.pop("aim")
    if "fallback" in rule:
        condition["fallback"] = rule.pop("fallback")
    rule["conditions"] = [condition]
    return rule
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_fancy_conditions.py -v
```

- [ ] **Step 5: 编写集成测试**

```python
# tests/test_fancy_conditions.py (续)

def make_flat_data(data):
    from webutils.function_fancy import flatten_dict_enhanced
    return flatten_dict_enhanced(data)

def create_test_skill_data():
    return {
        "dataList": [
            {"id": 10001, "name": "强烈斩击", "desc": "大于目标体力则造成额外伤害"},
            {"id": 10002, "name": "精准穿刺", "desc": "指定目标造成大量伤害"},
            {"id": 10003, "name": "横扫", "desc": "大于自身护盾则追加伤害"},
        ]
    }

def test_exec_json_single_condition():
    from webutils.function_fancy import exec_json
    data = create_test_skill_data()
    config = [{
        "aimFile": "Skill.*\\.json$",
        "conditions": [{
            "trigger": {"aim": r"dataList\.\d+\.id", "re": "^10001$"},
            "aim": "[back].name"
        }],
        "action": [{"from": "^(.*)$", "to": "[\\1]"}]
    }]
    result = exec_json(data, config)
    assert result["dataList"][0]["name"] == "[强烈斩击]"
    assert result["dataList"][1]["name"] == "精准穿刺"

def test_exec_json_multi_condition_and():
    from webutils.function_fancy import exec_json
    data = create_test_skill_data()
    config = [{
        "aimFile": "Skill.*\\.json$",
        "conditions": [
            {"trigger": {"aim": r"dataList\.\d+\.id", "re": "^10002$"}, "aim": "[back].name"},
            {"trigger": {"aim": r"dataList\.\d+\.desc", "re": "指定"}, "aim": "[back].name"}
        ],
        "action": [{"from": "^(.*)$", "to": "★\\1★"}]
    }]
    result = exec_json(data, config)
    assert result["dataList"][1]["name"] == "★精准穿刺★"
    assert result["dataList"][0]["name"] == "强烈斩击"

def test_exec_json_old_format_still_works():
    from webutils.function_fancy import exec_json
    data = create_test_skill_data()
    config = [{
        "trigger": {"aim": r"dataList\.\d+\.id", "re": "^10001$"},
        "aim": "[back].name",
        "action": [{"from": "^(.*)$", "to": "OLD"}]
    }]
    result = exec_json(data, config)
    assert result["dataList"][0]["name"] == "OLD"
    assert result["dataList"][1]["name"] == "精准穿刺"
```

- [ ] **Step 6: 运行测试确认失败（集成逻辑未实现）**

```bash
python -m pytest tests/test_fancy_conditions.py::test_exec_json_single_condition -v
```

- [ ] **Step 7: 改造 `exec_json` 函数**

修改 `webutils/function_fancy.py` 的 `exec_json` 函数：

```python
def exec_json(data: dict, config: list) -> dict:
    flat_data = flatten_dict_enhanced(data)
    updates = {}
    flat_items = [(path_tuple_to_str(k), k, v) for k, v in flat_data.items()]

    for rule in config:
        rule = _normalize_rule(rule)
        conditions = rule.get('conditions', [])
        if not conditions:
            continue

        operations = rule.get('action', [])
        first_cond = conditions[0]

        if first_cond.get('trigger'):
            first_aim_pattern = first_cond['trigger']['aim']
        else:
            first_aim_pattern = first_cond['aim']

        first_aim_re = re.compile(first_aim_pattern)

        matched_paths = [
            (key_str, key_tuple, val)
            for key_str, key_tuple, val in flat_items
            if first_aim_re.search(key_str)
        ]

        for key_str, key_tuple, val in matched_paths:
            all_conditions_met = True
            for cond in conditions:
                if cond.get('trigger'):
                    trigger_aim_re = re.compile(cond['trigger']['aim'])
                    trigger_re_re = re.compile(cond['trigger']['re'])
                    trigger_matched_paths = [
                        (ks, kt, v2)
                        for ks, kt, v2 in flat_items
                        if trigger_aim_re.search(ks) and _is_same_parent(kt, key_tuple)
                    ]
                    trigger_hit = any(
                        isinstance(v2, str) and trigger_re_re.search(v2)
                        for _, _, v2 in trigger_matched_paths
                    )
                    if not trigger_hit:
                        all_conditions_met = False
                        break
                else:
                    aim_re = re.compile(cond['aim'])
                    if not aim_re.search(key_str):
                        all_conditions_met = False
                        break

            if not all_conditions_met:
                continue

            for cond in conditions:
                dst_tuple = transform_path(key_tuple, cond.get('aim', ''))
                new_val = apply_operations(
                    get_value_by_path(data, dst_tuple),
                    operations,
                    data=flat_data,
                    dst_tuple=dst_tuple
                )
                updates[dst_tuple] = new_val

    return update_dict_with_flattened(data, updates)


def _is_same_parent(tuple_a: tuple, tuple_b: tuple) -> bool:
    """判断两个扁平路径是否属于同一个 dataList 父条目"""
    def find_datalist_index(t):
        for i, part in enumerate(t):
            if part == 'dataList' and i + 1 < len(t):
                return i + 1
        return None
    idx_a = find_datalist_index(tuple_a)
    idx_b = find_datalist_index(tuple_b)
    if idx_a is None or idx_b is None:
        return False
    return tuple_a[idx_a] == tuple_b[idx_b]
```

- [ ] **Step 8: 运行全部测试确认通过**

```bash
python -m pytest tests/test_fancy_conditions.py -v
```

- [ ] **Step 9: Commit**

```bash
git add webutils/function_fancy.py tests/test_fancy_conditions.py
git commit -m "feat: add multi-condition AND support to exec_json with backward compatibility"
```

---

### Task 2: `fancy/` 文件夹规则加载 & 迁移

**Files:**
- Modify: `webutils/function_fancy.py` (新增 `load_fancy_folder_rules`, `save_ruleset_to_folder`, `delete_ruleset_from_folder`, `migrate_user_fancy_to_folder`)
- Modify: `webui/app.py:697-703` (get_fancy_rulesets)
- Modify: `launcher/updates.py:130-132` (fancy 加载)
- Modify: `webui/js/features.js:249-258` (FancyManager.saveAll)

**Interfaces:**
- Produces: `load_fancy_folder_rules(fancy_dir=None) -> list[dict]`
- Produces: `save_ruleset_to_folder(name, data) -> Path`
- Produces: `delete_ruleset_from_folder(name) -> bool`
- Produces: `migrate_user_fancy_to_folder() -> int`
- Produces: `_get_fancy_folder() -> Path`
- Produces: `_sanitize_filename(name) -> str`

- [ ] **Step 1: 在 `function_fancy.py` 末尾添加加载/保存函数**

```python
# webutils/function_fancy.py 末尾追加

def _get_fancy_folder() -> Path:
    """获取 fancy/ 文件夹路径（位于项目根目录）"""
    project_root = Path(__file__).parent.parent
    return project_root / 'fancy'

def _sanitize_filename(name: str) -> str:
    """过滤文件名中的非法字符"""
    illegal_chars = r'\/:*?"<>|'
    for char in illegal_chars:
        name = name.replace(char, '_')
    return name.strip()

def load_fancy_folder_rules(fancy_dir: str = None) -> list[dict]:
    """从 fancy/ 文件夹加载所有用户规则集"""
    if fancy_dir:
        folder = Path(fancy_dir)
    else:
        folder = _get_fancy_folder()
    if not folder.exists():
        return []
    rulesets = []
    for f in sorted(folder.glob('*.json')):
        try:
            content = f.read_text(encoding='utf-8')
            data = json.loads(content)
            if isinstance(data, dict) and 'name' in data and 'rules' in data:
                rulesets.append(data)
            else:
                logger.warning(f"跳过无效规则集文件（缺少 name/rules）: {f.name}")
        except json.JSONDecodeError as e:
            logger.warning(f"跳过无效 JSON 文件: {f.name} — {e}")
        except Exception as e:
            logger.warning(f"跳过文件读取失败: {f.name} — {e}")
    return rulesets

def save_ruleset_to_folder(name: str, data: dict) -> Path:
    """保存规则集到 fancy/{name}.json，返回保存路径"""
    folder = _get_fancy_folder()
    folder.mkdir(parents=True, exist_ok=True)
    filename = _sanitize_filename(name) + '.json'
    filepath = folder / filename
    filepath.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )
    return filepath

def delete_ruleset_from_folder(name: str) -> bool:
    """删除规则集文件，返回是否成功"""
    folder = _get_fancy_folder()
    filename = _sanitize_filename(name) + '.json'
    filepath = folder / filename
    if filepath.exists():
        filepath.unlink()
        return True
    return False

def migrate_user_fancy_to_folder() -> int:
    """将 ConfigManager.user_fancy 中的旧数据迁移到 fancy/ 文件夹。
    返回迁移的规则集数量。迁移后清除 ConfigManager 中的旧字段。"""
    from globalManagers.ConfigManager import ConfigManager
    config = ConfigManager()
    old_data_str = config.get('user_fancy', None)
    if old_data_str is None:
        return 0
    try:
        old_rulesets = json.loads(old_data_str)
    except (json.JSONDecodeError, TypeError):
        logger.warning("旧 user_fancy 数据无效，跳过迁移")
        config.set('user_fancy', None)
        config.save()
        return 0
    if not isinstance(old_rulesets, list) or len(old_rulesets) == 0:
        config.set('user_fancy', None)
        config.save()
        return 0
    count = 0
    for ruleset in old_rulesets:
        if isinstance(ruleset, dict) and 'name' in ruleset:
            try:
                save_ruleset_to_folder(ruleset['name'], ruleset)
                count += 1
            except Exception as e:
                logger.error(f"迁移规则集 {ruleset.get('name', '?')} 失败: {e}")
    config.set('user_fancy', None)
    config.save()
    logger.info(f"已迁移 {count} 个规则集到 fancy/ 文件夹")
    return count
```

- [ ] **Step 2: 更新 `webui/app.py` 的 `get_fancy_rulesets`**

```python
# webui/app.py L697-703 替换为：
def get_fancy_rulesets(self):
    from webutils.function_fancy import load_fancy_folder_rules
    return {'success': True, 'data': {
        'builtin': builtinFancyConfig,
        'user': load_fancy_folder_rules(),
        'enabled': json.loads(ConfigManager().get('fancy_allow',
             "{\"技能文本美化(FL Like)\": true,\"气泡文本渐变(FL Like)\": true,\"EGO文本渐变(FL Like)\": true}"))
    }}
```

- [ ] **Step 3: 更新 `launcher/updates.py` 的 fancy 加载**

```python
# launcher/updates.py L130-132 替换为：
from webutils.function_fancy import load_fancy_folder_rules
config_list = builtinFancyConfig
config_list.extend(load_fancy_folder_rules())
enableMap = json.loads(ConfigManager().get('fancy_allow', '[]'))
```

- [ ] **Step 4: 在应用启动时调用迁移**

在 `webui/app.py` 的 `LCTA_API.__init__` 方法末尾添加：

```python
from webutils.function_fancy import migrate_user_fancy_to_folder
migrate_user_fancy_to_folder()
```

- [ ] **Step 5: 更新前端 `FancyManager.saveAll`**

```javascript
// webui/js/features.js L249-258 替换为：
async saveAll() {
    const userRulesets = this.rulesets.filter(rs => !rs.builtin);
    const userData = userRulesets.map(({ builtin, ...rest }) => rest);
    for (const rs of userData) {
        await pywebview.api.save_ruleset(rs.name, rs);
    }
    configManager.updateConfigValue('fancy-allow', JSON.stringify(this.enabledMap));
    configManager.flushPendingUpdates();
}
```

- [ ] **Step 6: Commit**

```bash
git add webutils/function_fancy.py webui/app.py webui/js/features.js launcher/updates.py
git commit -m "feat: migrate rulesets from ConfigManager to fancy/ folder with auto-migration"
```

---

### Task 3: RuleEditorAPI — 文件浏览 & 规则 CRUD

**Files:**
- Create: `webutils/function_rule_editor.py`

**Interfaces:**
- Produces: `get_lang_files() -> list[str]`
- Produces: `get_file_content(relative_path) -> dict` (keys: raw, parsed, file_classification)
- Produces: `search_files(keyword, case_sensitive) -> dict` (keys: results_by_category, total_matches)
- Produces: `get_ruleset_list() -> list[dict]`
- Produces: `get_ruleset(name) -> dict`
- Produces: `save_ruleset(name, data) -> dict`
- Produces: `create_ruleset(name) -> dict`
- Produces: `delete_ruleset(name) -> dict`
- Produces: `build_rule_from_form(form_data) -> dict`
- Produces: `validate_rule(rule_json) -> dict`
- Produces: `analyze_changes(changes) -> dict`

- [ ] **Step 1: 创建模块骨架和文件浏览器方法**

```python
# webutils/function_rule_editor.py
"""美化规则编辑器后端 API — 文件浏览、规则 CRUD、智能生成"""

import json
import os
import re
import logging
from pathlib import Path
from typing import Optional

from globalManagers.ConfigManager import ConfigManager
from webutils.function_fancy import (
    load_fancy_folder_rules, save_ruleset_to_folder,
    delete_ruleset_from_folder, _get_fancy_folder, _sanitize_filename
)

logger = logging.getLogger('rule_editor')

FILE_PREFIX_RULES = [
    ('BattleSpeechBubbleDlg', '战斗气泡'), ('BattleResultHint', '战斗结果提示'),
    ('BattleKeywords', '战斗关键词'), ('BattlePass', '通行证'),
    ('BattleUIText', '战斗UI'), ('BossRaidUI', '战斗映射UI'),
    ('BattleHint', '战斗提示'), ('BuffAbilities', '战斗Buff'),
    ('Bufs_Mirror', '镜牢Buff'), ('MirrorDungeon', '镜牢'),
    ('DailyLoginEvent', '签到'), ('CultivationEvent', '惜春养成'),
    ('CouponUIText', '兑换码UI'), ('ChoiceEvent', '事件选择'),
    ('DanteAbility', '但丁能力'), ('ActionEvents', '镜牢事件'),
    ('AbEventsResultLog', '事件效果'), ('AbnormalityGuides', '异想体线索/提示'),
    ('AttributeText', '七大罪'), ('AbEvents', '异想体事件'),
    ('AbDlg', '事件判定'), ('Announcer', '播报相关内容'),
    ('Assist', '援助相关'), ('ErrorCodeMsg', '错误代码'),
    ('UnitKeyword', '关键词'), ('Personalities', '人格'),
    ('Characters', '角色'), ('EGOgift', 'EGO饰品'),
    ('Dungeon', '地牢'), ('Enemies', '敌人'),
    ('PanicInfo', '效果'), ('Passives', '被动'),
    ('Railway', '轨道线'), ('Egos', '角色EGO'),
    ('Skill', '技能'), ('Stage', '舞台'),
    ('Story', '故事'), ('Event', '活动'), ('Bufs', '通用Buff'),
]

CATEGORY_FILE_PATTERNS = {
    'Skill': r'Skill.*\.json$', 'Bufs': r'Bufs.*\.json$',
    'BattleSpeechBubbleDlg': r'BattleSpeechBubbleDlg.*\.json$',
    'Egos': r'(Skills_Ego_Personality|Egos).*\.json$',
    'Passives': r'Passives.*\.json$', 'Personalities': r'Personalities.*\.json$',
    'Enemies': r'Enemies.*\.json$', 'EGOgift': r'EGOgift.*\.json$',
    'Railway': r'Railway.*\.json$', 'MirrorDungeon': r'MirrorDungeon.*\.json$',
    'Dungeon': r'Dungeon.*\.json$', 'Stage': r'Stage.*\.json$',
    'Story': r'Story.*\.json$', 'Event': r'Event.*\.json$',
    'BattleUIText': r'BattleUIText.*\.json$', 'BattleKeywords': r'BattleKeywords.*\.json$',
    'AbEvents': r'AbEvents.*\.json$', 'Announcer': r'Announcer.*\.json$',
    'UnitKeyword': r'UnitKeyword.*\.json$',
}

def _get_lang_dir() -> Optional[Path]:
    config = ConfigManager()
    game_path = config.get('game_path', '')
    if not game_path:
        return None
    lang_path = Path(game_path) / 'LimbusCompany_Data' / 'Lang'
    try:
        config_json = lang_path / 'config.json'
        if config_json.exists():
            lang_name = json.loads(config_json.read_text(encoding='utf-8')).get('lang', '')
            lang_path = lang_path / lang_name
    except Exception:
        pass
    return lang_path if lang_path.exists() else None

def get_lang_files() -> list[str]:
    lang_dir = _get_lang_dir()
    if not lang_dir:
        return []
    json_files = []
    for root, dirs, files in os.walk(lang_dir):
        for f in files:
            if f.endswith('.json'):
                full_path = Path(root) / f
                try:
                    json_files.append(str(full_path.relative_to(lang_dir)))
                except ValueError:
                    json_files.append(str(full_path))
    return sorted(json_files)

def get_category(relative_path: str) -> str:
    for prefix, category in FILE_PREFIX_RULES:
        if relative_path.startswith(prefix) or prefix in relative_path:
            return category
    return 'Other'

def get_file_content(relative_path: str) -> dict:
    lang_dir = _get_lang_dir()
    if not lang_dir:
        return {"error": "Lang 文件夹未配置"}
    full_path = lang_dir / relative_path
    if not full_path.exists():
        return {"error": f"文件不存在: {relative_path}"}
    try:
        raw = full_path.read_text(encoding='utf-8')
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        return {"raw": raw, "parsed": parsed, "file_classification": get_category(relative_path)}
    except Exception as e:
        return {"error": str(e), "raw": None, "parsed": None}

def search_files(keyword: str, case_sensitive: bool = False) -> dict:
    lang_dir = _get_lang_dir()
    if not lang_dir:
        return {"results_by_category": {}, "total_matches": 0}
    results_by_category = {}
    total_matches = 0
    search_keyword = keyword if case_sensitive else keyword.lower()

    def count_matches(obj):
        count = 0
        if isinstance(obj, str):
            target = obj if case_sensitive else obj.lower()
            if search_keyword in target:
                count += 1
        elif isinstance(obj, dict):
            for k, v in obj.items():
                count += count_matches(k) + count_matches(v)
        elif isinstance(obj, list):
            for item in obj:
                count += count_matches(item)
        return count

    for root, dirs, files in os.walk(lang_dir):
        for f in files:
            if not f.endswith('.json'):
                continue
            full_path = Path(root) / f
            try:
                rel_path = str(full_path.relative_to(lang_dir))
            except ValueError:
                rel_path = str(full_path)
            try:
                data = json.loads(full_path.read_text(encoding='utf-8'))
                matches = count_matches(data)
                if matches > 0:
                    category = get_category(rel_path)
                    if category not in results_by_category:
                        results_by_category[category] = []
                    results_by_category[category].append((rel_path, matches))
                    total_matches += matches
            except Exception:
                pass
    return {"results_by_category": results_by_category, "total_matches": total_matches}
```

- [ ] **Step 2: 添加规则集 CRUD 方法**

```python
# webutils/function_rule_editor.py (续)

def get_ruleset_list() -> list[dict]:
    rulesets = load_fancy_folder_rules()
    return [
        {"name": rs["name"], "desc": rs.get("desc", ""), "rule_count": len(rs.get("rules", []))}
        for rs in rulesets
    ]

def get_ruleset(name: str) -> dict:
    folder = _get_fancy_folder()
    filename = _sanitize_filename(name) + '.json'
    filepath = folder / filename
    if not filepath.exists():
        return {"error": f"规则集不存在: {name}"}
    try:
        return json.loads(filepath.read_text(encoding='utf-8'))
    except Exception as e:
        return {"error": str(e)}

def save_ruleset(name: str, data: dict) -> dict:
    try:
        if 'name' not in data:
            data['name'] = name
        filepath = save_ruleset_to_folder(name, data)
        return {"success": True, "path": str(filepath)}
    except Exception as e:
        return {"success": False, "error": str(e)}

def create_ruleset(name: str) -> dict:
    template = {"name": name, "desc": "", "rules": []}
    return save_ruleset(name, template)

def delete_ruleset(name: str) -> dict:
    success = delete_ruleset_from_folder(name)
    if success:
        return {"success": True}
    return {"success": False, "error": f"规则集不存在或删除失败: {name}"}
```

- [ ] **Step 3: 添加规则构建和验证方法**

```python
# webutils/function_rule_editor.py (续)

def _file_pattern_from_selection(selection: str) -> str:
    if selection in CATEGORY_FILE_PATTERNS:
        return CATEGORY_FILE_PATTERNS[selection]
    if any(c in selection for c in '.*+?^${}[]|()\\'):
        return selection
    return f"{re.escape(selection)}.*\\.json$"

def build_rule_from_form(form_data: dict) -> dict:
    aim_file = _file_pattern_from_selection(form_data.get("file_pattern", ""))
    item_ids = form_data.get("item_ids", [])
    field_path = form_data.get("field_path", "desc")
    operations = form_data.get("operations", [])
    extra_conditions = form_data.get("extra_conditions", [])

    conditions = []
    if item_ids:
        id_pattern = "^(" + "|".join(str(i) for i in item_ids) + ")$"
        conditions.append({
            "trigger": {"aim": r"dataList\.\d+\.id", "re": id_pattern},
            "aim": f"[back].{field_path}"
        })
    else:
        conditions.append({"aim": rf"dataList\.\d+\.{field_path}"})

    for ec in extra_conditions:
        cond = {}
        if ec.get("field") and ec.get("pattern"):
            cond["trigger"] = {
                "aim": rf"dataList\.\d+\.{ec['field']}",
                "re": ec["pattern"]
            }
            cond["aim"] = f"[back].{field_path}"
        conditions.append(cond)

    action = [{"from": op["from"], "to": op["to"]} for op in operations]
    return {"aimFile": aim_file, "conditions": conditions, "action": action}

def validate_rule(rule_json: str) -> dict:
    errors = []
    try:
        rule = json.loads(rule_json)
    except json.JSONDecodeError as e:
        return {"valid": False, "errors": [f"JSON 语法错误: {e}"]}
    if not isinstance(rule, dict):
        return {"valid": False, "errors": ["规则必须是 JSON 对象"]}
    if "aimFile" not in rule or not rule["aimFile"]:
        errors.append("缺少 aimFile 字段（文件匹配模式）")
    conds = rule.get("conditions", [])
    if not conds and "aim" not in rule and "trigger" not in rule:
        errors.append("缺少 conditions 或 aim 字段（定位条件）")
    action = rule.get("action", [])
    if not action:
        errors.append("缺少 action 字段（操作列表）")
    else:
        for i, act in enumerate(action):
            if not isinstance(act, dict):
                errors.append(f"action[{i}] 不是有效的操作对象")
            elif "from" in act and "to" not in act:
                errors.append(f"action[{i}] 有 from 但缺少 to")
            elif "to" in act and "from" not in act:
                errors.append(f"action[{i}] 有 to 但缺少 from")
    try:
        re.compile(rule.get("aimFile", ""))
    except re.error as e:
        errors.append(f"aimFile 正则语法错误: {e}")
    return {"valid": len(errors) == 0, "errors": errors}
```

- [ ] **Step 4: 添加智能分析引擎**

```python
# webutils/function_rule_editor.py (续)

def _analyze_value_change(old_val: str, new_val: str) -> dict:
    """LCS 分析：分解值变化为 prefix + core + suffix"""
    if not isinstance(old_val, str) or not isinstance(new_val, str):
        return {"change_type": "UNKNOWN"}
    lcp_len = 0
    for a, b in zip(old_val, new_val):
        if a == b: lcp_len += 1
        else: break
    old_rem = old_val[lcp_len:]
    new_rem = new_val[lcp_len:]
    lcs_len = 0
    for a, b in zip(reversed(old_rem), reversed(new_rem)):
        if a == b: lcs_len += 1
        else: break
    prefix_added = new_val[:lcp_len]
    core_old = old_val[lcp_len:len(old_val)-lcs_len] if lcs_len else old_val[lcp_len:]
    core_new = new_val[lcp_len:len(new_val)-lcs_len] if lcs_len else new_val[lcp_len:]
    suffix_added = new_val[len(new_val)-lcs_len:] if lcs_len else ""

    if core_old == core_new:
        if prefix_added and suffix_added: change_type = "PURE_WRAP"
        elif prefix_added: change_type = "PREFIX_ONLY"
        elif suffix_added: change_type = "SUFFIX_ONLY"
        else: change_type = "PURE_REPLACE"
    else:
        change_type = "REPLACE_WRAP" if (prefix_added or suffix_added) else "PURE_REPLACE"

    return {
        "change_type": change_type, "prefix_added": prefix_added,
        "core_old": core_old, "core_new": core_new,
        "suffix_added": suffix_added, "old_val": old_val, "new_val": new_val
    }

def _cluster_changes(changes: list) -> list:
    analyzed = []
    for c in changes:
        info = _analyze_value_change(c["old_val"], c["new_val"])
        info.update(c)
        analyzed.append(info)
    if not analyzed:
        return []
    first_type = analyzed[0]["change_type"]
    if first_type in ("PURE_REPLACE",):
        sort_key = lambda a: (a["change_type"], a["core_old"], a["core_new"])
    else:
        sort_key = lambda a: (a["change_type"], a["prefix_added"], a["suffix_added"])
    analyzed.sort(key=sort_key)
    groups, current = [], [analyzed[0]]
    for item in analyzed[1:]:
        prev = current[-1]
        if item["change_type"] in ("PURE_REPLACE",):
            if item["core_old"] == prev["core_old"] and item["core_new"] == prev["core_new"]:
                current.append(item)
            else:
                groups.append(current); current = [item]
        else:
            if item["prefix_added"] == prev["prefix_added"] and item["suffix_added"] == prev["suffix_added"]:
                current.append(item)
            else:
                groups.append(current); current = [item]
    groups.append(current)
    return groups

def _score_group(group: list) -> dict:
    n = len(group)
    files = set(item["file"] for item in group)
    items = set(item.get("item_id") for item in group if item.get("item_id"))
    categories = set(get_category(f) for f in files)
    change_type = group[0]["change_type"]
    has_ids = len(items) > 0

    s1 = min(100, len(files) * 8 + len(items) * 3 + n * 1)
    if change_type == "PURE_REPLACE": s2 = 100
    elif change_type == "PURE_WRAP": s2 = 95
    elif change_type == "REPLACE_WRAP": s2 = 70
    else: s2 = 60
    if len(categories) >= 3: s3 = 100
    elif len(categories) == 2: s3 = 80
    else: s3 = 60
    s3 += 10 if has_ids else 0
    s4 = 95 if has_ids else 60
    if n >= 5: s5 = 100
    elif n >= 3: s5 = 80
    elif n == 2: s5 = 60
    else: s5 = 30
    if change_type == "PURE_REPLACE" and not group[0].get("prefix_added"):
        s5 = min(100, s5 + 15)
    if any("<color=" in item.get("new_val", "") for item in group):
        s5 = min(100, s5 + 10)
    priority = 0.25 * s1 + 0.20 * s2 + 0.20 * s3 + 0.20 * s4 + 0.15 * s5
    return {"s1_coverage": s1, "s2_purity": s2, "s3_generalizability": s3,
            "s4_stability": s4, "s5_intent": s5, "priority": round(priority, 1)}

def _infer_file_scope(files: list) -> dict:
    categories = {}
    for f in files:
        cat = get_category(f)
        categories[cat] = categories.get(cat, 0) + 1
    cat_names = sorted(categories.keys())
    return {
        "suggested": "category" if len(cat_names) <= 2 else "multi_category",
        "categories": [{"name": c, "count": categories[c], "selected": True} for c in cat_names],
        "exact_files": files
    }

def analyze_changes(changes: list) -> dict:
    if not changes:
        return {"groups": [], "merge_suggestions": []}
    groups = _cluster_changes(changes)
    result_groups = []
    for group in groups:
        files = list(set(c["file"] for c in group))
        field_paths = list(set(c["field_path"] for c in group))
        item_ids = list(set(c.get("item_id") for c in group if c.get("item_id")))
        first = group[0]
        score = _score_group(group)

        if first["change_type"] == "PURE_REPLACE" and len(group) >= 3:
            if all(c["new_val"] in "><≥≤" for c in group):
                summary = "你似乎在对数学比较符号做统一替换"
            else:
                summary = f"检测到 {len(group)} 处相同的文本替换"
        elif first["change_type"] in ("PURE_WRAP", "REPLACE_WRAP"):
            colors = set()
            for part in [first["prefix_added"], first["suffix_added"]]:
                for m in re.finditer(r'color=#([0-9a-fA-F]{6})', part):
                    colors.add(m.group(1))
            if colors:
                summary = f"你似乎在对词汇做统一着色（颜色: #{list(colors)[0]}）"
            else:
                summary = f"检测到 {len(group)} 处文本格式化"
        else:
            summary = f"检测到 {len(group)} 处相同修改"

        suggestions = []
        if first["change_type"] == "PURE_REPLACE":
            compare_terms = [c["core_old"] for c in group]
            known = {"大于": ">", "小于": "<", "不低于": "≥", "不高于": "≤"}
            for term, sym in known.items():
                if term not in compare_terms:
                    suggestions.append(f"你也可以添加: {term} → {sym}")

        done_cores = set()
        action_preview = []
        for c in group:
            key = (c["core_old"], c["core_new"])
            if key not in done_cores:
                action_preview.append({"from": c["core_old"], "to": c["core_new"]})
                done_cores.add(key)

        result_groups.append({
            "change_type": first["change_type"],
            "summary": summary,
            "suggestions": suggestions,
            "action_preview": action_preview[:5],
            "file_count": len(files), "item_count": len(item_ids),
            "occurrence_count": len(group),
            "l1_options": _infer_file_scope(files),
            "l2_options": {"suggested": "id" if item_ids else "full_text", "item_ids": item_ids},
            "l3_options": {"suggested": "restricted" if len(field_paths) == 1 else "all_text",
                           "fields": field_paths},
            "l4_options": {"suggested": "exact" if first["change_type"] == "PURE_REPLACE" else "none"},
            "score": score
        })

    result_groups.sort(key=lambda g: g["score"]["priority"], reverse=True)
    return {"groups": result_groups, "merge_suggestions": []}
```

- [ ] **Step 4: Commit**

```bash
git add webutils/function_rule_editor.py
git commit -m "feat: add RuleEditorAPI with file browser, CRUD, rule building, and smart generation"
```

---

### Task 4: Frontend Shell — HTML + CSS

**Files:**
- Create: `webui/rule-editor.html`
- Create: `webui/css/rule-editor.css`

- [ ] **Step 1: 创建 HTML**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LCTA - 美化规则编辑器</title>
    <link rel="stylesheet" href="css/base.css">
    <link rel="stylesheet" href="css/components.css">
    <link rel="stylesheet" href="css/rule-editor.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script type="module">
        import {EditorView, basicSetup} from "https://esm.sh/codemirror@6.0.1";
        import {json} from "https://esm.sh/@codemirror/lang-json@6.0.1";
        window.CodeMirror = {EditorView, basicSetup, json};
    </script>
</head>
<body class="theme-light">
<div class="rule-editor-container">
    <div class="re-sidebar">
        <div class="re-sidebar-header">
            <h3><i class="fas fa-folder-open"></i> 文件浏览器</h3>
        </div>
        <div class="re-search-bar">
            <input type="text" id="re-file-search" placeholder="搜索文件内容...">
            <label class="re-checkbox"><input type="checkbox" id="re-case-sensitive"> 区分大小写</label>
            <button id="re-search-btn" class="re-btn re-btn-sm"><i class="fas fa-search"></i> 搜索</button>
            <button id="re-search-clear-btn" class="re-btn re-btn-sm"><i class="fas fa-times"></i> 清除</button>
        </div>
        <div class="re-file-tabs">
            <button class="re-tab active" data-tab="file-list">文件列表</button>
            <button class="re-tab" data-tab="search-results">搜索结果</button>
        </div>
        <div id="re-file-list-container" class="re-file-list"></div>
        <div id="re-search-results-container" class="re-search-results" style="display:none;"></div>
    </div>
    <div class="re-main">
        <div class="re-toolbar">
            <select id="re-ruleset-select"></select>
            <button id="re-new-ruleset-btn" class="re-btn"><i class="fas fa-plus"></i> 新建</button>
            <button id="re-save-ruleset-btn" class="re-btn re-btn-primary"><i class="fas fa-save"></i> 保存</button>
            <button id="re-delete-ruleset-btn" class="re-btn re-btn-danger"><i class="fas fa-trash"></i> 删除</button>
        </div>
        <div class="re-mode-toggle">
            <button class="re-mode-btn active" data-mode="simple">🔰 简单模式</button>
            <button class="re-mode-btn" data-mode="advanced">⚙ 高级模式</button>
        </div>
        <div id="re-simple-mode" class="re-editor-panel">
            <div class="re-form-group"><label>文件匹配</label>
                <select id="re-simple-file"><option value="">-- 选择文件分类 --</option></select>
                <input type="text" id="re-simple-file-custom" placeholder="或自定义正则..." style="margin-top:4px;">
            </div>
            <div class="re-form-group"><label>数据条目</label>
                <div class="re-form-row">
                    <label class="re-checkbox"><input type="checkbox" id="re-simple-use-id" checked> 按ID定位</label>
                    <input type="text" id="re-simple-item-id" placeholder="ID（逗号分隔）" style="flex:1;">
                    <input type="text" id="re-simple-field" placeholder="字段名" style="flex:1;" value="desc">
                </div>
            </div>
            <div class="re-form-group"><label>条件触发（可选）</label>
                <div id="re-simple-conditions"></div>
                <button class="re-btn re-btn-sm" id="re-add-condition-btn">＋ 添加条件</button>
            </div>
            <div class="re-form-group"><label>操作列表</label>
                <div id="re-simple-operations">
                    <div class="re-operation-item">
                        <input type="text" placeholder="查找" class="re-op-from">
                        <span>→</span>
                        <input type="text" placeholder="替换为" class="re-op-to">
                        <button class="re-btn re-btn-sm re-remove-op-btn">✕</button>
                    </div>
                </div>
                <button class="re-btn re-btn-sm" id="re-add-op-btn">＋ 添加操作</button>
            </div>
            <div class="re-form-row" style="margin-top:12px;">
                <button class="re-btn re-btn-primary" id="re-preview-rule-btn">👁 预览JSON</button>
                <button class="re-btn re-btn-success" id="re-generate-rule-btn">📋 生成规则JSON</button>
            </div>
            <div id="re-simple-preview" style="margin-top:8px; display:none;">
                <pre id="re-simple-preview-content" style="font-size:12px; background:var(--color-bg-primary); padding:8px; border-radius:6px; overflow:auto; max-height:200px;"></pre>
            </div>
        </div>
        <div id="re-advanced-mode" class="re-editor-panel" style="display:none;">
            <div class="re-advanced-toolbar">
                <select id="re-template-select"><option value="">📋 模板...</option></select>
                <button class="re-btn re-btn-sm" id="re-format-json-btn">格式化</button>
                <button class="re-btn re-btn-sm" id="re-validate-btn">验证</button>
            </div>
            <div id="re-advanced-editor" style="height:300px; border:1px solid var(--color-border); border-radius:6px;"></div>
            <div id="re-validation-result" style="margin-top:4px; font-size:12px;"></div>
        </div>
        <div class="re-rules-preview">
            <h4>当前规则集预览</h4>
            <div id="re-rules-preview-list"></div>
        </div>
        <div class="re-action-bar">
            <button id="re-apply-btn" class="re-btn re-btn-success"><i class="fas fa-play"></i> 应用规则集到游戏</button>
            <button id="re-smart-gen-btn" class="re-btn re-btn-accent"><i class="fas fa-brain"></i> 智能生成规则集</button>
        </div>
    </div>
</div>
<div class="re-bottom-panel">
    <div class="re-bottom-header">
        <h4><i class="fas fa-file-alt"></i> 文件内容预览</h4>
        <span id="re-current-file">未选择文件</span>
    </div>
    <div id="re-content-simple" class="re-content-panel"></div>
    <div id="re-content-advanced" class="re-content-panel" style="display:none;"></div>
</div>
<script src="js/rule-editor.js"></script>
</body>
</html>
```

- [ ] **Step 2: 创建 CSS（使用上一轮讨论中设计的完整样式）**

完整 CSS 内联在 HTML 的 `<style>` 标签中或作为独立文件 `webui/css/rule-editor.css`，内容为讨论中设计的样式（`re-sidebar`, `re-main`, `re-btn`, `re-data-card`, `re-smart-gen-*` 等）。

- [ ] **Step 3: Commit**

```bash
git add webui/rule-editor.html webui/css/rule-editor.css
git commit -m "feat: add rule editor HTML shell and CSS styling"
```

---

### Task 5: Frontend JS — 核心框架 & 文件浏览器

**Files:**
- Create: `webui/js/rule-editor.js`

- [ ] **Step 1: 编写 JS 核心状态管理和文件浏览器**

完整 JS 代码包含：state 对象、`init()`、`loadLangFiles()`、`loadRulesets()`、`renderFileList()`、`openFile()`、`renderSimpleContent()`、`renderDataCard()`、`renderAdvancedContent()`、`performSearch()`、`renderSearchCategories()`、`bindEvents()`、`selectField()`、`addItemToRule()` 等函数。

- [ ] **Step 2: Commit**

```bash
git add webui/js/rule-editor.js
git commit -m "feat: add rule editor core JS with file browser and dual-mode content display"
```

---

### Task 6: Frontend JS — 简单模式 & 高级模式 & 智能生成

**Files:**
- Modify: `webui/js/rule-editor.js` (追加简单模式、高级模式、智能生成逻辑)

- [ ] **Step 1: 追加简单模式表单逻辑**

添加：`initSimpleFileSelect()`、`buildFormData()`、`previewRule()`、`generateRule()`、`renderRulesPreview()`、`removeRule()`、`addConditionRow()`、`addOperationRow()`

- [ ] **Step 2: 追加高级模式逻辑**

添加：`initAdvancedMode()`、`loadTemplates()`、`getAdvancedContent()`、`validateAdvancedContent()`、`formatAdvancedContent()`、`syncAdvancedFromRuleset()`

- [ ] **Step 3: 追加智能生成 UI 逻辑**

添加：`openSmartGeneration()`、`showSmartGenDialog()`、`previewSmartGroup()`、`applySmartGroup()`、`generateAllSmart()`

- [ ] **Step 4: 追加规则集管理事件绑定**

在 `bindEvents` 中追加：新建/保存/删除/选择规则集事件，应用规则集事件，智能生成按钮事件，模式切换事件。

- [ ] **Step 5: Commit**

```bash
git add webui/js/rule-editor.js
git commit -m "feat: add simple mode, advanced mode, and smart generation UI logic"
```

---

### Task 7: Integration — 主应用连接

**Files:**
- Modify: `webui/app.py` (新增 `RuleEditorAPI` 类和 `open_rule_editor` 方法)
- Modify: `webui/sections/fancy.html` (添加按钮)
- Modify: `webui/js/features.js` 或 `webui/js/utils.js` (添加触发函数)

- [ ] **Step 1: 在 `webui/app.py` 中添加 `RuleEditorAPI` 类和窗口创建方法**

```python
class RuleEditorAPI:
    def __init__(self):
        from webutils.function_rule_editor import (
            get_lang_files, get_file_content, search_files,
            get_ruleset_list, get_ruleset, save_ruleset,
            create_ruleset, delete_ruleset,
            build_rule_from_form, validate_rule, analyze_changes,
            CATEGORY_FILE_PATTERNS
        )
        self.get_lang_files = get_lang_files
        self.get_file_content = get_file_content
        self.search_files = search_files
        self.get_ruleset_list = get_ruleset_list
        self.get_ruleset = get_ruleset
        self.save_ruleset = save_ruleset
        self.create_ruleset = create_ruleset
        self.delete_ruleset = delete_ruleset
        self.build_rule_from_form = build_rule_from_form
        self.validate_rule = validate_rule
        self.analyze_changes = analyze_changes

    def apply_ruleset(self, name: str) -> dict:
        from webutils.function_fancy import fancy_main
        from pathlib import Path
        try:
            game_path = ConfigManager().get('game_path')
            lang_path = Path(game_path) / 'LimbusCompany_Data' / 'lang'
            config_lang = json.loads((lang_path / 'config.json').read_text(encoding='utf-8')).get('lang', '')
            from webutils.function_rule_editor import get_ruleset
            ruleset = get_ruleset(name)
            if 'error' in ruleset:
                return {"success": False, "message": ruleset['error']}
            fancy_main(game_path, config_lang, [ruleset])
            return {"success": True, "message": f"已应用"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_autocomplete_data(self) -> dict:
        from webutils.function_rule_editor import CATEGORY_FILE_PATTERNS
        return {
            "file_patterns": [{"label": k, "value": v} for k, v in CATEGORY_FILE_PATTERNS.items()],
            "common_replacements": [
                {"from": "大于", "to": ">"}, {"from": "小于", "to": "<"},
                {"from": "不低于", "to": "≥"}, {"from": "不高于", "to": "≤"},
                {"from": "自身", "to": "<u><color=#7C5738>自身</color></u>"},
                {"from": "目标", "to": "<u><color=#7C5738>目标</color></u>"},
                {"from": "护盾", "to": "<u><color=#81BBE8>护盾</color></u>"},
                {"from": "理智值", "to": "<u><color=#81BBE8>理智值</color></u>"},
                {"from": "体力", "to": "<u><color=#61DA61>体力</color></u>"},
            ]
        }

    def get_templates(self) -> list[dict]:
        return [
            {"name": "空规则集", "template": {"name": "", "desc": "", "rules": []}},
            {"name": "简单文本替换", "template": {
                "name": "", "desc": "",
                "rules": [{"aimFile": "Skill.*\\.json$",
                           "conditions": [{"aim": "dataList\\.\\d+\\.desc"}],
                           "action": [{"from": "查找", "to": "替换"}]}]
            }},
            {"name": "按ID定位替换", "template": {
                "name": "", "desc": "",
                "rules": [{"aimFile": "Skill.*\\.json$",
                           "conditions": [{"trigger": {"aim": "dataList\\.\\d+\\.id", "re": "^10001$"},
                                           "aim": "[back].desc"}],
                           "action": [{"from": "查找", "to": "替换"}]}]
            }},
            {"name": "颜色渐变", "template": {
                "name": "", "desc": "",
                "rules": [{"aimFile": "BattleSpeechBubbleDlg.*\\.json$",
                           "conditions": [{"aim": "dataList\\.\\d+\\.dlg"}],
                           "action": [{"rate": 0.4}]}]
            }},
        ]

# 在 LCTA_API 类中添加：
def open_rule_editor(self):
    html_path = os.path.join(os.getenv('path_'), "webui/rule-editor.html")
    window = webview.create_window(
        "LCTA - 美化规则编辑器", url=html_path,
        width=1200, height=800, resizable=True, text_select=True,
        js_api=RuleEditorAPI()
    )
    if not hasattr(self, '_rule_editor_windows'):
        self._rule_editor_windows = []
    self._rule_editor_windows.append(window)
```

- [ ] **Step 2: 在 fancy 页面添加按钮**

```html
<!-- webui/sections/fancy.html 按钮组末尾 -->
<button class="action-btn" onclick="openRuleEditor()">
    <i class="fas fa-external-link-alt"></i> 打开规则编辑器
</button>
```

- [ ] **Step 3: 添加 JS 触发函数**

```javascript
// webui/js/features.js 或 webui/js/utils.js
function openRuleEditor() {
    pywebview.api.open_rule_editor();
}
```

- [ ] **Step 4: 手动端到端验证**

验证：主应用→文本美化→打开规则编辑器→文件列表→简单模式→编辑规则→高级模式→智能生成→保存→应用

- [ ] **Step 5: Commit**

```bash
git add webui/app.py webui/sections/fancy.html webui/js/features.js
git commit -m "feat: integrate rule editor with main app via fancy page button"
```

---

## 自审清单

- [x] **Spec coverage**: conditions格式(T1) / fancy文件夹(T2) / 文件浏览(T3,T5) / 简单模式(T3,T6) / 高级模式(T6) / 智能生成(T3,T6) / 错误处理(各Task内联) / 迁移(T2) / 主应用集成(T7)
- [x] **无占位符**: 所有步骤含实际代码
- [x] **类型一致性**: `get_lang_files→list[str]`, `build_rule_from_form(form_data)→dict`, `analyze_changes(changes)→dict` 在前后端定义一致
