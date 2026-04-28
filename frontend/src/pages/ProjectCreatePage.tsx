/**
 * @file ProjectCreatePage.tsx
 * @description 项目创建页面 — 三步向导：选择行业模板 -> 预览知识体系 -> 填写项目信息并创建
 *
 * 主要流程：
 * 1. 选择行业（能源/制造/IT/金融/医疗等），系统推荐对应的四级知识体系模板
 * 2. 预览知识体系树形结构（可展开/折叠各层级）
 * 3. 填写项目名称和描述，确认创建后跳转至项目详情页
 */

import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, ArrowRight, Check, ChevronDown, ChevronRight, BookOpen } from 'lucide-react';
import {
  fetchIndustries,
  fetchIndustryTemplate,
  createProject,
  type IndustryItem,
  type TaxonomyNode,
} from '@/services/projectApi';

/** 行业卡片颜色映射 */
const INDUSTRY_COLORS: Record<string, string> = {
  energy: '#f59e0b',
  manufacturing: '#6366f1',
  it: '#3b82f6',
  finance: '#10b981',
  healthcare: '#ef4444',
};

/** 创建向导的三个步骤名称 */
const STEPS = ['选择行业', '预览知识体系', '填写信息'];

// ── 知识体系预览树组件 ──────────────────────────

/**
 * 知识体系预览树组件 — 递归渲染行业模板的多级知识分类
 * @param nodes 当前层级的节点列表
 * @param depth 当前递归深度（用于缩进和颜色）
 */
function TaxonomyTree({ nodes, depth = 0 }: { nodes: TaxonomyNode[]; depth?: number }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set()); // 展开的节点ID集合

  /** 切换节点展开/折叠 */
  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  return (
    <div className={depth > 0 ? 'ml-4' : ''}>
      {nodes.map((node) => {
        const hasChildren = node.children && node.children.length > 0;
        const isOpen = expanded.has(node.id);
        const levelColors = ['var(--color-accent)', 'var(--color-success)', 'var(--color-info)', 'var(--color-warning)'];
        const dotColor = levelColors[Math.min(depth, 3)];

        return (
          <div key={node.id} className="mb-1">
            <button
              onClick={() => hasChildren && toggle(node.id)}
              className="flex items-center gap-2 w-full text-left px-2 py-1.5 rounded-md text-sm transition-colors text-th-text-primary"
            >
              {hasChildren ? (
                isOpen ? <ChevronDown size={14} className="text-th-text-muted" /> : <ChevronRight size={14} className="text-th-text-muted" />
              ) : (
                <span className="w-3.5 h-3.5 flex items-center justify-center">
                  <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: dotColor }} />
                </span>
              )}
              <span className="font-medium">{node.name}</span>
              {node.description && (
                <span className="text-xs ml-1 truncate text-th-text-muted">
                  {node.description.slice(0, 40)}
                </span>
              )}
            </button>
            {hasChildren && isOpen && <TaxonomyTree nodes={node.children} depth={depth + 1} />}
          </div>
        );
      })}
    </div>
  );
}

// ── 项目创建主页面 ─────────────────────────────────────────

/**
 * 项目创建页面组件
 *
 * 提供三步向导引导用户创建知识库项目：
 * Step 0 — 选择行业（展示行业卡片网格）
 * Step 1 — 预览该行业的知识体系模板树
 * Step 2 — 填写项目名称和描述，确认创建
 */
