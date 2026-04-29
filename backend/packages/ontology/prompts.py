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
