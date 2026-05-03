/**
 * 轻量 i18n 字典 — V15 Phase F
 *
 * 不引入 i18next。核心页面 key 手工维护。
 * 新增 key 同时在 zh 和 en 两个 map 补。
 */

export type Locale = 'zh' | 'en';

export type TranslationKey =
  // 品牌 / 顶栏
  | 'brand.name'
  | 'brand.tagline'
  | 'mode.read'
  | 'mode.manage'
  | 'mode.read.sub'
  | 'mode.manage.sub'
  | 'topbar.settings'
  // ReaderHome
  | 'reader.title'
  | 'reader.searchPlaceholder'
  | 'reader.searchBtn'
  | 'reader.searching'
  | 'reader.cardHotWiki'
  | 'reader.cardDomainMap'
  | 'reader.cardRecent'
  | 'reader.emptyWiki'
  | 'reader.emptyDomain'
  | 'reader.emptyRecent'
  | 'reader.emptyProject'
  | 'reader.emptyProjectHint'
  | 'reader.loadingProject'
  | 'reader.sources'
  | 'reader.routeWiki'
  | 'reader.routeRag'
  | 'reader.routeHybrid'
  // GovernanceHome
  | 'gov.title'
  | 'gov.subtitle'
  | 'gov.seedDemo'
  | 'settings.tabSystem'
  | 'gov.queueDetail'
  | 'gov.countTotal'
  | 'gov.emptyQueue'
  | 'gov.btnApprove'
  | 'gov.btnReject'
  | 'gov.btnEdit'
  | 'gov.kindDraft'
  | 'gov.kindUnverified'
  | 'gov.kindConflict'
  | 'gov.kindStandardize'
  | 'gov.kindArchive'
  | 'gov.health'
  | 'gov.healthSub'
  | 'gov.metricCoverage'
  | 'gov.metricFallback'
  | 'gov.metricProvenance'
  | 'gov.hintCoverage'
  | 'gov.hintFallback'
  | 'gov.hintProvenance'
  // 设置
  | 'settings.title'
  | 'settings.tabAI'
  | 'settings.tabTheme'
  | 'settings.tabLocale'
  | 'settings.tabAbout'
  | 'settings.cancel'
  | 'settings.save'
  | 'settings.localeZh'
  | 'settings.localeEn'
  | 'settings.localeDesc'
  // M16 #1 · 运营观察仪表盘
  | 'observ.dashboard.title'
  | 'observ.dashboard.subtitle'
  | 'observ.refresh'
  | 'observ.card.decisions'
  | 'observ.card.queries'
  | 'observ.card.observations'
  | 'observ.card.recallEval'
  | 'observ.card.recallTrend'
  | 'observ.card.conditionHealth'
  | 'observ.alert'
  | 'observ.empty'
  | 'observ.loading'
  // M17 #1 · 矩阵审核台 / 我认领的 / GT 审批 / 横评
  | 'matrix.title'
  | 'matrix.subtitle'
  | 'matrix.legendR'
  | 'matrix.legendC'
  | 'matrix.legendI'
  | 'matrix.totalPending'
  | 'myclaimed.title'
  | 'myclaimed.subtitle'
  | 'myclaimed.empty'
  | 'myclaimed.bulkApprove'
  | 'myclaimed.bulkReject'
  | 'myclaimed.selectAll'
  | 'myclaimed.unselectAll'
  | 'myclaimed.selected'
  | 'gtreview.title'
  | 'gtreview.subtitle'
  | 'gtreview.candidates'
  | 'gtreview.existing'
  | 'gtreview.confirm'
  | 'gtreview.skip'
  | 'gtreview.empty'
  | 'compare.title'
  | 'compare.subtitle'
  | 'compare.empty'
  | 'compare.col.project'
  | 'compare.col.decisions'
  | 'compare.col.queries'
  | 'compare.col.useful'
  | 'compare.col.latency'
  | 'compare.col.observations'
  | 'compare.col.gt'
  | 'compare.col.recall'
  // M18 #2 · Wiki 质量看板
  | 'wq.title'
  | 'wq.subtitle'
  | 'wq.aggCard'
  | 'wq.totalScored'
  | 'wq.alertingCount'
  | 'wq.avgOverall'
  | 'wq.radar'
  | 'wq.alertList'
  | 'wq.empty'
  | 'wq.dim.consistency'
  | 'wq.dim.completeness'
  | 'wq.dim.evidence'
  | 'wq.dim.repetition'
  | 'wq.dim.freshness'
  | 'wq.dim.cross_domain'
  | 'wq.col.page'
  | 'wq.col.type'
  | 'wq.col.overall'
  | 'wq.col.scoredAt'
  | 'wq.filterAlerting'
  | 'wq.trend'
  | 'wq.trendDelta'
  | 'wq.trendAlert'
  // M18 #3 · PromptVersion 管理
  | 'pv.title'
  | 'pv.subtitle'
  | 'pv.tabList'
  | 'pv.tabAB'
  | 'pv.create'
  | 'pv.deactivate'
  | 'pv.autoTune'
  | 'pv.col.versionId'
  | 'pv.col.condition'
  | 'pv.col.language'
  | 'pv.col.activatedAt'
  | 'pv.col.status'
  | 'pv.col.note'
  | 'pv.col.actions'
  | 'pv.col.sampleSize'
  | 'pv.col.approveRate'
  | 'pv.statusActive'
  | 'pv.statusInactive'
  | 'pv.empty'
  | 'pv.filterCondition'
  | 'pv.filterLanguage'
  | 'pv.filterAll'
  | 'pv.confirmDeactivate'
  | 'pv.autoTuneAction'
  | 'pv.autoTuneNoop'
  | 'pv.autoTuneReason'
  // M19 #3 · PromptVersion diff UI
  | 'pv.tabDiff'
  | 'pv.diffSelect'
  | 'pv.diffSelectLeft'
  | 'pv.diffSelectRight'
  | 'pv.diffEmpty'
  | 'pv.diffNoChanges'
  | 'pv.diffExcerpt'
  | 'pv.diffSystem'
  | 'pv.diffStats'
  // M21 i18n 收口 · 5 Agent / 4 角色 / 4 监测条件 / 3 层 Wiki / 调试提示清理
  | 'agent.curator'
  | 'agent.auditor'
  | 'agent.deduper'
  | 'agent.standardizer'
  | 'agent.gardener'
  | 'agent.planner'
  | 'role.dg'
  | 'role.sme'
  | 'role.sec'
  | 'role.aiops'
  | 'role.dg.full'
  | 'role.sme.full'
  | 'role.sec.full'
  | 'role.aiops.full'
  | 'cond.new_entity_type'
  | 'cond.relation_solidification'
  | 'cond.relation_split'
  | 'cond.standard_upgrade'
  | 'wiki.layer.index'
  | 'wiki.layer.domain_overview'
  | 'wiki.layer.source_summary'
  | 'observ.endpointHint'
  | 'gtreview.subtitleClean'
  | 'gtreview.minUsefulRate'
  | 'gtreview.minSamples'
  | 'myclaimed.subtitleClean'
  | 'wq.emptyClean'
  | 'observ.legendApproveRejectPending'
  | 'observ.commonRejectReasons'
  // GovernanceHome 6 工位 pipeline
  | 'pipeline.title'
  | 'pipeline.subtitle'
  | 'pipeline.empty'
  | 'pipeline.switch'
  | 'pipeline.matrix'
  | 'pipeline.run'
  | 'pipeline.s1.label'
  | 'pipeline.s1.desc'
  | 'pipeline.s2.label'
  | 'pipeline.s2.desc'
  | 'pipeline.s3.label'
  | 'pipeline.s3.desc'
  | 'pipeline.s4.label'
  | 'pipeline.s4.desc'
  | 'pipeline.s5.label'
  | 'pipeline.s5.desc'
  | 'pipeline.s6.label'
  | 'pipeline.s6.desc'
  | 'pipeline.running'
  | 'common.loading'
  | 'common.loadFailed'
  | 'observ.gtSet'
  | 'observ.notEvaluated'
  | 'observ.noReports'
  | 'observ.recallEvalHistory'
  | 'observ.row.totalDecisions'
  | 'observ.row.approveReject'
  | 'observ.row.approvalRate'
  | 'observ.row.promoteRollback'
  | 'observ.row.promoteRatio'
  | 'observ.row.queryTotalHits'
  | 'observ.row.hitRate'
  | 'observ.row.avgLatency'
  | 'observ.row.p95Latency'
  | 'observ.row.feedbackRate'
  | 'observ.row.usefulRate'
  | 'observ.row.activeWindow'
  | 'observ.row.alerting'
  | 'observ.row.totalWindow'
  | 'observ.row.gtCount'
  | 'observ.row.latestRecall'
  | 'observ.row.latestPrecision'
  | 'observ.row.latestF1'
  | 'observ.row.k'
  | 'observ.row.totalQueries'
  | 'observ.row.evalAt'
  | 'observ.row.recallTrend'
  | 'observ.row.precisionTrend'
  | 'observ.row.f1Trend'
  | 'observ.row.recallDelta'
  | 'observ.row.precisionDelta'
  | 'observ.row.f1Delta'
  | 'observ.row.improving'
  | 'observ.row.degrading'
  | 'observ.row.stable'
  | 'observ.row.recallTrendPair'
  | 'reader.routeLabel'
  | 'reader.routeShown'
  | 'observ.fetchFailed'
  | 'observ.status.watching'
  | 'observ.status.alert'
  | 'observ.status.expired'
  | 'observ.status.rolled_back'
  | 'condhealth.suggest.low_samples'
  | 'condhealth.suggest.all_pending'
  | 'condhealth.suggest.low_approve'
  | 'condhealth.suggest.mid_approve'
  | 'condhealth.suggest.high_approve'
  | 'condhealth.suggest.unclassified'
  // M18 #4 · 反馈原因可视化
  | 'observ.feedbackReasons.title'
  | 'observ.feedbackReasons.empty'
  | 'observ.feedbackReasons.totalNegFeedback';