export default function ProjectCreatePage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0); // 当前步骤索引（0/1/2）
  const [industries, setIndustries] = useState<IndustryItem[]>([]); // 可选行业列表
  const [selectedIndustry, setSelectedIndustry] = useState<string | null>(null); // 选中的行业 code
  const [taxonomy, setTaxonomy] = useState<TaxonomyNode[]>([]); // 行业模板知识体系树
  const [loadingTaxonomy, setLoadingTaxonomy] = useState(false); // 模板加载中
  const [projectName, setProjectName] = useState(''); // 项目名称输入
  const [projectDesc, setProjectDesc] = useState(''); // 项目描述输入
  const [creating, setCreating] = useState(false); // 正在创建项目
  const [error, setError] = useState(''); // 错误信息

  // 页面加载时获取可选行业列表
  useEffect(() => {
    fetchIndustries().then(setIndustries).catch(() => {});
  }, []);

  const selectedItem = industries.find((i) => i.code === selectedIndustry); // 当前选中的行业对象

  /** 进入下一步（Step0->加载模板->Step1, Step1->Step2） */
  const goNext = async () => {
    if (step === 0 && selectedIndustry) {
      setLoadingTaxonomy(true);
      try {
        const tmpl = await fetchIndustryTemplate(selectedIndustry);
        setTaxonomy(tmpl.taxonomy);
        setProjectName(selectedItem ? `${selectedItem.name}知识库` : '');
      } catch {
        setError('加载模板失败');
        return;
      } finally {
        setLoadingTaxonomy(false);
      }
      setStep(1);
    } else if (step === 1) {
      setStep(2);
    }
  };

  /** 返回上一步（Step0 时导航回项目列表页） */
  const goBack = () => {
    if (step > 0) setStep(step - 1);
    else navigate('/projects');
  };

  /** 提交创建项目请求（成功后跳转至项目详情页） */
  const handleCreate = async () => {
    if (!selectedIndustry || !projectName.trim()) return;
    setCreating(true);
    setError('');
    try {
      const proj = await createProject({
        name: projectName.trim(),
        industry_code: selectedIndustry,
        description: projectDesc.trim(),
      });
      navigate(`/projects/${proj.id}`);
    } catch (e: any) {
      setError(e.message || '创建失败');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col page-enter bg-base">
      {/* Header */}
      <header
        className="border-b px-8 py-4 bg-elevated border-th-border"
      >
        <div className="max-w-4xl mx-auto flex items-center gap-4">
          <button
            onClick={goBack}
            className="p-2 rounded-lg transition-colors text-th-text-secondary"
          >
            <ArrowLeft size={18} />
          </button>
          <div className="flex items-center gap-3">
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center bg-accent"
            >
              <BookOpen size={16} className="text-white" />
            </div>
            <h1 className="text-base font-semibold text-th-text-primary">
              新建项目
            </h1>
          </div>
        </div>
      </header>

      {/* Step indicator */}
      <div className="px-8 py-4 bg-elevated">
        <div className="max-w-4xl mx-auto flex items-center gap-2">
          {STEPS.map((s, i) => (
            <div key={s} className="flex items-center gap-2">
              <div
                className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                  i < step ? 'bg-success text-white' : i === step ? 'bg-accent text-white' : 'bg-hover text-th-text-muted'
                }`}
              >
                {i < step ? <Check size={12} /> : i + 1}
              </div>
              <span
                className={`text-sm ${i === step ? 'text-th-text-primary' : 'text-th-text-muted'}`}
              >
                {s}
              </span>
              {i < STEPS.length - 1 && (
                <div className="w-8 h-px mx-1 bg-[var(--color-border)]" />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Content */}
      <main className="flex-1 px-8 py-8">
        <div className="max-w-4xl mx-auto">
          {/* Step 0: Select industry */}
          {step === 0 && (
            <div>
              <h2 className="text-lg font-semibold mb-2 text-th-text-primary">
                选择行业
              </h2>
              <p className="text-sm mb-6 text-th-text-muted">
                不同行业有不同的知识体系架构，选择后系统将推荐对应的四级知识体系模板
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {industries.map((ind) => {
                  const isSelected = selectedIndustry === ind.code;
                  const color = INDUSTRY_COLORS[ind.code] || '#6b7280';
                  return (
                    <button
                      key={ind.code}
                      onClick={() => setSelectedIndustry(ind.code)}
                      className={`text-left p-5 rounded-xl border-2 transition-all bg-surface ${
                        isSelected ? 'shadow-md' : 'border-th-border'
                      }`}
                      style={{
                        ...(isSelected ? { borderColor: color } : {}),
                      }}
                    >
                      <div className="flex items-center gap-3 mb-3">
                        <div
                          className="w-10 h-10 rounded-lg flex items-center justify-center text-white font-bold"
                          style={{ backgroundColor: color }}
                        >
                          {ind.name.charAt(0)}
                        </div>
                        <div>
                          <div className="font-semibold text-th-text-primary">
                            {ind.name}
                          </div>
                          <div className="text-xs text-th-text-muted">
                            {ind.name_en}
                          </div>
                        </div>
                      </div>
                      <p className="text-xs mb-2 line-clamp-2 text-th-text-secondary">
                        {ind.description}
                      </p>
                      <div className="flex gap-3 text-xs text-th-text-muted">
                        <span>{ind.department_count} 个部门</span>
                        <span>{ind.domain_count} 个知识域</span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Step 1: Preview taxonomy */}
          {step === 1 && (
            <div>
              <h2 className="text-lg font-semibold mb-2 text-th-text-primary">
                知识体系预览
              </h2>
              <p className="text-sm mb-4 text-th-text-muted">
                以下是{selectedItem?.name}行业推荐的四级知识体系架构，创建后可在"知识体系"页面调整
              </p>
              {loadingTaxonomy ? (
                <div className="py-10 text-center text-th-text-muted">
                  加载中...
                </div>
              ) : (
                <div
                  className="p-4 rounded-xl border max-h-[500px] overflow-y-auto bg-surface border-th-border"
                >
                  <TaxonomyTree nodes={taxonomy} />
                </div>
              )}
            </div>
          )}

          {/* Step 2: Project info */}
          {step === 2 && (
            <div>
              <h2 className="text-lg font-semibold mb-2 text-th-text-primary">
                项目信息
              </h2>
              <p className="text-sm mb-6 text-th-text-muted">
                为您的知识库项目命名
              </p>
              <div className="max-w-lg space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-1 text-th-text-secondary">
                    项目名称 *
                  </label>
                  <input
                    type="text"
                    value={projectName}
                    onChange={(e) => setProjectName(e.target.value)}
                    placeholder="例如：XX公司安全生产知识库"
                    className="w-full px-3 py-2 rounded-lg border text-sm bg-base border-th-border text-th-text-primary"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1 text-th-text-secondary">
                    项目描述
                  </label>
                  <textarea
                    value={projectDesc}
                    onChange={(e) => setProjectDesc(e.target.value)}
                    placeholder="简要描述项目用途..."
                    rows={3}
                    className="w-full px-3 py-2 rounded-lg border text-sm resize-none bg-base border-th-border text-th-text-primary"
                  />
                </div>
                <div
                  className="p-3 rounded-lg text-sm flex items-center gap-3 bg-hover text-th-text-secondary"
                >
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center text-white font-bold shrink-0"
                    style={{ backgroundColor: INDUSTRY_COLORS[selectedIndustry || ''] || '#6b7280' }}
                  >
                    {selectedItem?.name.charAt(0)}
                  </div>
                  <div>
                    <div className="text-th-text-primary">{selectedItem?.name}</div>
                    <div className="text-xs">
                      {selectedItem?.department_count} 个部门 / {selectedItem?.domain_count} 个知识域
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="mt-4 p-3 rounded-lg text-sm bg-[var(--color-error-bg)] text-th-error">
              {error}
            </div>
          )}
        </div>
      </main>

      {/* Footer buttons */}
      <footer
        className="border-t px-8 py-4 bg-elevated border-th-border"
      >
        <div className="max-w-4xl mx-auto flex justify-between">
          <button
            onClick={goBack}
            className="px-4 py-2 rounded-lg text-sm border border-th-border text-th-text-secondary"
          >
            {step === 0 ? '取消' : '上一步'}
          </button>
          {step < 2 ? (
            <button
              onClick={goNext}
              disabled={step === 0 && !selectedIndustry}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-white disabled:opacity-40 bg-accent"
            >
              下一步
              <ArrowRight size={14} />
            </button>
          ) : (
            <button
              onClick={handleCreate}
              disabled={!projectName.trim() || creating}
              className="flex items-center gap-2 px-6 py-2 rounded-lg text-sm font-medium text-white disabled:opacity-40 bg-accent"
            >
              {creating ? '创建中...' : '创建项目'}
              <Check size={14} />
            </button>
          )}
        </div>
      </footer>
    </div>
  );
}
