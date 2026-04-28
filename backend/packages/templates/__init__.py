"""行业知识体系模板模块。

书虫智能体的核心设计原则之一：项目创建时必须选择行业，行业决定后续所有模块的行为逻辑。
本模块提供多个行业的四级知识体系架构（L1行业 → L2部门 → L3业务领域 → L4知识条目），
作为推荐模板供用户选择和定制。

已支持行业：能源(energy)、金融(finance)、医疗健康(healthcare)、
           信息技术(it)、制造业(manufacturing)

用法：
    from packages.templates import get_template, list_industries
    template = get_template("energy")       # 获取能源行业模板
    industries = list_industries()          # 列出所有可用行业
    domains = template_to_domains(template) # 转换为 domain 记录列表
"""

from packages.templates.registry import (
    INDUSTRY_REGISTRY,
    IndustryTemplate,
    TaxonomyNode,
    get_template,
    list_industries,
    template_to_domains,
)

__all__ = [
    "INDUSTRY_REGISTRY",
    "IndustryTemplate",
    "TaxonomyNode",
    "get_template",
    "list_industries",
    "template_to_domains",
]