type Dict = Record<TranslationKey, string>;

const zh: Dict = {
  'brand.name': '知识图鉴',
  'brand.tagline': 'Wiki-Map',
  'mode.read': '消费',
  'mode.manage': '治理',
  'mode.read.sub': '读 Wiki / 查知识 / 问答',
  'mode.manage.sub': '编译 / 审核 / 配置',
  'topbar.settings': '设置',

  'reader.title': '你好，在查什么？',
  'reader.searchPlaceholder': '输入你的问题，例如：动火作业需要几级审批？',
  'reader.searchBtn': '搜索',
  'reader.searching': '思考中...',
  'reader.cardHotWiki': '热门 Wiki',
  'reader.cardDomainMap': '知识地图',
  'reader.cardRecent': '最近问答',
  'reader.emptyWiki': '尚无已编译 Wiki 页',
  'reader.emptyDomain': '尚无已识别知识域',
  'reader.emptyRecent': '还没问过问题',
  'reader.emptyProject': '还没有项目',
  'reader.emptyProjectHint': '请先去 /projects/new 创建一个知识项目',
  'reader.loadingProject': '加载项目...',
  'reader.sources': '来源',
  'reader.routeWiki': 'Wiki 快路径',
  'reader.routeRag': 'RAG 深检索',
  'reader.routeHybrid': '双路径交叉',

  'gov.title': '治理收件箱',
  'gov.subtitle': '调度员 · 每日 08:00 合单',
  'gov.seedDemo': '种入示例工单',
  'settings.tabSystem': '组件状态',
  'gov.queueDetail': '工单详情',
  'gov.countTotal': '共 {n} 条',
  'gov.emptyQueue': '无待审工单（切换上方 Agent 或刷新）',
  'gov.btnApprove': '通过',
  'gov.btnReject': '打回',
  'gov.btnEdit': '改',
  'gov.kindDraft': '草稿待审',
  'gov.kindUnverified': '未溯源',
  'gov.kindConflict': '事实冲突',
  'gov.kindStandardize': '实体归一',
  'gov.kindArchive': '建议归档',
  'gov.health': '健康面板',
  'gov.healthSub': '园丁 · 每日刷新',
  'gov.metricCoverage': 'Wiki 覆盖率',
  'gov.metricFallback': 'RAG 兜底率',
  'gov.metricProvenance': '溯源完整度',
  'gov.hintCoverage': '已编译 / 已识别域',
  'gov.hintFallback': '数值越低说明治理起效',
  'gov.hintProvenance': '审核员统计',

  'settings.title': '设置',
  'settings.tabAI': 'AI 配置',
  'settings.tabTheme': '主题外观',
  'settings.tabLocale': '语言',
  'settings.tabAbout': '关于',
  'settings.cancel': '取消',
  'settings.save': '保存',
  'settings.localeZh': '中文',
  'settings.localeEn': 'English',
  'settings.localeDesc': '切换界面语言；仅影响显示，不影响后端数据',
  // M16 #1 · 运营观察仪表盘 (zh)
  'observ.dashboard.title': '运营观察仪表盘',
  'observ.dashboard.subtitle': '决策书 §5.3 KAP IP 引擎 · 全维度运营观察',
  'observ.refresh': '刷新',
  'observ.card.decisions': '演化决策（M6 #3）',
  'observ.card.queries': '查询召回（M7+M8）',
  'observ.card.observations': '7 天观察期（M5 #2 + M6 #2）',
  'observ.card.recallEval': '召回评估（M8 #2 + M9）',
  'observ.card.recallTrend': '召回率趋势（M9 #2）',
  'observ.card.conditionHealth': '监测条件健康度（M10 #2）',
  'observ.alert': '告警',
  'observ.empty': '暂无数据',
  'observ.loading': '加载中...',
  // M17 #1 · 矩阵 / 我认领 / GT / 横评 (zh)
  'matrix.title': '矩阵审核台',
  'matrix.subtitle': '4 角色 × 6 工位 · 决策书 §5.2 D6',
  'matrix.legendR': 'R = 主审',
  'matrix.legendC': 'C = 协审',
  'matrix.legendI': 'I = 知会（不出工单）',
  'matrix.totalPending': '合计 {n} 待办',
  'myclaimed.title': '我认领的工单',
  'myclaimed.subtitle': 'claimed_by · 批量决策',
  'myclaimed.empty': '未找到 {user} 认领的工单（{project}）',
  'myclaimed.bulkApprove': '批量通过',
  'myclaimed.bulkReject': '批量打回',
  'myclaimed.selectAll': '全选',
  'myclaimed.unselectAll': '取消全选',
  'myclaimed.selected': '已选 {selected} / {total}',
  'gtreview.title': 'Ground Truth 候选审批',
  'gtreview.subtitle': '决策书 §5.3 · 从高 useful_rate 查询反向构造 ground truth',
  'gtreview.candidates': '待审批候选',
  'gtreview.existing': '已入库',
  'gtreview.confirm': '确认入库',
  'gtreview.skip': '跳过',
  'gtreview.empty': '暂无候选',
  'compare.title': '多 Project 横评仪表盘',
  'compare.subtitle': '一次拉所有 project 的 4 维度摘要做横向对比（决策书 §5.3）',
  'compare.empty': '尚无任何 project 有运营数据',
  'compare.col.project': 'project_id',
  'compare.col.decisions': '决策数 (批准率)',
  'compare.col.queries': '查询数 (命中率)',
  'compare.col.useful': '有用率 (反馈数)',
  'compare.col.latency': 'avg/p95 ms',
  'compare.col.observations': '观察期 active/total',
  'compare.col.gt': 'GT 集',
  'compare.col.recall': '最近评估 R/P/F1',
  // M18 #2 · Wiki 质量看板 (zh)
  'wq.title': 'Wiki 质量看板',
  'wq.subtitle': '决策书 §6 · 6 维 LLM-Critic（M17 #3）',
  'wq.aggCard': '聚合摘要',
  'wq.totalScored': '已评分页数',
  'wq.alertingCount': '低分告警',
  'wq.avgOverall': '加权平均分',
  'wq.radar': '6 维维度雷达',
  'wq.alertList': '告警页清单',
  'wq.empty': '暂无评分数据（先在 wiki_compiler 编译几次）',
  'wq.dim.consistency': '一致性',
  'wq.dim.completeness': '完整性',
  'wq.dim.evidence': '证据',
  'wq.dim.repetition': '去重',
  'wq.dim.freshness': '时效',
  'wq.dim.cross_domain': '跨域',
  'wq.col.page': '页面',
  'wq.col.type': '类型',
  'wq.col.overall': '总分',
  'wq.col.scoredAt': '评分时间',
  'wq.filterAlerting': '只看告警',
  'wq.trend': '历史趋势',
  'wq.trendDelta': '当前 vs 起始',
  'wq.trendAlert': '趋势告警（跌幅 > 10pp）',
  // M18 #3 · PromptVersion 管理 (zh)
  'pv.title': 'Prompt 版本管理',
  'pv.subtitle': 'M11 #4 / M12 / M16 · LLM 自学习闭环',
  'pv.tabList': '版本列表',
  'pv.tabAB': 'AB 比较',
  'pv.create': '新建版本',
  'pv.deactivate': '停用',
  'pv.autoTune': '触发 auto-tune',
  'pv.col.versionId': '版本 ID',
  'pv.col.condition': '监测条件',
  'pv.col.language': '语言',
  'pv.col.activatedAt': '激活时间',
  'pv.col.status': '状态',
  'pv.col.note': '备注',
  'pv.col.actions': '操作',
  'pv.col.sampleSize': '样本数',
  'pv.col.approveRate': '批准率',
  'pv.statusActive': '激活中',
  'pv.statusInactive': '已停用',
  'pv.empty': '暂无版本（先点 "新建版本"）',
  'pv.filterCondition': '监测条件',
  'pv.filterLanguage': '语言',
  'pv.filterAll': '全部',
  'pv.confirmDeactivate': '确认停用版本 {id}？',
  'pv.autoTuneAction': '动作: {action}',
  'pv.autoTuneNoop': 'auto-tune 完成（无变化）',
  'pv.autoTuneReason': '原因',
  'pv.tabDiff': '版本对比',
  'pv.diffSelect': '选择两版本对比',
  'pv.diffSelectLeft': '左侧（旧）',
  'pv.diffSelectRight': '右侧（新）',
  'pv.diffEmpty': '请选择两个版本',
  'pv.diffNoChanges': '两版本 system_prompt 完全一致',
  'pv.diffExcerpt': 'prompt 摘要',
  'pv.diffSystem': 'system_prompt',
  'pv.diffStats': '差异：+{added} / -{removed}',
  // M21 i18n 收口 (zh)
  'agent.curator': '治理员',
  'agent.auditor': '审核员',
  'agent.deduper': '去重员',
  'agent.standardizer': '规范员',
  'agent.gardener': '园丁',
  'agent.planner': '调度员',
  'role.dg': 'DG',
  'role.sme': 'SME',
  'role.sec': 'SEC',
  'role.aiops': 'AIOps',
  'role.dg.full': '数据治理员',
  'role.sme.full': '业务专家',
  'role.sec.full': '安全审计员',
  'role.aiops.full': 'AI 运营员',
  'cond.new_entity_type': '新实体类型',
  'cond.relation_solidification': '关系固化',
  'cond.relation_split': '关系拆分',
  'cond.standard_upgrade': '标准升版',
  'wiki.layer.index': '索引',
  'wiki.layer.domain_overview': '领域概览',
  'wiki.layer.source_summary': '源文档摘要',
  'observ.endpointHint': '',                                  // 生产隐藏调试提示
  'gtreview.subtitleClean': '决策书 §5.3 · 从高有用率查询反向构造标注集',
  'gtreview.minUsefulRate': '最低有用率',
  'gtreview.minSamples': '最小样本数',
  'myclaimed.subtitleClean': '按认领人筛选 · 批量决策',
  'wq.emptyClean': '暂无评分数据（先编译几次 Wiki 页）',
  'observ.legendApproveRejectPending': '批/驳/待',
  'observ.commonRejectReasons': '常见驳回',
  'pipeline.title': '知识体系建立 · 完整流程',
  'pipeline.subtitle': '从导入到出 Schema · 6 步',
  'pipeline.empty': '尚无项目 — 请先新建项目',
  'pipeline.switch': '切项目 / 新建项目',
  'pipeline.matrix': '矩阵审核台',
  'pipeline.run': '运行',
  'pipeline.s1.label': '1. 项目',
  'pipeline.s1.desc': '选行业模板',
  'pipeline.s2.label': '2. 上传',
  'pipeline.s2.desc': '飞书/钉钉/本地',
  'pipeline.s3.label': '3. 去噪审核',
  'pipeline.s3.desc': '保留/归档/丢弃',
  'pipeline.s4.label': '4. 知识体系',
  'pipeline.s4.desc': '四级 Schema',
  'pipeline.s5.label': '5. Wiki',
  'pipeline.s5.desc': '编译产物',
  'pipeline.s6.label': '6. 图谱',
  'pipeline.s6.desc': '实体关系',
  'pipeline.running': '运行中',
  'common.loading': '加载中...',
  'common.loadFailed': '加载失败',
  'observ.gtSet': 'Ground Truth 集',
  'observ.notEvaluated': '尚未运行评估',
  'observ.noReports': '尚无运行报告（先在 SME 端运行 recall-eval）',
  'observ.recallEvalHistory': '召回评估历史趋势',
  'observ.row.totalDecisions': '总决策数',
  'observ.row.approveReject': '本体批准 / 驳回',
  'observ.row.approvalRate': '批准率',
  'observ.row.promoteRollback': '灰度切换 / 回滚',
  'observ.row.promoteRatio': '切换 / 回滚比',
  'observ.row.queryTotalHits': '查询总数 / 命中数',
  'observ.row.hitRate': '命中率',
  'observ.row.avgLatency': '平均延时',
  'observ.row.p95Latency': 'P95 延时',
  'observ.row.feedbackRate': '用户反馈率',
  'observ.row.usefulRate': '有用率',
  'observ.row.activeWindow': '活跃观察期',
  'observ.row.alerting': '告警中',
  'observ.row.totalWindow': '历史观察期',
  'observ.row.gtCount': 'Ground Truth 集',
  'observ.row.latestRecall': '召回率',
  'observ.row.latestPrecision': '精确率',
  'observ.row.latestF1': 'F1',
  'observ.row.k': 'K',
  'observ.row.totalQueries': '查询总数',
  'observ.row.evalAt': '评估时间',
  'observ.row.recallTrend': '召回率趋势',
  'observ.row.precisionTrend': '精确率趋势',
  'observ.row.f1Trend': 'F1 趋势',
  'observ.row.recallDelta': '召回率变化',
  'observ.row.precisionDelta': '精确率变化',
  'observ.row.f1Delta': 'F1 变化',
  'observ.row.improving': '上升',
  'observ.row.degrading': '下降',
  'observ.row.stable': '稳定',
  'observ.row.recallTrendPair': '召回率（基线 → 当前）',
  'reader.routeLabel': '本次走的路径',
  'reader.routeShown': '路径',
  'observ.fetchFailed': '请求失败',
  'observ.status.watching': '观察中',
  'observ.status.alert': '告警',
  'observ.status.expired': '已过期',
  'observ.status.rolled_back': '已回滚',
  'condhealth.suggest.low_samples': '样本不足（{total} < {min_samples}），暂无法评估 prompt 健康度',
  'condhealth.suggest.all_pending': '全部待审，等 SME 审批后再评估',
  'condhealth.suggest.low_approve': '接受率偏低（{approve_rate_pct}），建议收紧触发阈值或细化 prompt 例子；可参考常见驳回理由调优',
  'condhealth.suggest.mid_approve': '中等接受率（{approve_rate_pct}），建议样本扩大后再评估；可关注常见驳回理由',
  'condhealth.suggest.high_approve': '接受率高（{approve_rate_pct}），prompt 健康',
  'condhealth.suggest.unclassified': '无法分类的提议（缺 entity_type 和 relation_type）',
  // M18 #4 · 反馈原因可视化 (zh)
  'observ.feedbackReasons.title': '反馈原因 Top 5（无用反馈）',
  'observ.feedbackReasons.empty': '暂无负反馈原因',
  'observ.feedbackReasons.totalNegFeedback': '负反馈样本数',
};

