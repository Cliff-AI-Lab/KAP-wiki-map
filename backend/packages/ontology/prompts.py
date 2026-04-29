"""本体演化提议 prompt 模板（决策书 §5.3 LLM 提议机制）。"""

# ════════════════════════════════════════════════════════════════════════
# 监测条件 1：未匹配实体累计超阈值 → 提议新实体类型
# ════════════════════════════════════════════════════════════════════════

ENTITY_TYPE_PROPOSE_SYSTEM = """你是一名资深的知识工程师，专长本体演化。

任务：客户上传材料中出现了大量类型不在 L1+L2 本体的实体。请归纳这批实体的共性，
提议**一个**新的实体类型加入 L2 本体。

判断原则：
1. 类型粒度合适——既不能太宽（如"对象"），也不能太窄（如"#1 锅炉"）
2. type_name 用客户行业惯用术语
3. type_id 必须英文 snake_case
4. 给出 3-5 个 examples 帮助 SME 审核
5. 如果这批实体语义太杂混不能归一类，返回 confidence < 0.3 让 SME 知道需要细分

严格按 JSON 格式输出。"""

ENTITY_TYPE_PROPOSE_USER = """## 现有 L1 + L2 已注册的实体类型
{existing_types}

## 客户行业
{industry_code}（{industry_name}）

## 未匹配实体样本（共 {evidence_count} 个）
{sample_entities}

## 请输出 JSON：
{{
  "type_id": "英文 snake_case id（如 'control_loop'）",
  "type_name": "中文显示名（如 '控制回路'）",
  "description": "1-2 句解释",
  "examples": ["实例 1", "实例 2", "实例 3"],
  "parent_type_id": "可选；若该新类型应作为现有类型的子类型则填",
  "confidence": 0.0-1.0,
  "reasoning": "提议理由（一句话）"
}}"""


# ════════════════════════════════════════════════════════════════════════
#  监测条件 2：自定义关系反复出现 → 提议固化进本体（M5 #1）
# ════════════════════════════════════════════════════════════════════════

RELATION_SOLIDIFY_SYSTEM = """你是一名知识工程师，专长本体演化。

任务：SME 在审核台手工标注的"自定义关系"反复出现，请归纳并提议**一个**新的关系类型加入 L2 本体。

判断原则：
1. 关系语义清晰可复用（不是一次性的临时标注）
2. type_id 必须英文 snake_case（如 'maintained_by'）
3. source_types / target_types 给出允许的实体类型 id 列表（必须在 L1+L2 已注册）
4. 给出 3-5 个 examples
5. 如果使用记录语义混杂不能归为一类，confidence < 0.3 让 SME 知道需要拆分

严格按 JSON 格式输出。"""

RELATION_SOLIDIFY_USER = """## 现有 L1 + L2 已注册的关系类型
{existing_relations}

## 现有实体类型（供 source_types / target_types 引用）
{existing_entities}

## SME 手工标注使用记录（共 {evidence_count} 条）
{usage_samples}

## 请输出 JSON：
{{
  "type_id": "英文 snake_case",
  "type_name": "中文显示名",
  "description": "1-2 句解释",
  "source_types": ["实体类型 id 1", "实体类型 id 2"],
  "target_types": ["实体类型 id"],
  "examples": ["实例描述 1", "实例 2", "实例 3"],
  "confidence": 0.0-1.0,
  "reasoning": "提议理由（一句话）"
}}"""


# ════════════════════════════════════════════════════════════════════════
#  监测条件 3：关系类型在不同语境语义漂移 → 提议拆分（M5 #1）
# ════════════════════════════════════════════════════════════════════════

RELATION_SPLIT_SYSTEM = """你是一名知识工程师，专长本体演化。

任务：观察到现有的某个关系类型在不同语境下被用于多种语义，需要判断是否拆分为多个细化关系。

判断原则：
1. 语义聚类：把样本按语义分组（如 'governs' 实际有"标准约束"和"行政规范"两种用法）
2. 仅当样本明显分为 ≥2 个语义簇时才拆分；否则返回 should_split=false
3. 拆分后的新 type_id 必须英文 snake_case，且不能与现有冲突
4. 每个新关系给出 3-5 个 examples

严格按 JSON 格式输出。"""

RELATION_SPLIT_USER = """## 待评估的关系类型
{relation_type_id}（{relation_name}）

## 现有 L1 + L2 全部关系类型（避免命名冲突）
{existing_relations}

## 该关系的实际使用样本（共 {sample_count} 条）
{samples}

## 请输出 JSON：
{{
  "should_split": true/false,
  "split_into": [
    {{
      "type_id": "新关系 1 id",
      "type_name": "中文",
      "description": "...",
      "source_types": [...],
      "target_types": [...],
      "examples": [...]
    }},
    {{"type_id": "新关系 2 id", ...}}
  ],
  "deprecate_original": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "拆分理由（一句话）"
}}"""


# ════════════════════════════════════════════════════════════════════════
#  监测条件 4：行业标准升版 → 提议本体扩展（M5 #1）
# ════════════════════════════════════════════════════════════════════════

STANDARD_UPGRADE_SYSTEM = """你是一名行业标准追踪专家。

任务：客户文档引用了新版行业标准（GB / IEC / DL/T 等），需要提议把新版加入 L2 本体的 standard 实体类型 examples（保留旧版以便溯源）。

判断原则：
1. 新版标准必须明确替代旧版（如 'GB/T 6075-2024' 替代 'GB/T 6075-2012'）
2. 仅升版同一个标准号；不归并不同标准
3. examples 列表更新为 [新版, 旧版（标记 [作废]）]
4. confidence < 0.5 时让 SME 人审

严格按 JSON 格式输出。"""

STANDARD_UPGRADE_USER = """## 行业
{industry_code}（{industry_name}）

## 现有 L1 standard 实体类型 examples
{current_examples}

## 客户最新文档引用的标准（共 {standard_count} 项）
{new_standards}

## 请输出 JSON：
{{
  "should_upgrade": true/false,
  "upgrades": [
    {{
      "old": "GB/T 6075-2012",
      "new": "GB/T 6075-2024",
      "rationale": "新版替代旧版的依据"
    }}
  ],
  "new_examples": ["GB/T 6075-2024", "GB/T 6075-2012 [作废]", "..."],
  "confidence": 0.0-1.0,
  "reasoning": "升版判断理由（一句话）"
}}"""
