/**
 * 智能分析结果页面（AnalysisPage）
 *
 * 书虫智能体的核心分析模块，对知识库进行多维度自动化分析并展示报告。
 *
 * 功能模块：
 * 1. 行业自动识别 —— 基于文档内容推断所属行业及置信度
 * 2. 重复文档检测 —— 发现完全相同或高度相似的文档组
 * 3. 版本关系识别 —— 自动识别文档的版本链（V1→V2→V3）
 * 4. 文档质量评分 —— 统计文档质量分布及常见问题
 * 5. 知识缺口分析 —— 按领域识别缺失的文档类型并给出建议
 *
 * @module pages/AnalysisPage
 */

import React, { useState, useEffect, useCallback } from 'react';
import { 
  Brain, 
  Copy, 
  GitBranch, 
  AlertTriangle, 
  CheckCircle,
  TrendingUp,
  FileWarning,
  Building2,
  Download,
  RefreshCw,
  Zap,
  FileText,
  Folder
} from 'lucide-react';
import { Card, Button, Badge } from '@/components/ui';
import { useProject } from '@/contexts/ProjectContext';

/**
 * 模拟分析数据（开发阶段使用，后续由后端 API 返回真实结果）
 *
 * 包含五大分析维度的样例数据：
 * - industryDetection: 行业识别结果（行业名称、置信度、各行业得分）
 * - duplicateGroups:   重复文档分组（完全相同 / 高度相似）
 * - versionChains:     版本链（同一文档的多版本时间线）
 * - qualityStats:      质量统计（平均分、分布、常见问题）
 * - knowledgeGaps:     知识缺口（缺失领域、优先级、改进建议）
 */
const MOCK_ANALYSIS = {
  industryDetection: {
    detected: "能源电力",       // 识别出的主行业
    confidence: 0.93,           // 置信度（0~1）
    scores: {                   // 各行业匹配得分
      "能源电力": 40,
      "制造业": 5,
      "化工": 3,
      "通用": 2,
    }
  },
  duplicateGroups: [
    {
      id: "dup_001",
      type: "similar",          // similar=高度相似, exact=完全相同
      similarity: 0.92,
      documents: ["锅炉点火操作规程.docx", "锅炉点火操作规程_V2.docx"],
    },
    {
      id: "dup_002",
      type: "exact",
      similarity: 1.0,
      documents: ["安全管理制度.pdf", "安全管理制度(1).pdf"],
    },
  ],
  versionChains: [
    {
      baseName: "锅炉点火操作规程",  // 版本链的基础文档名
      versions: [
        { name: "锅炉点火操作规程_V3.0.docx", version: "3.0", isLatest: true },
        { name: "锅炉点火操作规程_V2.0.docx", version: "2.0", isLatest: false },
        { name: "锅炉点火操作规程_V1.0.docx", version: "1.0", isLatest: false },
      ]
    },
    {
      baseName: "DCS系统技术规范",
      versions: [
        { name: "DCS系统技术规范_20240301.docx", version: "2024-03-01", isLatest: true },
        { name: "DCS系统技术规范_20230615.docx", version: "2023-06-15", isLatest: false },
      ]
    },
  ],
  qualityStats: {
    avgScore: 78.5,             // 全库平均质量分
    distribution: {             // 质量等级分布（百分比）
      "优秀(90-100)": 15,
      "良好(75-89)": 45,
      "一般(60-74)": 30,
      "较差(<60)": 10,
    },
    commonIssues: [             // 高频质量问题列表
      { issue: "缺少标题结构", count: 28 },
      { issue: "内容过短", count: 15 },
      { issue: "可能是扫描件", count: 8 },
      { issue: "文档可能过期", count: 5 },
    ]
  },
  knowledgeGaps: [              // 知识缺口列表（domain=领域, type=缺失类型）
    { domain: "安全", type: "应急预案", priority: "high", suggestion: "建议补充应急预案类文档" },
    { domain: "设备", type: "维护手册", priority: "high", suggestion: "建议补充设备维护手册" },
    { domain: "生产", type: "培训资料", priority: "medium", suggestion: "生产领域培训资料较少" },
  ]
};

/**
 * 智能分析页面组件
 *
 * 从后端获取分析结果并以卡片形式展示五大分析维度。
 * 支持手动触发"重新分析"和"导出报告"操作。
 */
