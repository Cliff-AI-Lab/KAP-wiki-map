/**
 * @file UploadPage.tsx
 * @description 知识上传页面 — 支持飞书/钉钉云平台文档导入与本地文件上传。
 *
 * 核心流程（分阶段向导）：
 * 1. 选择平台（飞书 / 钉钉 / 本地上传）
 * 2. 账号授权（云平台）或选择文件（本地）
 * 3. 选择文档（云平台树形文档选择器）
 * 4. 智能去噪（AI 分析文档质量并给出入库建议）
 * 5. 确认入库（将通过审核的文档写入知识库）
 *
 * 本地上传流程跳过授权阶段，直接进入文件选择。
 */

import React, { useState, useRef } from 'react';
import { FileText, FolderOpen, CheckCircle, Loader2, HardDrive, Upload, FolderUp, X, File, RefreshCw } from 'lucide-react';
import { Card, Button, Badge } from '@/components/ui';
import { FeishuIcon, DingTalkIcon } from '@/components/icons/BrandIcons';
import { useProject } from '@/contexts/ProjectContext';

/** 知识来源平台类型 */
type Platform = 'feishu' | 'dingtalk' | 'local';

/**
 * 云平台文档项 — 用于飞书/钉钉文档树的递归节点
 */
interface CloudDocItem {
  /** 文档唯一标识 */
  id: string;
  /** 文档/文件夹显示名 */
  name: string;
  /** 文档类型：folder 为文件夹，其余为叶子文档 */
  type: 'folder' | 'doc' | 'sheet' | 'docx' | 'pdf' | 'wiki' | 'file';
  /** 子节点列表（仅文件夹有） */
  children?: CloudDocItem[];
  /** 是否被选中 */
  selected?: boolean;
  /** 文件大小（字节） */
  size?: number;
  /** 最后更新时间 */
  updateTime?: string;
  /** 文档在线链接 */
  url?: string;
}

/**
 * 本地文件项 — 用于本地上传的文件条目
 */
interface LocalFileItem {
  /** 前端生成的唯一ID */
  id: string;
  /** 原始 File 对象（用于 FormData 上传） */
  file: File;
  /** 文件名 */
  name: string;
  /** 文件大小（字节） */
  size: number;
  /** 文件扩展名 */
  type: string;
  /** 相对路径（文件夹上传时含子路径） */
  path: string;
  /** 处理状态 */
  status: 'pending' | 'processing' | 'done' | 'error';
  /** 错误信息 */
  error?: string;
}

// 支持的本地文件类型
const SUPPORTED_EXTENSIONS = ['.docx', '.doc', '.pdf', '.xlsx', '.xls', '.pptx', '.ppt', '.txt', '.md'];

// 文件类型图标颜色
const FILE_TYPE_COLORS: Record<string, string> = {
  'docx': '#2B579A',
  'doc': '#2B579A',
  'pdf': '#F40F02',
  'xlsx': '#217346',
  'xls': '#217346',
  'pptx': '#D24726',
  'ppt': '#D24726',
  'txt': '#666666',
  'md': '#083FA1',
  'wiki': '#3370FF',
  'sheet': '#217346',
};

// 获取文件扩展名
const getFileExtension = (filename: string): string => {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  return ext;
};

// 格式化文件大小
const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
};

// 检查文件是否支持
const isFileSupported = (file: File): boolean => {
  const ext = '.' + getFileExtension(file.name);
  return SUPPORTED_EXTENSIONS.includes(ext.toLowerCase());
};

// 平台配置
const platforms: { id: Platform; name: string; icon: React.ReactNode; color: string; description: string; authRequired: boolean }[] = [
  { 
    id: 'feishu', 
    name: '飞书', 
    icon: <FeishuIcon size={40} />, 
    color: '#3370FF', 
    description: '通过API连接飞书云文档、知识库',
    authRequired: true
  },
  { 
    id: 'dingtalk', 
    name: '钉钉', 
    icon: <DingTalkIcon size={40} />, 
    color: '#0089FF', 
    description: '通过API连接钉钉文档、云盘',
    authRequired: true
  },
  { 
    id: 'local', 
    name: '本地上传', 
    icon: <HardDrive size={40} />, 
    color: '#666', 
    description: '上传本地 Word、PDF、Excel 等文件',
    authRequired: false
  },
];

// 上传阶段（根据平台不同）
const getStages = (platform: Platform | null) => {
  if (platform === 'local') {
    return [
      { id: 1, name: '选择平台', description: '选择知识来源' },
      { id: 2, name: '选择文件', description: '选择本地文件或文件夹' },
      { id: 3, name: '智能去噪', description: 'AI筛选高质量内容' },
      { id: 4, name: '确认入库', description: '审核并入库' },
    ];
  }
  return [
    { id: 1, name: '选择平台', description: '选择知识来源' },
    { id: 2, name: '账号授权', description: '登录并授权API访问' },
    { id: 3, name: '选择文档', description: '从云端选择文档' },
    { id: 4, name: '智能去噪', description: 'AI筛选高质量内容' },
    { id: 5, name: '确认入库', description: '审核并入库' },
  ];
};

/**
 * 知识上传页面组件
 *
 * 提供分阶段向导式交互，引导用户完成：平台选择 -> 授权/文件选择 -> 智能去噪 -> 确认入库。
 * 支持飞书、钉钉云平台文档导入以及本地文件（Word/PDF/Excel/PPT/TXT/MD）上传。
 */