const en: Dict = {
  'brand.name': 'Wiki-Map',
  'brand.tagline': 'Knowledge Atlas',
  'mode.read': 'Read',
  'mode.manage': 'Manage',
  'mode.read.sub': 'Read Wiki / Search / Q&A',
  'mode.manage.sub': 'Compile / Audit / Configure',
  'topbar.settings': 'Settings',

  'reader.title': 'What are you looking for?',
  'reader.searchPlaceholder': 'Ask a question, e.g., how many approval levels does hot work need?',
  'reader.searchBtn': 'Search',
  'reader.searching': 'Thinking...',
  'reader.cardHotWiki': 'Hot Wiki',
  'reader.cardDomainMap': 'Knowledge Map',
  'reader.cardRecent': 'Recent Q&A',
  'reader.emptyWiki': 'No compiled wiki pages yet',
  'reader.emptyDomain': 'No recognized domains yet',
  'reader.emptyRecent': 'No questions asked yet',
  'reader.emptyProject': 'No project yet',
  'reader.emptyProjectHint': 'Go to /projects/new to create one',
  'reader.loadingProject': 'Loading projects...',
  'reader.sources': 'Sources',
  'reader.routeWiki': 'Wiki fast path',
  'reader.routeRag': 'RAG deep search',
  'reader.routeHybrid': 'Dual cross-check',

  'gov.title': 'Governance Inbox',
  'gov.subtitle': 'planner · daily 08:00 digest',
  'gov.seedDemo': 'Sample Items',
  'settings.tabSystem': 'Components',
  'gov.queueDetail': 'Queue Detail',
  'gov.countTotal': '{n} items',
  'gov.emptyQueue': 'No pending items (switch agent or refresh)',
  'gov.btnApprove': 'Approve',
  'gov.btnReject': 'Reject',
  'gov.btnEdit': 'Edit',
  'gov.kindDraft': 'draft pending',
  'gov.kindUnverified': 'unverified',
  'gov.kindConflict': 'conflict',
  'gov.kindStandardize': 'standardize',
  'gov.kindArchive': 'archive',
  'gov.health': 'Health Panel',
  'gov.healthSub': 'gardener · daily refresh',
  'gov.metricCoverage': 'Wiki Coverage',
  'gov.metricFallback': 'RAG Fallback',
  'gov.metricProvenance': 'Provenance',
  'gov.hintCoverage': 'compiled / recognized domains',
  'gov.hintFallback': 'lower is better',
  'gov.hintProvenance': 'Auditor sampling',

  'settings.title': 'Settings',
  'settings.tabAI': 'AI',
  'settings.tabTheme': 'Theme',
  'settings.tabLocale': 'Language',
  'settings.tabAbout': 'About',
  'settings.cancel': 'Cancel',
  'settings.save': 'Save',
  'settings.localeZh': '中文',
  'settings.localeEn': 'English',
  'settings.localeDesc': 'UI language only; backend data unaffected',
  // M16 #1 · ObservabilityDashboard (en)
  'observ.dashboard.title': 'Operations Observability',
  'observ.dashboard.subtitle': 'Decision book §5.3 · KAP IP engine · all-dimension observability',
  'observ.refresh': 'Refresh',
  'observ.card.decisions': 'Evolution decisions (M6 #3)',
  'observ.card.queries': 'Query recall (M7+M8)',
  'observ.card.observations': '7-day observation window (M5 #2 + M6 #2)',
  'observ.card.recallEval': 'Recall evaluation (M8 #2 + M9)',
  'observ.card.recallTrend': 'Recall trend (M9 #2)',
  'observ.card.conditionHealth': 'Condition health (M10 #2)',
  'observ.alert': 'Alert',
  'observ.empty': 'No data',
  'observ.loading': 'Loading...',
  // M17 #1 · matrix / my-claimed / gt / compare (en)
  'matrix.title': 'Governance Matrix',
  'matrix.subtitle': '4 roles × 6 workstations · Decision book §5.2 D6',
  'matrix.legendR': 'R = primary',
  'matrix.legendC': 'C = consulted',
  'matrix.legendI': 'I = informed (no ticket)',
  'matrix.totalPending': '{n} pending in total',
  'myclaimed.title': 'My claimed tickets',
  'myclaimed.subtitle': 'claimed_by · bulk decisions',
  'myclaimed.empty': 'No tickets claimed by {user} ({project})',
  'myclaimed.bulkApprove': 'Bulk approve',
  'myclaimed.bulkReject': 'Bulk reject',
  'myclaimed.selectAll': 'Select all',
  'myclaimed.unselectAll': 'Unselect all',
  'myclaimed.selected': 'Selected {selected} / {total}',
  'gtreview.title': 'Ground truth review',
  'gtreview.subtitle': 'Decision book §5.3 · Build ground truth from high useful_rate queries',
  'gtreview.candidates': 'Pending candidates',
  'gtreview.existing': 'Already in store',
  'gtreview.confirm': 'Confirm',
  'gtreview.skip': 'Skip',
  'gtreview.empty': 'No candidates',
  'compare.title': 'Multi-project comparison',
  'compare.subtitle': 'Pull all-project 4-dimension summaries for side-by-side comparison',
  'compare.empty': 'No project has operational data yet',
  'compare.col.project': 'project_id',
  'compare.col.decisions': 'Decisions (approval rate)',
  'compare.col.queries': 'Queries (hit rate)',
  'compare.col.useful': 'Useful rate (feedback count)',
  'compare.col.latency': 'avg/p95 ms',
  'compare.col.observations': 'Observations active/total',
  'compare.col.gt': 'GT set',
  'compare.col.recall': 'Latest R/P/F1',
  // M18 #2 · Wiki quality dashboard (en)
  'wq.title': 'Wiki Quality Dashboard',
  'wq.subtitle': 'Decision book §6 · 6-dim LLM-Critic (M17 #3)',
  'wq.aggCard': 'Aggregate summary',
  'wq.totalScored': 'Pages scored',
  'wq.alertingCount': 'Low-score alerts',
  'wq.avgOverall': 'Avg weighted score',
  'wq.radar': '6-dimension radar',
  'wq.alertList': 'Alerting pages',
  'wq.empty': 'No quality scores yet (run wiki_compiler first)',
  'wq.dim.consistency': 'Consistency',
  'wq.dim.completeness': 'Completeness',
  'wq.dim.evidence': 'Evidence',
  'wq.dim.repetition': 'Repetition',
  'wq.dim.freshness': 'Freshness',
  'wq.dim.cross_domain': 'Cross-domain',
  'wq.col.page': 'Page',
  'wq.col.type': 'Type',
  'wq.col.overall': 'Overall',
  'wq.col.scoredAt': 'Scored at',
  'wq.filterAlerting': 'Alerting only',
  'wq.trend': 'Trend over time',
  'wq.trendDelta': 'current vs earliest',
  'wq.trendAlert': 'Trend alert (drop > 10pp)',
  // M18 #3 · PromptVersion management (en)
  'pv.title': 'Prompt Version Manager',
  'pv.subtitle': 'M11 #4 / M12 / M16 · LLM self-learning loop',
  'pv.tabList': 'Versions',
  'pv.tabAB': 'AB Comparison',
  'pv.create': 'New version',
  'pv.deactivate': 'Deactivate',
  'pv.autoTune': 'Run auto-tune',
  'pv.col.versionId': 'Version ID',
  'pv.col.condition': 'Condition',
  'pv.col.language': 'Lang',
  'pv.col.activatedAt': 'Activated at',
  'pv.col.status': 'Status',
  'pv.col.note': 'Note',
  'pv.col.actions': 'Actions',
  'pv.col.sampleSize': 'Samples',
  'pv.col.approveRate': 'Approve rate',
  'pv.statusActive': 'Active',
  'pv.statusInactive': 'Inactive',
  'pv.empty': 'No versions yet (click "New version")',
  'pv.filterCondition': 'Condition',
  'pv.filterLanguage': 'Language',
  'pv.filterAll': 'All',
  'pv.confirmDeactivate': 'Deactivate version {id}?',
  'pv.autoTuneAction': 'Action: {action}',
  'pv.autoTuneNoop': 'Auto-tune complete (no change)',
  'pv.autoTuneReason': 'Reason',
  'pv.tabDiff': 'Diff',
  'pv.diffSelect': 'Select two versions to compare',
  'pv.diffSelectLeft': 'Left (older)',
  'pv.diffSelectRight': 'Right (newer)',
  'pv.diffEmpty': 'Please select two versions',
  'pv.diffNoChanges': 'system_prompt is identical between the two versions',
  'pv.diffExcerpt': 'Excerpt',
  'pv.diffSystem': 'system_prompt',
  'pv.diffStats': 'Diff: +{added} / -{removed}',
  // M21 i18n consolidation (en)
  'agent.curator': 'Curator',
  'agent.auditor': 'Auditor',
  'agent.deduper': 'Deduper',
  'agent.standardizer': 'Standardizer',
  'agent.gardener': 'Gardener',
  'agent.planner': 'Planner',
  'role.dg': 'DG',
  'role.sme': 'SME',
  'role.sec': 'SEC',
  'role.aiops': 'AIOps',
  'role.dg.full': 'Data Governor',
  'role.sme.full': 'Subject Matter Expert',
  'role.sec.full': 'Security Auditor',
  'role.aiops.full': 'AI Operator',
  'cond.new_entity_type': 'New entity type',
  'cond.relation_solidification': 'Relation solidification',
  'cond.relation_split': 'Relation split',
  'cond.standard_upgrade': 'Standard upgrade',
  'wiki.layer.index': 'Index',
  'wiki.layer.domain_overview': 'Domain overview',
  'wiki.layer.source_summary': 'Source summary',
  'observ.endpointHint': '',
  'gtreview.subtitleClean': 'Decision book §5.3 · Build ground truth from high-useful-rate queries',
  'gtreview.minUsefulRate': 'Min useful rate',
  'gtreview.minSamples': 'Min samples',
  'myclaimed.subtitleClean': 'Filter by claimer · bulk actions',
  'wq.emptyClean': 'No quality scores yet (compile some Wiki pages first)',
  'observ.legendApproveRejectPending': 'approved/rejected/pending',
  'observ.commonRejectReasons': 'Common reject reasons',
  'pipeline.title': 'Knowledge pipeline · 6 stages',
  'pipeline.subtitle': 'Import → Schema · 6 steps',
  'pipeline.empty': 'No project yet — create one first',
  'pipeline.switch': 'Switch / New project',
  'pipeline.matrix': 'Governance Matrix',
  'pipeline.run': 'Run',
  'pipeline.s1.label': '1. Project',
  'pipeline.s1.desc': 'Pick industry template',
  'pipeline.s2.label': '2. Upload',
  'pipeline.s2.desc': 'Lark / DingTalk / local',
  'pipeline.s3.label': '3. Denoise',
  'pipeline.s3.desc': 'Keep / archive / drop',
  'pipeline.s4.label': '4. Schema',
  'pipeline.s4.desc': '4-level taxonomy',
  'pipeline.s5.label': '5. Wiki',
  'pipeline.s5.desc': 'Compiled artifacts',
  'pipeline.s6.label': '6. Graph',
  'pipeline.s6.desc': 'Entities / relations',
  'pipeline.running': 'Running...',
  'common.loading': 'Loading...',
  'common.loadFailed': 'Load failed',
  'observ.gtSet': 'Ground truth set',
  'observ.notEvaluated': 'Not yet evaluated',
  'observ.noReports': 'No reports yet (run recall-eval from SME end first)',
  'observ.recallEvalHistory': 'Recall evaluation history',
  'observ.row.totalDecisions': 'Total decisions',
  'observ.row.approveReject': 'Proposals approved / rejected',
  'observ.row.approvalRate': 'Approval rate',
  'observ.row.promoteRollback': 'Promote / rollback',
  'observ.row.promoteRatio': 'Promote / rollback ratio',
  'observ.row.queryTotalHits': 'Total queries / hits',
  'observ.row.hitRate': 'Hit rate',
  'observ.row.avgLatency': 'Avg latency',
  'observ.row.p95Latency': 'P95 latency',
  'observ.row.feedbackRate': 'Feedback coverage',
  'observ.row.usefulRate': 'Useful rate',
  'observ.row.activeWindow': 'Active windows',
  'observ.row.alerting': 'Alerting',
  'observ.row.totalWindow': 'Total windows',
  'observ.row.gtCount': 'Ground truth set',
  'observ.row.latestRecall': 'Recall',
  'observ.row.latestPrecision': 'Precision',
  'observ.row.latestF1': 'F1',
  'observ.row.k': 'K',
  'observ.row.totalQueries': 'Total queries',
  'observ.row.evalAt': 'Evaluated at',
  'observ.row.recallTrend': 'Recall trend',
  'observ.row.precisionTrend': 'Precision trend',
  'observ.row.f1Trend': 'F1 trend',
  'observ.row.recallDelta': 'Recall delta',
  'observ.row.precisionDelta': 'Precision delta',
  'observ.row.f1Delta': 'F1 delta',
  'observ.row.improving': 'Improving',
  'observ.row.degrading': 'Degrading',
  'observ.row.stable': 'Stable',
  'observ.row.recallTrendPair': 'Recall (baseline → current)',
  'reader.routeLabel': 'Route used',
  'reader.routeShown': 'Route',
  'observ.fetchFailed': 'Request failed',
  'observ.status.watching': 'Watching',
  'observ.status.alert': 'Alert',
  'observ.status.expired': 'Expired',
  'observ.status.rolled_back': 'Rolled back',
  'condhealth.suggest.low_samples': 'Insufficient samples ({total} < {min_samples}); cannot assess prompt health yet',
  'condhealth.suggest.all_pending': 'All pending; wait for SME review before assessment',
  'condhealth.suggest.low_approve': 'Low approval rate ({approve_rate_pct}); tighten trigger threshold or refine prompt examples; review common reject reasons',
  'condhealth.suggest.mid_approve': 'Moderate approval rate ({approve_rate_pct}); collect more samples before reassessing',
  'condhealth.suggest.high_approve': 'High approval rate ({approve_rate_pct}); prompt healthy',
  'condhealth.suggest.unclassified': 'Unclassifiable proposal (missing entity_type and relation_type)',
  // M18 #4 · Feedback reasons visualization (en)
  'observ.feedbackReasons.title': 'Top 5 feedback reasons (negative)',
  'observ.feedbackReasons.empty': 'No negative feedback reasons yet',
  'observ.feedbackReasons.totalNegFeedback': 'Negative feedback samples',
};

const DICTS: Record<Locale, Dict> = { zh, en };

export function translate(locale: Locale, key: TranslationKey, vars?: Record<string, string | number>): string {
  const raw = DICTS[locale]?.[key] ?? DICTS.zh[key] ?? key;
  if (!vars) return raw;
  return raw.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? `{${k}}`));
}
