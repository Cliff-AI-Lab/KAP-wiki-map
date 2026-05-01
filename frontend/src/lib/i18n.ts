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
  | 'compare.col.recall';

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
  'gov.subtitle': 'planner · 每日 08:00 合单',
  'gov.seedDemo': '种入示例工单',
  'settings.tabSystem': '组件状态',
  'gov.queueDetail': '工单详情',
  'gov.countTotal': '共 {n} 条',
  'gov.emptyQueue': '无待审工单（切换上方 Agent 或刷新）',
  'gov.btnApprove': '通过',
  'gov.btnReject': '打回',
  'gov.btnEdit': '改',
  'gov.kindDraft': 'draft 待审',
  'gov.kindUnverified': '未溯源',
  'gov.kindConflict': '事实冲突',
  'gov.kindStandardize': '实体归一',
  'gov.kindArchive': '建议归档',
  'gov.health': '健康面板',
  'gov.healthSub': 'gardener · 每日刷新',
  'gov.metricCoverage': 'Wiki 覆盖率',
  'gov.metricFallback': 'RAG 兜底率',
  'gov.metricProvenance': '溯源完整度',
  'gov.hintCoverage': '已编译 / 已识别域',
  'gov.hintFallback': '数值越低说明治理起效',
  'gov.hintProvenance': 'Auditor 统计',

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
};

const DICTS: Record<Locale, Dict> = { zh, en };

export function translate(locale: Locale, key: TranslationKey, vars?: Record<string, string | number>): string {
  const raw = DICTS[locale]?.[key] ?? DICTS.zh[key] ?? key;
  if (!vars) return raw;
  return raw.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? `{${k}}`));
}