export const UploadPage: React.FC = () => {
  const { currentProject } = useProject();
  const [currentStage, setCurrentStage] = useState(1); // 当前向导阶段编号
  const [selectedPlatform, setSelectedPlatform] = useState<Platform | null>(null); // 当前选中的平台
  const [_isAuthorized, setIsAuthorized] = useState(false); // 云平台授权状态
  const [isLoading, setIsLoading] = useState(false); // 通用加载标志
  const [authError, setAuthError] = useState<string | null>(null); // 授权错误信息

  // ── 云平台相关状态 ──
  const [cloudDocs, setCloudDocs] = useState<CloudDocItem[]>([]); // 云平台文档树数据
  const [selectedCloudDocs, setSelectedCloudDocs] = useState<Set<string>>(new Set()); // 已勾选的云文档ID集合
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set()); // 已展开的文件夹ID集合

  // ── 本地上传相关状态 ──
  const [localFiles, setLocalFiles] = useState<LocalFileItem[]>([]); // 已选择的本地文件列表
  const fileInputRef = useRef<HTMLInputElement>(null); // 文件选择input引用
  const folderInputRef = useRef<HTMLInputElement>(null); // 文件夹选择input引用

  // 选择平台
  const handleSelectPlatform = (platform: Platform) => {
    setSelectedPlatform(platform);
    setAuthError(null);
    
    if (platform === 'local') {
      // 本地上传直接进入文件选择
      setCurrentStage(2);
    } else {
      // 云平台进入授权阶段
      setCurrentStage(2);
    }
  };

  // 加载云平台文档列表
  const loadCloudDocuments = async () => {
    setIsLoading(true);
    
    try {
      // 尝试调用真实API
      const response = await fetch(`/api/platform/${selectedPlatform}/documents`);
      
      if (response.ok) {
        const data = await response.json();
        setCloudDocs(data.documents || []);
      } else {
        // 使用模拟数据
        loadMockCloudDocuments();
      }
    } catch (error) {
      console.error('加载文档失败:', error);
      // 使用模拟数据
      loadMockCloudDocuments();
    } finally {
      setIsLoading(false);
    }
  };

  // 加载模拟的云平台文档
  const loadMockCloudDocuments = () => {
    const mockData: CloudDocItem[] = selectedPlatform === 'feishu' ? [
      {
        id: 'wiki-1',
        name: '技术知识库',
        type: 'folder',
        children: [
          { id: 'wiki-1-1', name: '系统架构设计文档', type: 'wiki', size: 1024000, updateTime: '2026-03-10' },
          { id: 'wiki-1-2', name: 'API接口规范 v2.0', type: 'wiki', size: 512000, updateTime: '2026-03-09' },
          { id: 'wiki-1-3', name: '数据库设计说明', type: 'wiki', size: 256000, updateTime: '2026-03-08' },
        ],
      },
      {
        id: 'doc-1',
        name: '云文档',
        type: 'folder',
        children: [
          { id: 'doc-1-1', name: '产品需求文档PRD.docx', type: 'docx', size: 2048000, updateTime: '2026-03-10' },
          { id: 'doc-1-2', name: '项目计划表.xlsx', type: 'sheet', size: 128000, updateTime: '2026-03-07' },
        ],
      },
      {
        id: 'space-1',
        name: '共享空间',
        type: 'folder',
        children: [
          { id: 'space-1-1', name: '培训材料汇总', type: 'folder', children: [
            { id: 'space-1-1-1', name: '新员工入职手册.pdf', type: 'pdf', size: 3072000, updateTime: '2026-03-05' },
            { id: 'space-1-1-2', name: '技能培训PPT.pptx', type: 'file', size: 5120000, updateTime: '2026-03-04' },
          ]},
        ],
      },
    ] : [
      {
        id: 'ding-1',
        name: '钉钉文档',
        type: 'folder',
        children: [
          { id: 'ding-1-1', name: '部门工作手册', type: 'doc', size: 1024000, updateTime: '2026-03-10' },
          { id: 'ding-1-2', name: '流程制度汇编', type: 'doc', size: 2048000, updateTime: '2026-03-09' },
        ],
      },
      {
        id: 'ding-2',
        name: '知识库',
        type: 'folder',
        children: [
          { id: 'ding-2-1', name: '技术文档中心', type: 'folder', children: [
            { id: 'ding-2-1-1', name: '开发规范.docx', type: 'docx', size: 512000, updateTime: '2026-03-08' },
            { id: 'ding-2-1-2', name: '测试用例模板.xlsx', type: 'sheet', size: 256000, updateTime: '2026-03-07' },
          ]},
        ],
      },
    ];
    
    setCloudDocs(mockData);
    // 默认展开第一层
    setExpandedFolders(new Set(mockData.map(d => d.id)));
  };

  // 处理本地文件选择
  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files) return;
    
    const newFiles: LocalFileItem[] = [];
    const skippedFiles: string[] = [];
    
    Array.from(files).forEach((file, index) => {
      if (isFileSupported(file)) {
        newFiles.push({
          id: `local-${Date.now()}-${index}`,
          file,
          name: file.name,
          size: file.size,
          type: getFileExtension(file.name),
          path: (file as any).webkitRelativePath || file.name,
          status: 'pending',
        });
      } else {
        skippedFiles.push(file.name);
      }
    });
    
    setLocalFiles(prev => [...prev, ...newFiles]);
    event.target.value = '';
    
    if (skippedFiles.length > 0) {
      console.log('跳过不支持的文件:', skippedFiles);
    }
  };

  // 移除本地文件
  const removeLocalFile = (fileId: string) => {
    setLocalFiles(prev => prev.filter(f => f.id !== fileId));
  };

  // 清空所有本地文件
  const clearAllLocalFiles = () => {
    setLocalFiles([]);
  };

  // 切换文件夹展开
  const toggleFolderExpand = (folderId: string) => {
    const newExpanded = new Set(expandedFolders);
    if (newExpanded.has(folderId)) {
      newExpanded.delete(folderId);
    } else {
      newExpanded.add(folderId);
    }
    setExpandedFolders(newExpanded);
  };

  // 切换云文档选择
  const toggleCloudDocSelect = (docId: string) => {
    const newSelected = new Set(selectedCloudDocs);
    if (newSelected.has(docId)) {
      newSelected.delete(docId);
    } else {
      newSelected.add(docId);
    }
    setSelectedCloudDocs(newSelected);
  };

  // 获取所有叶子节点（可选择的文档）
  const getAllLeafDocs = (items: CloudDocItem[]): CloudDocItem[] => {
    const leaves: CloudDocItem[] = [];
    const traverse = (docs: CloudDocItem[]) => {
      docs.forEach(doc => {
        if (doc.children && doc.children.length > 0) {
          traverse(doc.children);
        } else if (doc.type !== 'folder') {
          leaves.push(doc);
        }
      });
    };
    traverse(items);
    return leaves;
  };

  // 全选/取消全选云文档
  const toggleSelectAllCloud = () => {
    const allLeaves = getAllLeafDocs(cloudDocs);
    if (selectedCloudDocs.size > 0) {
      setSelectedCloudDocs(new Set());
    } else {
      setSelectedCloudDocs(new Set(allLeaves.map(d => d.id)));
    }
  };

  // 进入去噪阶段
  const handleStartDenoise = () => {
    const stages = getStages(selectedPlatform);
    const denoiseStage = stages.find(s => s.name === '智能去噪');
    if (denoiseStage) {
      setCurrentStage(denoiseStage.id);
    }
  };

  // 确认入库
  const handleConfirmImport = () => {
    const stages = getStages(selectedPlatform);
    const confirmStage = stages.find(s => s.name === '确认入库');
    if (confirmStage) {
      setCurrentStage(confirmStage.id);
    }
  };


  // 重置状态
  const resetAll = () => {
    setCurrentStage(1);
    setSelectedPlatform(null);
    setIsAuthorized(false);
    setCloudDocs([]);
    setSelectedCloudDocs(new Set());
    setLocalFiles([]);
    setAuthError(null);
  };

  // 渲染进度条
  const renderProgress = () => {
    const stages = getStages(selectedPlatform);
    
    return (
      <div className="flex items-center gap-2 mb-8">
        {stages.map((stage, index) => (
          <React.Fragment key={stage.id}>
            <div className="flex items-center gap-2">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-all ${
                  currentStage >= stage.id
                    ? 'bg-accent text-white'
                    : 'bg-hover text-th-text-muted'
                }`}
              >
                {currentStage > stage.id ? <CheckCircle size={16} /> : stage.id}
              </div>
              <div className="hidden sm:block">
                <div className={`text-sm font-medium ${currentStage >= stage.id ? 'text-th-text-primary' : 'text-th-text-muted'}`}>
                  {stage.name}
                </div>
              </div>
            </div>
            {index < stages.length - 1 && (
              <div
                className={`flex-1 h-0.5 transition-all ${
                  currentStage > stage.id ? 'bg-accent' : 'bg-th-border'
                }`}
              />
            )}
          </React.Fragment>
        ))}
      </div>
    );
  };

  // 渲染平台选择
  const renderPlatformSelect = () => (
    <div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {platforms.map(platform => (
          <Card
            key={platform.id}
            className={`p-6 cursor-pointer transition-all hover:scale-[1.02] ${
              selectedPlatform === platform.id ? 'ring-2 ring-accent' : ''
            }`}
            onClick={() => handleSelectPlatform(platform.id)}
          >
            <div className="mb-4" style={{ color: platform.color }}>{platform.icon}</div>
            <h3 className="text-lg font-semibold mb-2" style={{ color: platform.color }}>
              {platform.name}
            </h3>
            <p className="text-sm text-th-text-muted">{platform.description}</p>
            {platform.authRequired && (
              <Badge variant="neutral" className="mt-3">需要API授权</Badge>
            )}
          </Card>
        ))}
      </div>
    </div>
  );

  // ── 云平台凭证配置状态 ──
  const [configStatus, setConfigStatus] = useState<any>(null); // 后端返回的配置状态
  const [appIdInput, setAppIdInput] = useState(''); // App ID / AppKey 输入
  const [appSecretInput, setAppSecretInput] = useState(''); // App Secret 输入
  const [showSecret, setShowSecret] = useState(false); // 是否明文显示密钥
  const [configStep, setConfigStep] = useState<'check' | 'guide' | 'input' | 'done'>('check'); // 配置子步骤

  // 检查平台配置状态
  const checkPlatformConfig = async () => {
    setIsLoading(true);
    try {
      const response = await fetch(`/api/platform/${selectedPlatform}/auth/status`);
      const data = await response.json();
      setConfigStatus(data);
      
      if (data.configured && data.authorized) {
        // 已配置且授权有效，直接进入文档选择
        setConfigStep('done');
        setCurrentStage(3);
        await loadCloudDocuments();
      } else if (data.configured && !data.authorized) {
        // 已配置但授权失败
        setConfigStep('input');
        setAuthError(data.error || '授权验证失败，请重新配置凭证');
      } else {
        // 未配置，显示配置指南
        setConfigStep('guide');
      }
    } catch (error) {
      // API不可用，显示配置界面
      setConfigStep('guide');
    } finally {
      setIsLoading(false);
    }
  };

  // 保存凭证配置
  const saveCredentials = async () => {
    if (!appIdInput || !appSecretInput) {
      setAuthError('请输入完整的凭证信息');
      return;
    }
    
    setIsLoading(true);
    setAuthError(null);
    
    try {
      const response = await fetch(`/api/platform/${selectedPlatform}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          platform: selectedPlatform,
          app_id: appIdInput,
          app_secret: appSecretInput,
        }),
      });
      
      if (response.ok) {
        // 配置成功，进入文档选择
        setConfigStep('done');
        setCurrentStage(3);
        await loadCloudDocuments();
      } else {
        const error = await response.json();
        setAuthError(error.detail || '凭证验证失败');
      }
    } catch (error) {
      setAuthError('保存配置失败，请检查网络连接');
    } finally {
      setIsLoading(false);
    }
  };

  // 进入云平台授权阶段时自动检查配置状态（已配置则跳到文档选择）
  React.useEffect(() => {
    if (currentStage === 2 && selectedPlatform && selectedPlatform !== 'local') {
      checkPlatformConfig();
    }
  }, [currentStage, selectedPlatform]);

  // 渲染云平台授权
  const renderCloudAuthorize = () => {
    const platform = platforms.find(p => p.id === selectedPlatform);
    const platformName = platform?.name || '';
    const platformColor = platform?.color || '#666';
    
    // 加载中
    if (isLoading && configStep === 'check') {
      return (
        <div className="max-w-lg mx-auto text-center py-12">
          <Loader2 size={32} className="animate-spin mx-auto mb-4" style={{ color: platformColor }} />
          <p className="text-th-text-muted">正在检查{platformName}授权状态...</p>
        </div>
      );
    }
    
    return (
      <div className="max-w-2xl mx-auto">
        {/* 头部 */}
        <div className="text-center mb-8">
          <div className="mb-4 flex justify-center" style={{ color: platformColor }}>
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center" style={{ backgroundColor: `${platformColor}15` }}>
              {platform?.icon}
            </div>
          </div>
          <h3 className="text-xl font-semibold mb-2">配置{platformName}应用</h3>
          <p className="text-th-text-muted">
            需要在{platformName}开放平台创建应用并获取凭证
          </p>
        </div>

        {/* 错误提示 */}
        {authError && (
          <div className="mb-6 p-4 rounded-btn" style={{ background: 'rgba(255, 99, 99, 0.08)', color: 'var(--color-error)', boxShadow: '0px 0px 0px 1px rgba(255, 99, 99, 0.20)' }}>
            <strong>错误：</strong>{authError}
          </div>
        )}

        {/* 配置指南 */}
        {(configStep === 'guide' || configStep === 'input') && (
          <div className="space-y-6">
            {/* 步骤说明 */}
            <Card className="p-6">
              <h4 className="font-semibold mb-4 flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-accent text-[var(--color-bg-base)] text-sm flex items-center justify-center">1</span>
                创建{platformName}应用并申请权限
              </h4>
              
              <div className="space-y-3 text-sm">
                {selectedPlatform === 'feishu' ? (
                  <>
                    <div className="flex items-start gap-2">
                      <span className="text-th-text-muted">①</span>
                      <span>登录 <a href="https://open.feishu.cn/app" target="_blank" className="text-accent hover:underline">飞书开放平台</a>，创建「企业自建应用」</span>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="text-th-text-muted">②</span>
                      <span>在「凭证与基础信息」获取 <strong>App ID</strong> 和 <strong>App Secret</strong></span>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="text-th-text-muted">③</span>
                      <div>
                        <span>在「权限管理」申请以下权限：</span>
                        <ul className="mt-2 ml-4 space-y-1 text-th-text-muted">
                          <li>• <code className="bg-hover px-1 rounded">wiki:wiki:readonly</code> - 知识库读取</li>
                          <li>• <code className="bg-hover px-1 rounded">docx:document:readonly</code> - 文档读取</li>
                          <li>• <code className="bg-hover px-1 rounded">drive:drive:readonly</code> - 云盘读取</li>
                          <li>• <code className="bg-hover px-1 rounded">drive:file:readonly</code> - 文件下载</li>
                        </ul>
                      </div>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="text-th-text-muted">④</span>
                      <span>发布应用版本，等待<strong>企业管理员审批</strong>通过</span>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="flex items-start gap-2">
                      <span className="text-th-text-muted">①</span>
                      <span>登录 <a href="https://open.dingtalk.com/developer" target="_blank" className="text-accent hover:underline">钉钉开放平台</a>，创建「企业内部应用」</span>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="text-th-text-muted">②</span>
                      <span>获取 <strong>AppKey</strong> 和 <strong>AppSecret</strong></span>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="text-th-text-muted">③</span>
                      <div>
                        <span>在「权限管理」申请以下权限：</span>
                        <ul className="mt-2 ml-4 space-y-1 text-th-text-muted">
                          <li>• 通讯录个人信息读取</li>
                          <li>• 云盘空间管理</li>
                          <li>• 文档读取权限</li>
                        </ul>
                      </div>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="text-th-text-muted">④</span>
                      <span>提交发布申请，等待<strong>管理员审批</strong></span>
                    </div>
                  </>
                )}
              </div>
            </Card>

            {/* 凭证输入 */}
            <Card className="p-6">
              <h4 className="font-semibold mb-4 flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-accent text-[var(--color-bg-base)] text-sm flex items-center justify-center">2</span>
                输入应用凭证
              </h4>
              
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-1">
                    {selectedPlatform === 'feishu' ? 'App ID' : 'AppKey'}
                  </label>
                  <input
                    type="text"
                    value={appIdInput}
                    onChange={(e) => setAppIdInput(e.target.value)}
                    placeholder={selectedPlatform === 'feishu' ? 'cli_xxxxxxxx' : 'dingxxxxxxxx'}
                    className="w-full px-3 py-2 rounded-btn bg-transparent text-th-text-primary placeholder:text-th-text-muted focus:outline-none"
                    style={{ boxShadow: 'var(--shadow-input)' }}
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium mb-1">
                    {selectedPlatform === 'feishu' ? 'App Secret' : 'AppSecret'}
                  </label>
                  <div className="relative">
                    <input
                      type={showSecret ? 'text' : 'password'}
                      value={appSecretInput}
                      onChange={(e) => setAppSecretInput(e.target.value)}
                      placeholder="请输入密钥"
                      className="w-full px-3 py-2 rounded-btn bg-transparent text-th-text-primary placeholder:text-th-text-muted focus:outline-none pr-20"
                      style={{ boxShadow: 'var(--shadow-input)' }}
                    />
                    <button
                      type="button"
                      onClick={() => setShowSecret(!showSecret)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-sm text-th-text-muted hover:text-th-text-primary"
                    >
                      {showSecret ? '隐藏' : '显示'}
                    </button>
                  </div>
                </div>
                
                <Button
                  onClick={saveCredentials}
                  disabled={isLoading || !appIdInput || !appSecretInput}
                  className="w-full"
                  size="lg"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="animate-spin mr-2" size={18} />
                      验证中...
                    </>
                  ) : (
                    <>
                      <CheckCircle className="mr-2" size={18} />
                      验证并保存
                    </>
                  )}
                </Button>
              </div>
            </Card>

            {/* 已授权的权限 */}
            {configStatus?.permissions?.length > 0 && (
              <div className="p-4 rounded-card" style={{ background: 'rgba(95, 201, 146, 0.06)', boxShadow: '0px 0px 0px 1px rgba(95, 201, 146, 0.20)' }}>
                <h5 className="font-medium mb-2" style={{ color: 'var(--color-success)' }}>已授权权限</h5>
                <div className="flex flex-wrap gap-2">
                  {configStatus.permissions.map((p: string) => (
                    <Badge key={p} variant="success">{p}</Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* 返回按钮 */}
        <div className="mt-6 pt-4" style={{ boxShadow: 'inset 0 1px 0 var(--color-border)' }}>
          <button
            className="text-sm text-th-text-muted hover:text-th-text-primary"
            onClick={() => {
              setCurrentStage(1);
              setSelectedPlatform(null);
              setConfigStep('check');
              setAppIdInput('');
              setAppSecretInput('');
              setAuthError(null);
            }}
          >
            ← 返回选择平台
          </button>
        </div>
      </div>
    );
  };

  // 递归渲染云文档树
  const renderCloudDocTree = (items: CloudDocItem[], level: number = 0) => {
    return items.map(item => {
      const isFolder = item.type === 'folder' || (item.children && item.children.length > 0);
      const isExpanded = expandedFolders.has(item.id);
      const typeColor = FILE_TYPE_COLORS[item.type] || '#666';
      
      return (
        <div key={item.id} style={{ marginLeft: level * 16 }}>
          {isFolder ? (
            // 文件夹
            <div>
              <div
                className="flex items-center gap-2 p-2 rounded-btn cursor-pointer hover:bg-hover"
                onClick={() => toggleFolderExpand(item.id)}
              >
                <FolderOpen size={18} className={`transition-transform ${isExpanded ? '' : '-rotate-90'}`} style={{ color: typeColor }} />
                <span className="font-medium">{item.name}</span>
                <Badge variant="neutral" className="ml-2">
                  {item.children?.length || 0}
                </Badge>
              </div>
              {isExpanded && item.children && (
                <div className="ml-2 border-l border-th-border pl-2">
                  {renderCloudDocTree(item.children, level + 1)}
                </div>
              )}
            </div>
          ) : (
            // 文档
            <label
              className={`flex items-center gap-3 p-2 rounded-btn cursor-pointer transition-all ${
                selectedCloudDocs.has(item.id)
                  ? 'bg-[rgba(85,179,255,0.10)]'
                  : 'hover:bg-hover'
              }`}
            >
              <input
                type="checkbox"
                checked={selectedCloudDocs.has(item.id)}
                onChange={() => toggleCloudDocSelect(item.id)}
                className="w-4 h-4 rounded"
              />
              <div 
                className="w-8 h-8 rounded flex items-center justify-center text-white text-xs font-bold flex-shrink-0"
                style={{ backgroundColor: typeColor }}
              >
                {item.type.substring(0, 3).toUpperCase()}
              </div>
              <span className="flex-1 truncate">{item.name}</span>
              <span className="text-xs text-th-text-muted flex-shrink-0">
                {item.updateTime}
              </span>
            </label>
          )}
        </div>
      );
    });
  };

  // 渲染云平台文档选择
  const renderCloudDocumentSelect = () => {
    const platform = platforms.find(p => p.id === selectedPlatform);
    const allLeaves = getAllLeafDocs(cloudDocs);
    
    return (
      <div>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2" style={{ color: platform?.color }}>
              <div className="w-6 h-6 flex items-center justify-center">
                {selectedPlatform === 'feishu' && <FeishuIcon size={24} />}
                {selectedPlatform === 'dingtalk' && <DingTalkIcon size={24} />}
              </div>
              <span className="font-medium">{platform?.name}</span>
            </div>
            <Badge variant="success">已连接</Badge>
          </div>
          <Button 
            variant="ghost" 
            size="sm" 
            onClick={loadCloudDocuments}
            disabled={isLoading}
          >
            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
            刷新
          </Button>
        </div>

        {isLoading ? (
          <div className="text-center py-12">
            <Loader2 size={32} className="animate-spin mx-auto mb-4 text-accent" />
            <p className="text-th-text-muted">正在加载文档列表...</p>
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between mb-4 p-3 bg-hover rounded-btn">
              <div className="flex items-center gap-4">
                <Button variant="secondary" size="sm" onClick={toggleSelectAllCloud}>
                  {selectedCloudDocs.size > 0 ? '取消全选' : '全选'}
                </Button>
                <span className="text-sm text-th-text-muted">
                  已选择 <strong>{selectedCloudDocs.size}</strong> / {allLeaves.length} 个文档
                </span>
              </div>
              <Button
                onClick={handleStartDenoise}
                disabled={selectedCloudDocs.size === 0}
              >
                下一步：智能去噪 →
              </Button>
            </div>

            <div className="glass-card rounded-card p-4 max-h-[400px] overflow-y-auto">
              {cloudDocs.length > 0 ? (
                renderCloudDocTree(cloudDocs)
              ) : (
                <div className="text-center py-8 text-th-text-muted">
                  <FolderOpen size={48} className="mx-auto mb-4 opacity-30" />
                  <p>暂无可用文档</p>
                </div>
              )}
            </div>
          </>
        )}

        <div className="mt-6 pt-4" style={{ boxShadow: 'inset 0 1px 0 var(--color-border)' }}>
          <button
            className="text-sm text-th-text-muted hover:text-th-text-primary"
            onClick={() => {
              setCurrentStage(1);
              setSelectedPlatform(null);
              setIsAuthorized(false);
              setCloudDocs([]);
              setSelectedCloudDocs(new Set());
            }}
          >
            ← 返回选择平台
          </button>
        </div>
      </div>
    );
  };

  // 渲染本地上传界面
  const renderLocalUpload = () => (
    <div>
      {/* 隐藏的文件输入框 */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept={SUPPORTED_EXTENSIONS.join(',')}
        onChange={handleFileSelect}
        className="hidden"
      />
      <input
        ref={folderInputRef}
        type="file"
        multiple
        // @ts-ignore
        webkitdirectory=""
        onChange={handleFileSelect}
        className="hidden"
      />

      {/* 上传区域 */}
      <div className="rounded-card p-8 mb-6 text-center" style={{ boxShadow: 'var(--shadow-input)' }}>
        <div className="flex justify-center gap-4 mb-6">
          <Button
            variant="secondary"
            size="lg"
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-2"
          >
            <Upload size={20} />
            选择文件
          </Button>
          
          <Button
            variant="secondary"
            size="lg"
            onClick={() => folderInputRef.current?.click()}
            className="flex items-center gap-2"
          >
            <FolderUp size={20} />
            选择文件夹
          </Button>
        </div>
        
        <p className="text-th-text-muted text-sm">
          支持格式：Word (.doc, .docx)、PDF、Excel (.xls, .xlsx)、PPT (.ppt, .pptx)、TXT、Markdown
        </p>
      </div>

      {/* 已选文件列表 */}
      {localFiles.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-4 p-3 bg-hover rounded-btn">
            <div className="flex items-center gap-4">
              <span className="font-medium">已选择 {localFiles.length} 个文件</span>
              <span className="text-sm text-th-text-muted">
                共 {formatFileSize(localFiles.reduce((sum, f) => sum + f.size, 0))}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={clearAllLocalFiles}>
                清空全部
              </Button>
              <Button onClick={handleStartDenoise}>
                下一步：智能去噪 →
              </Button>
            </div>
          </div>

          <div className="space-y-2 max-h-[400px] overflow-y-auto">
            {localFiles.map(file => {
              const ext = file.type;
              const color = FILE_TYPE_COLORS[ext] || '#666';
              
              return (
                <div
                  key={file.id}
                  className="flex items-center gap-3 p-3 bg-hover rounded-btn group"
                >
                  <div 
                    className="w-10 h-10 rounded-btn flex items-center justify-center text-white text-xs font-bold flex-shrink-0"
                    style={{ backgroundColor: color }}
                  >
                    {ext.toUpperCase()}
                  </div>
                  
                  <div className="flex-1 min-w-0">
                    <div className="font-medium truncate">{file.name}</div>
                    <div className="text-xs text-th-text-muted">
                      {file.path !== file.name && <span className="mr-2">{file.path}</span>}
                      {formatFileSize(file.size)}
                    </div>
                  </div>
                  
                  <button
                    onClick={() => removeLocalFile(file.id)}
                    className="opacity-0 group-hover:opacity-100 p-1 hover:bg-hover rounded transition-all"
                  >
                    <X size={16} className="text-th-error" />
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 空状态 */}
      {localFiles.length === 0 && (
        <div className="text-center py-8 text-th-text-muted">
          <File size={48} className="mx-auto mb-4 opacity-30" />
          <p>点击上方按钮选择文件或文件夹</p>
        </div>
      )}

      <div className="mt-6 pt-4" style={{ boxShadow: 'inset 0 1px 0 var(--color-border)' }}>
        <button
          className="text-sm text-th-text-muted hover:text-th-text-primary"
          onClick={() => {
            setCurrentStage(1);
            setSelectedPlatform(null);
            setLocalFiles([]);
          }}
        >
          ← 返回选择平台
        </button>
      </div>
    </div>
  );

  // 渲染文档选择（根据平台）
  const renderDocumentSelect = () => {
    if (selectedPlatform === 'local') {
      return renderLocalUpload();
    }
    return renderCloudDocumentSelect();
  };

  // ── 去噪分析相关状态 ──
  const [denoiseItems, setDenoiseItems] = useState<any[]>([]); // 去噪分析结果列表
  const [denoiseLoading, setDenoiseLoading] = useState(false); // 去噪分析加载中
  const [denoiseAnalyzed, setDenoiseAnalyzed] = useState(false); // 是否已完成分析
  const [_currentProjectId, setCurrentProjectId] = useState<string>(''); // 当前项目ID
  const [processingProgress, setProcessingProgress] = useState(0); // 分析进度百分比（0~100）
  const [ingestResponse, setIngestResponse] = useState<any>(null); // 真实入库 API 响应
  const [batchId, setBatchId] = useState<string>(''); // V14: analyze 返回的批次ID

  // 执行去噪分析 — V11.2: 直接调用真实 ingest API，不再使用 mock
  const runDenoiseAnalysis = async () => {
    setDenoiseLoading(true);
    setProcessingProgress(0);

    try {
      const pid = currentProject?.id || 'default';

      if (selectedPlatform === 'local' && localFiles.length > 0) {
        // ── 本地文件：V14 调用 /analyze（分析不入库）──
        setProcessingProgress(10);
        const formData = new FormData();
        formData.append('project_id', pid);
        for (const f of localFiles) {
          formData.append('files', f.file);
        }

        setProcessingProgress(30);
        const response = await fetch('/api/v1/knowledge/analyze', {
          method: 'POST',
          body: formData,
        });

        setProcessingProgress(80);

        if (!response.ok) {
          const errText = await response.text();
          throw new Error(`分析失败: ${errText}`);
        }

        const data = await response.json();
        setIngestResponse(data);
        setBatchId(data.batch_id || '');
        setProcessingProgress(100);

        // 用 /analyze 返回的 documents 数组构建去噪结果（此时尚未入库）
        const realItems = (data.documents || []).map((doc: any) => ({
          doc_id: doc.doc_id,
          doc_name: doc.title || doc.doc_id,
          doc_type: doc.doc_type || '未知',
          match_score: Math.round((doc.confidence || 0.7) * 100),
          match_reason: doc.summary || 'AI 分析完成',
          suggested_decision: doc.decision === 'KEEP' ? 'keep' : 'delete',
          user_decision: doc.decision === 'KEEP' ? 'keep' : 'delete',
          domain_id: doc.domain_id || '',
          entity_count: doc.entity_count || 0,
          needs_review: doc.needs_review || false,
        }));

        setDenoiseItems(realItems);
        setDenoiseAnalyzed(true);

      } else {
        // ── 云平台：调用 ingest-demo ──
        setProcessingProgress(20);
        const response = await fetch(
          `/api/v1/knowledge/ingest-demo?force=false&project_id=${encodeURIComponent(pid)}`,
          { method: 'POST' },
        );
        setProcessingProgress(80);

        if (response.ok) {
          const data = await response.json();
          setIngestResponse(data);
          setProcessingProgress(100);

          // ingest-demo 也返回 documents 数组
          const realItems = (data.documents || []).map((doc: any) => ({
            doc_id: doc.doc_id,
            doc_name: doc.title || doc.doc_id,
            doc_type: doc.doc_type || '文档',
            match_score: Math.round((doc.confidence || 0.7) * 100),
            match_reason: doc.summary || '已处理',
            suggested_decision: doc.decision === 'KEEP' ? 'keep' : 'delete',
            user_decision: doc.decision === 'KEEP' ? 'keep' : 'delete',
            domain_id: doc.domain_id || '',
            entity_count: doc.entity_count || 0,
          }));
          setDenoiseItems(realItems);
        } else {
          // 云平台API失败时的最小回退
          const allLeaves = getAllLeafDocs(cloudDocs);
          const selected = allLeaves.filter(d => selectedCloudDocs.has(d.id));
          setDenoiseItems(selected.map(doc => ({
            doc_id: doc.id, doc_name: doc.name, doc_type: '文档',
            match_score: 70, match_reason: 'API调用失败，显示默认',
            suggested_decision: 'keep', user_decision: null,
          })));
        }
        setDenoiseAnalyzed(true);
      }
    } catch (error) {
      console.error('蒸馏分析失败:', error);
      alert('分析失败: ' + (error as Error).message);
      // 回退：显示文件列表（未分析状态）
      const items = localFiles.map(f => ({
        doc_id: f.id, doc_name: f.name,
        match_score: 0, match_reason: '分析失败: ' + (error as Error).message,
        suggested_decision: 'keep', user_decision: null
      }));
      setDenoiseItems(items);
      setDenoiseAnalyzed(true);
    } finally {
      setDenoiseLoading(false);
    }
  };
  
  // 设置单个文档决策
  const setItemDecision = (docId: string, decision: 'keep' | 'delete') => {
    setDenoiseItems(prev => prev.map(item =>
      item.doc_id === docId ? { ...item, user_decision: decision } : item
    ));
  };
  
  // 批量设置决策
  const setBatchDecision = (decision: 'keep' | 'delete', filter?: 'pending' | 'all') => {
    setDenoiseItems(prev => prev.map(item => {
      if (filter === 'pending' && item.user_decision !== null) return item;
      return { ...item, user_decision: decision };
    }));
  };
  
  // 采纳所有建议
  const acceptAllSuggestions = () => {
    setDenoiseItems(prev => prev.map(item => ({
      ...item,
      user_decision: item.user_decision || item.suggested_decision
    })));
  };

  // 渲染智能去噪
  const renderDenoise = () => {
    // 如果还没分析，显示分析按钮
    if (!denoiseAnalyzed && !denoiseLoading) {
      const itemCount = selectedPlatform === 'local' 
        ? localFiles.length 
        : selectedCloudDocs.size;
      
      return (
        <div className="text-center py-12">
          <div className="w-20 h-20 rounded-full bg-[rgba(192,132,252,0.10)] flex items-center justify-center mx-auto mb-6">
            <RefreshCw size={32} className="text-[#c084fc]" />
          </div>
          <h3 className="text-lg font-semibold mb-2">智能去噪分析</h3>
          <p className="text-th-text-muted mb-6">
            AI将分析 {itemCount} 个文档，识别内容类型并判断相关性
          </p>
          <Button onClick={runDenoiseAnalysis} size="lg">
            开始分析
          </Button>
          <div className="mt-4">
            <button
              className="text-sm text-th-text-muted hover:text-th-text-primary"
              onClick={() => setCurrentStage(selectedPlatform === 'local' ? 2 : 3)}
            >
              ← 返回修改
            </button>
          </div>
        </div>
      );
    }
    
    // 分析中
    if (denoiseLoading && !denoiseAnalyzed) {
      return (
        <div className="text-center py-12">
          <Loader2 size={40} className="animate-spin mx-auto mb-4 text-[#c084fc]" />
          <h3 className="text-lg font-semibold mb-2">正在分析...</h3>
          <p className="text-th-text-muted mb-4">
            {processingProgress < 30 ? '创建项目...' :
             processingProgress < 50 ? '上传文档...' :
             processingProgress < 80 ? 'AI正在打标和分析...' :
             '生成去噪建议...'}
          </p>
          <div className="w-64 h-2 bg-hover rounded-full mx-auto overflow-hidden">
            <div 
              className="h-full bg-accent rounded-full transition-all duration-300"
              style={{ width: `${processingProgress}%` }}
            />
          </div>
          <p className="text-sm text-th-text-muted mt-2">{processingProgress}%</p>
        </div>
      );
    }
    
    // 统计
    const stats = {
      total: denoiseItems.length,
      toKeep: denoiseItems.filter(i => (i.user_decision || i.suggested_decision) === 'keep').length,
      toDelete: denoiseItems.filter(i => (i.user_decision || i.suggested_decision) === 'delete').length,
      reviewed: denoiseItems.filter(i => i.user_decision !== null).length,
    };

    return (
      <div>
        <div className="mb-6">
          <h3 className="text-lg font-semibold mb-2">智能去噪分析</h3>
          <p className="text-th-text-muted">
            AI已分析完成，请审核并决定哪些文档入库
          </p>
        </div>
        
        {/* 统计卡片 */}
        <div className="grid grid-cols-4 gap-3 mb-4">
          <div className="bg-hover rounded-btn p-3 text-center">
            <div className="text-metric">{stats.total}</div>
            <div className="text-xs text-th-text-muted">总数</div>
          </div>
          <div className="stat-card stat-card--success">
            <div className="text-metric text-th-success">{stats.toKeep}</div>
            <div className="text-xs text-th-success">入库</div>
          </div>
          <div className="stat-card stat-card--error">
            <div className="text-metric text-th-error">{stats.toDelete}</div>
            <div className="text-xs text-th-error">删除</div>
          </div>
          <div className="stat-card stat-card--info">
            <div className="text-metric text-accent">{stats.reviewed}</div>
            <div className="text-xs text-accent">已审核</div>
          </div>
        </div>
        
        {/* 批量操作栏 */}
        <div className="flex items-center justify-between p-3 bg-hover rounded-btn mb-4">
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={acceptAllSuggestions}>
              <CheckCircle size={14} className="mr-1" />
              采纳建议
            </Button>
            <Button variant="secondary" size="sm" onClick={() => setBatchDecision('keep', 'all')}>
              ✓ 全部入库
            </Button>
            <Button variant="secondary" size="sm" onClick={() => setBatchDecision('delete', 'all')}>
              ✗ 全部删除
            </Button>
          </div>
          <Button variant="ghost" size="sm" onClick={runDenoiseAnalysis}>
            <RefreshCw size={14} className="mr-1" />
            重新分析
          </Button>
        </div>

        {/* 文档列表 */}
        <div className="space-y-2 max-h-[350px] overflow-y-auto">
          {denoiseItems.map((item) => {
            const decision = item.user_decision || item.suggested_decision;
            const isKeep = decision === 'keep';
            const isReviewed = item.user_decision !== null;
            const score = item.match_score || 0;
            
            return (
              <Card
                key={item.doc_id}
                className={`p-3 transition-all ${
                  isReviewed && !isKeep ? 'opacity-50' : ''
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  {/* 左侧：状态指示器 + 文档信息 */}
                  {isReviewed && (
                    <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: isKeep ? 'var(--color-success)' : 'var(--color-error)' }} />
                  )}
                  <div className="flex items-center gap-3 flex-1 min-w-0">
                    <FileText size={16} className="flex-shrink-0 text-th-text-muted" />
                    <div className="min-w-0 flex-1">
                      <div className="font-medium truncate">{item.doc_name}</div>
                      <div className="text-xs text-th-text-muted truncate">
                        {item.doc_type && <span className="mr-2">{item.doc_type}</span>}
                        {item.match_reason}
                      </div>
                    </div>
                  </div>
                  
                  {/* 中间：分数 */}
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <div className="w-20 h-2 bg-hover rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${
                          score >= 70 ? 'bg-[var(--color-success)]' : score >= 40 ? 'bg-[var(--color-warning)]' : 'bg-[var(--color-error)]'
                        }`}
                        style={{ width: `${Math.min(score, 100)}%` }}
                      />
                    </div>
                    <span className={`text-sm font-medium w-10 ${
                      score >= 70 ? 'text-th-success' : score >= 40 ? 'text-[var(--color-warning)]' : 'text-th-error'
                    }`}>
                      {score}分
                    </span>
                  </div>
                  
                  {/* 右侧：操作按钮 */}
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button
                      onClick={() => setItemDecision(item.doc_id, 'keep')}
                      className={`p-2 rounded-btn transition-all ${
                        decision === 'keep'
                          ? 'btn-keep active text-white'
                          : 'bg-hover text-th-text-muted hover:text-th-success'
                      }`}
                      title="入库"
                    >
                      <CheckCircle size={18} />
                    </button>
                    <button
                      onClick={() => setItemDecision(item.doc_id, 'delete')}
                      className={`p-2 rounded-btn transition-all ${
                        decision === 'delete'
                          ? 'btn-discard active'
                          : 'bg-hover text-th-text-muted hover:text-th-error'
                      }`}
                      title="删除"
                    >
                      <X size={18} />
                    </button>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>

        {/* 底部操作 */}
        <div className="flex justify-between items-center mt-6 pt-4" style={{ boxShadow: 'inset 0 1px 0 var(--color-border)' }}>
          <button
            className="text-sm text-th-text-muted hover:text-th-text-primary"
            onClick={() => {
              setCurrentStage(selectedPlatform === 'local' ? 2 : 3);
              setDenoiseAnalyzed(false);
              setDenoiseItems([]);
              setCurrentProjectId('');
            }}
          >
            ← 返回修改
          </button>
          <Button 
            onClick={applyAndImport}
            disabled={stats.toKeep === 0 || denoiseLoading}
            className="btn-keep"
          >
            {denoiseLoading ? '入库中...' : `确认入库 (${stats.toKeep}份) →`}
          </Button>
        </div>
      </div>
    );
  };

  // V14: 按用户审核决策调用 /finalize 真正入库
  const applyAndImport = async () => {
    setDenoiseLoading(true);
    try {
      if (batchId) {
        // V14 新流程：调用 /finalize 按用户决策入库
        const decisions = denoiseItems.map(item => ({
          doc_id: item.doc_id,
          decision: (item.user_decision || item.suggested_decision) === 'keep' ? 'KEEP' : 'ARCHIVE',
        }));
        const resp = await fetch(`/api/v1/knowledge/finalize?batch_id=${encodeURIComponent(batchId)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(decisions),
        });
        if (resp.ok) {
          const data = await resp.json();
          setIngestResponse({ ...ingestResponse, ...data });
        }
      } else {
        // 旧流程回退（云平台 ingest-demo 路径）：对delete项调归档
        const deleteItems = denoiseItems.filter(i => i.user_decision === 'delete');
        if (deleteItems.length > 0) {
          await Promise.all(deleteItems.map(item =>
            fetch(`/api/v1/knowledge/review-queue/${encodeURIComponent(item.doc_id)}/resolve?final_decision=ARCHIVE&reviewer=user`, {
              method: 'POST',
            })
          ));
        }
      }
    } catch (e) {
      console.warn('入库失败:', e);
    } finally {
      setDenoiseLoading(false);
    }
    handleConfirmImport();
  };
  
  // 渲染确认入库 — V11.2: 显示真实蒸馏结果 + 多路径导航
  const renderConfirm = () => {
    const keptCount = denoiseItems.filter(i => (i.user_decision || i.suggested_decision) === 'keep').length;
    const resp = ingestResponse;
    const pid = currentProject?.id || 'default';
    const basePath = `/projects/${pid}`;

    return (
      <div className="max-w-2xl mx-auto">
        <div className="text-center mb-6">
          <div className="w-16 h-16 rounded-full bg-[rgba(95,201,146,0.10)] flex items-center justify-center mx-auto mb-4">
            <CheckCircle size={36} className="text-th-success" />
          </div>
          <h3 className="text-2xl font-semibold mb-2">入库完成</h3>
          <p className="text-th-text-muted">
            {resp
              ? `${resp.distillation?.kept || keptCount} 篇文档已入库, ${resp.storage?.vector_chunks || 0} 向量分块, ${resp.storage?.wiki_pages || 0} Wiki页编译`
              : `已成功导入 ${keptCount} 个文档到知识库`
            }
          </p>
        </div>

        {/* 处理结果统计 */}
        {resp && (
          <div className="grid grid-cols-4 gap-3 mb-6">
            <div className="glass-card rounded-btn p-3 text-center">
              <div className="text-xl font-semibold">{resp.parsed || 0}</div>
              <div className="text-xs text-th-text-muted">解析文档</div>
            </div>
            <div className="glass-card rounded-btn p-3 text-center">
              <div className="text-xl font-semibold text-th-success">{resp.distillation?.kept || 0}</div>
              <div className="text-xs text-th-text-muted">入库</div>
            </div>
            <div className="glass-card rounded-btn p-3 text-center">
              <div className="text-xl font-semibold">{resp.storage?.vector_chunks || 0}</div>
              <div className="text-xs text-th-text-muted">向量分块</div>
            </div>
            <div className="glass-card rounded-btn p-3 text-center">
              <div className="text-xl font-semibold text-accent">{resp.storage?.wiki_pages || 0}</div>
              <div className="text-xs text-th-text-muted">Wiki 页</div>
            </div>
          </div>
        )}

        {/* 文档处理明细 */}
        {denoiseItems.length > 0 && (
          <div className="glass-card rounded-card p-4 mb-6 max-h-[200px] overflow-y-auto">
            <div className="text-label mb-2">处理明细</div>
            <div className="space-y-1.5">
              {denoiseItems.map((item) => (
                <div key={item.doc_id} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                      item.suggested_decision === 'keep' ? 'bg-[var(--color-success)]' : 'bg-th-text-muted'
                    }`} />
                    <span className="truncate">{item.doc_name}</span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {item.domain_id && (
                      <Badge variant="info" size="sm">{item.domain_id}</Badge>
                    )}
                    {item.entity_count > 0 && (
                      <span className="text-[10px] text-th-text-muted">{item.entity_count} 实体</span>
                    )}
                    <Badge variant={item.suggested_decision === 'keep' ? 'success' : 'neutral'} size="sm">
                      {item.suggested_decision === 'keep' ? 'KEEP' : 'ARCHIVE'}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 多路径导航 — 让用户知道去哪里看结果 */}
        <div className="grid grid-cols-2 gap-3 mb-4">
          <button
            onClick={() => window.location.href = `${basePath}/wiki`}
            className="glass-card rounded-card p-4 text-left hover:border-accent/30 transition-all group"
          >
            <div className="text-sm font-medium group-hover:text-accent">知识 Wiki</div>
            <div className="text-xs text-th-text-muted mt-1">查看编译好的知识卡片和域概览</div>
          </button>
          <button
            onClick={() => window.location.href = `${basePath}/graph`}
            className="glass-card rounded-card p-4 text-left hover:border-accent/30 transition-all group"
          >
            <div className="text-sm font-medium group-hover:text-accent">知识图谱</div>
            <div className="text-xs text-th-text-muted mt-1">查看实体关系和文档关联</div>
          </button>
          <button
            onClick={() => window.location.href = `${basePath}/catalog`}
            className="glass-card rounded-card p-4 text-left hover:border-accent/30 transition-all group"
          >
            <div className="text-sm font-medium group-hover:text-accent">知识目录</div>
            <div className="text-xs text-th-text-muted mt-1">浏览已入库的文档分类</div>
          </button>
          <button
            onClick={() => window.location.href = `${basePath}/qa`}
            className="glass-card rounded-card p-4 text-left hover:border-accent/30 transition-all group"
          >
            <div className="text-sm font-medium group-hover:text-accent">智能问答</div>
            <div className="text-xs text-th-text-muted mt-1">基于已入库知识进行问答</div>
          </button>
        </div>

        <div className="flex gap-3 justify-center">
          <Button variant="secondary" onClick={resetAll}>
            继续导入
          </Button>
        </div>
      </div>
    );
  };

  // 根据当前阶段渲染内容
  const renderStageContent = () => {
    if (currentStage === 1) {
      return renderPlatformSelect();
    }
    
    // 云平台：阶段2是授权，阶段3是选择文档
    if (selectedPlatform !== 'local') {
      if (currentStage === 2) {
        return renderCloudAuthorize();
      }
      if (currentStage === 3) {
        return renderDocumentSelect();
      }
      if (currentStage === 4) {
        return renderDenoise();
      }
      if (currentStage === 5) {
        return renderConfirm();
      }
    }
    
    // 本地上传：阶段2是选择文件
    if (selectedPlatform === 'local') {
      if (currentStage === 2) {
        return renderDocumentSelect();
      }
      if (currentStage === 3) {
        return renderDenoise();
      }
      if (currentStage === 4) {
        return renderConfirm();
      }
    }
    
    return null;
  };

  return (
    <div className="p-6 page-enter">
      <div className="mb-6">
        <h1 className="text-metric mb-2">知识上传</h1>
        <p className="text-th-text-muted">
          从本地文件或云平台（飞书/钉钉）导入企业知识文档
        </p>
      </div>

      {renderProgress()}

      <Card className="p-6">
        {renderStageContent()}
      </Card>
    </div>
  );
};

export default UploadPage;