const AnalysisPage: React.FC = () => {
  const { currentProject } = useProject();
  const [isProcessing, setIsProcessing] = useState(false);   // 是否正在执行分析
  const [analysis, setAnalysis] = useState<typeof MOCK_ANALYSIS>(MOCK_ANALYSIS); // 分析结果数据

  /** 从后端加载分析结果，失败时保留当前数据 */
  const loadAnalysis = useCallback(async () => {
    setIsProcessing(true);
    try {
      const pid = currentProject?.id || 'default';
      const res = await fetch(`/api/v1/analysis?project_id=${encodeURIComponent(pid)}`);
      if (res.ok) {
        const data = await res.json();
        setAnalysis(data);
      }
    } catch (e) {
      console.error('分析加载失败:', e);
    } finally {
      setIsProcessing(false);
    }
  }, [currentProject?.id]);

  useEffect(() => { loadAnalysis(); }, [loadAnalysis]);

  /** 点击"重新分析"按钮的处理函数 */
  const runAnalysis = () => { loadAnalysis(); };

  return (
    <div className="p-8 space-y-8 page-enter">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Brain className="text-accent" />
            智能分析
          </h1>
          <p className="text-th-text-muted mt-1">
            自动识别行业、检测重复、识别版本、评估质量、分析缺口
          </p>
        </div>
        <div className="flex gap-3">
          <Button variant="secondary" icon={<Download size={16} />}>
            导出报告
          </Button>
          <Button 
            icon={<RefreshCw size={16} className={isProcessing ? 'animate-spin' : ''} />}
            onClick={runAnalysis}
            loading={isProcessing}
          >
            重新分析
          </Button>
        </div>
      </div>

      {/* 行业识别 */}
      <Card className="p-6">
        <h3 className="font-semibold mb-4 flex items-center gap-2">
          <Building2 size={18} />
          行业自动识别
        </h3>
        <div className="flex items-center gap-8">
          <div>
            <div className="text-metric text-accent flex items-center gap-2">
              <Zap size={28} className="text-amber-500" />
              {analysis.industryDetection.detected}
            </div>
            <div className="text-sm text-th-text-muted mt-1">
              置信度: {(analysis.industryDetection.confidence * 100).toFixed(0)}%
            </div>
          </div>
          <div className="flex-1">
            <div className="text-sm text-th-text-muted mb-2">各行业得分</div>
            <div className="flex gap-2 flex-wrap">
              {Object.entries(analysis.industryDetection.scores).map(([industry, score]) => (
                <Badge 
                  key={industry} 
                  variant={industry === analysis.industryDetection.detected ? "success" : "neutral"}
                >
                  {industry}: {score}
                </Badge>
              ))}
            </div>
          </div>
        </div>
      </Card>

      {/* 两列布局 */}
      <div className="grid grid-cols-2 gap-6">
        {/* 重复文档检测 */}
        <Card className="p-6">
          <h3 className="font-semibold mb-4 flex items-center gap-2">
            <Copy size={18} />
            重复文档检测
            {analysis.duplicateGroups.length > 0 && (
              <Badge variant="warning">{analysis.duplicateGroups.length}组</Badge>
            )}
          </h3>
          {analysis.duplicateGroups.length > 0 ? (
            <div className="space-y-3">
              {analysis.duplicateGroups.map((group) => (
                <div 
                  key={group.id}
                  className="p-3 rounded-card glass-card"
                >
                  <div className="flex items-center justify-between mb-2">
                    <Badge variant={group.type === 'exact' ? 'error' : 'warning'}>
                      {group.type === 'exact' ? '完全相同' : '高度相似'}
                    </Badge>
                    <span className="text-sm text-th-text-muted">
                      相似度: {(group.similarity * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="text-sm space-y-1">
                    {group.documents.map((doc, i) => (
                      <div key={i} className="truncate flex items-center gap-1">
                        <FileText size={14} className="text-th-text-muted shrink-0" />
                        {doc}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-th-text-muted">
              <CheckCircle size={32} className="mx-auto mb-2 text-green-500" />
              未发现重复文档
            </div>
          )}
        </Card>

        {/* 版本关系识别 */}
        <Card className="p-6">
          <h3 className="font-semibold mb-4 flex items-center gap-2">
            <GitBranch size={18} />
            版本关系识别
            {analysis.versionChains.length > 0 && (
              <Badge variant="info">{analysis.versionChains.length}个版本链</Badge>
            )}
          </h3>
          <div className="space-y-4">
            {analysis.versionChains.map((chain, idx) => (
              <div key={idx} className="p-3 rounded-card glass-card">
                <div className="font-medium mb-2 flex items-center gap-2">
                  <Folder size={16} className="text-accent" />
                  {chain.baseName}
                </div>
                <div className="pl-4 border-l-2 border-th-border space-y-1">
                  {chain.versions.map((v, i) => (
                    <div key={i} className="flex items-center gap-2 text-sm">
                      <span className={v.isLatest ? 'text-green-500' : 'text-th-text-muted'}>
                        {v.isLatest ? '●' : '○'}
                      </span>
                      <span className={v.isLatest ? 'font-medium' : ''}>
                        {v.name}
                      </span>
                      {v.isLatest && (
                        <Badge variant="success" size="sm">最新</Badge>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* 文档质量评分 */}
      <Card className="p-6">
        <h3 className="font-semibold mb-4 flex items-center gap-2">
          <TrendingUp size={18} />
          文档质量评分
        </h3>
        <div className="grid grid-cols-4 gap-6">
          {/* 平均分 */}
          <div className="text-center">
            <div className="text-4xl font-bold text-accent">
              {analysis.qualityStats.avgScore.toFixed(1)}
            </div>
            <div className="text-sm text-th-text-muted">平均质量分</div>
          </div>

          {/* 分布 */}
          <div className="col-span-2">
            <div className="text-sm text-th-text-muted mb-2">质量分布</div>
            {Object.entries(analysis.qualityStats.distribution).map(([level, count]) => (
              <div key={level} className="flex items-center gap-2 mb-1">
                <span className="text-xs w-24">{level}</span>
                <div className="flex-1 h-4 bg-hover rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-accent rounded-full"
                    style={{ width: `${count}%` }}
                  />
                </div>
                <span className="text-xs w-8">{count}%</span>
              </div>
            ))}
          </div>

          {/* 常见问题 */}
          <div>
            <div className="text-sm text-th-text-muted mb-2">常见问题</div>
            <div className="space-y-1">
              {analysis.qualityStats.commonIssues.slice(0, 4).map((item, i) => (
                <div key={i} className="flex items-center justify-between text-sm">
                  <span className="truncate">{item.issue}</span>
                  <Badge variant="neutral" size="sm">{item.count}</Badge>
                </div>
              ))}
            </div>
          </div>
        </div>
      </Card>

      {/* 知识缺口分析 */}
      <Card className="p-6">
        <h3 className="font-semibold mb-4 flex items-center gap-2">
          <FileWarning size={18} />
          知识缺口分析
          {analysis.knowledgeGaps.filter(g => g.priority === 'high').length > 0 && (
            <Badge variant="error">
              {analysis.knowledgeGaps.filter(g => g.priority === 'high').length}个高优先级
            </Badge>
          )}
        </h3>
        <div className="space-y-3">
          {analysis.knowledgeGaps.map((gap, i) => (
            <div
              key={i}
              className={`p-4 rounded-card ${
                gap.priority === 'high'
                  ? 'bg-[var(--color-error-bg)] shadow-[0px_0px_0px_1px_var(--color-error-border)]'
                  : 'bg-[var(--color-warning-bg)] shadow-[0px_0px_0px_1px_var(--color-warning-border)]'
              }`}
            >
              <div className="flex items-center gap-3">
                <AlertTriangle 
                  size={18} 
                  className={gap.priority === 'high' ? 'text-red-500' : 'text-yellow-500'} 
                />
                <div className="flex-1">
                  <div className="font-medium">
                    「{gap.domain}」领域缺少「{gap.type}」
                  </div>
                  <div className="text-sm text-th-text-muted mt-1">
                    {gap.suggestion}
                  </div>
                </div>
                <Badge variant={gap.priority === 'high' ? 'error' : 'warning'}>
                  {gap.priority === 'high' ? '高优先级' : '中优先级'}
                </Badge>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
};

export default AnalysisPage;
