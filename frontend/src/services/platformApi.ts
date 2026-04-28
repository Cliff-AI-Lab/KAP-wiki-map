/**
 * 平台 API 服务 - 飞书/钉钉文档对接
 *
 * 本模块封装了：
 * - 飞书 OAuth 授权 + 知识库/云盘文档获取与下载
 * - 钉钉 OAuth 授权 + 文档空间获取与下载
 * - 统一的 platformService 抽象层，屏蔽各平台差异
 *
 * 前端通过 platformService 对外暴露统一接口，
 * 实际请求经 /api/auth/* 和 /api/feishu/* 等反向代理到后端。
 */

// 声明Vite环境变量类型
declare global {
  interface ImportMeta {
    env: {
      VITE_FEISHU_APP_ID?: string;
      VITE_FEISHU_REDIRECT_URI?: string;
      VITE_DINGTALK_APP_KEY?: string;
      VITE_DINGTALK_REDIRECT_URI?: string;
      [key: string]: string | undefined;
    };
  }
}

/** 支持的平台类型 */
export type Platform = 'feishu' | 'dingtalk' | 'local';

/** 统一文档/文件夹节点（树状结构） */
export interface DocItem {
  id: string;
  name: string;
  /** 节点类型：文件夹 / 文档 / 表格 / 知识库 / 文件 */
  type: 'folder' | 'doc' | 'sheet' | 'wiki' | 'file';
  parentId?: string;
  /** 子节点列表（文件夹时） */
  children?: DocItem[];
  /** 文件大小（字节） */
  size?: number;
  updateTime?: string;
  url?: string;
  mimeType?: string;
}

/** OAuth 授权状态 */
export interface AuthState {
  /** 平台标识 */
  platform: Platform;
  /** 是否已授权 */
  isAuthorized: boolean;
  accessToken?: string;
  refreshToken?: string;
  /** Token 过期时间戳（毫秒） */
  expiresAt?: number;
  /** 授权用户信息 */
  userInfo?: {
    id: string;
    name: string;
    avatar?: string;
    email?: string;
  };
}

// ========== 飞书 API ==========

/** 飞书应用 ID，从环境变量注入 */
const FEISHU_APP_ID = import.meta.env.VITE_FEISHU_APP_ID || '';
/** 飞书 OAuth 回调地址 */
const FEISHU_REDIRECT_URI = import.meta.env.VITE_FEISHU_REDIRECT_URI || window.location.origin + '/auth/feishu/callback';

/** 飞书平台 API 集合 */
export const feishuApi = {
  /**
   * 获取OAuth授权URL
   */
  getAuthUrl(): string {
    const state = Math.random().toString(36).substring(7);
    sessionStorage.setItem('feishu_oauth_state', state);
    
    return `https://open.feishu.cn/open-apis/authen/v1/authorize?` +
      `app_id=${FEISHU_APP_ID}` +
      `&redirect_uri=${encodeURIComponent(FEISHU_REDIRECT_URI)}` +
      `&state=${state}` +
      `&scope=docs:doc:readonly wiki:wiki:readonly drive:drive:readonly`;
  },

  /**
   * 用授权码换取token
   */
  async exchangeToken(code: string): Promise<AuthState> {
    const response = await fetch('/api/auth/feishu/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
    });
    
    if (!response.ok) {
      throw new Error('飞书授权失败');
    }
    
    return response.json();
  },

  /**
   * 获取知识库空间列表
   */
  async getWikiSpaces(accessToken: string): Promise<DocItem[]> {
    const response = await fetch('/api/feishu/wiki/spaces', {
      headers: { 'Authorization': `Bearer ${accessToken}` },
    });
    
    if (!response.ok) {
      throw new Error('获取知识库失败');
    }
    
    const data = await response.json();
    return data.spaces.map((space: any) => ({
      id: space.space_id,
      name: space.name,
      type: 'folder' as const,
    }));
  },

  /**
   * 获取知识库节点（文档列表）
   */
  async getWikiNodes(accessToken: string, spaceId: string, parentNodeToken?: string): Promise<DocItem[]> {
    const url = parentNodeToken 
      ? `/api/feishu/wiki/spaces/${spaceId}/nodes?parent_node_token=${parentNodeToken}`
      : `/api/feishu/wiki/spaces/${spaceId}/nodes`;
      
    const response = await fetch(url, {
      headers: { 'Authorization': `Bearer ${accessToken}` },
    });
    
    if (!response.ok) {
      throw new Error('获取文档列表失败');
    }
    
    const data = await response.json();
    return data.items.map((node: any) => ({
      id: node.node_token,
      name: node.title,
      type: node.obj_type === 'docx' ? 'doc' : node.obj_type,
      updateTime: new Date(node.edit_time * 1000).toLocaleDateString(),
    }));
  },

  /**
   * 获取云文档列表
   */
  async getDriveFiles(accessToken: string, folderToken?: string): Promise<DocItem[]> {
    const url = folderToken 
      ? `/api/feishu/drive/files?folder_token=${folderToken}`
      : `/api/feishu/drive/files`;
      
    const response = await fetch(url, {
      headers: { 'Authorization': `Bearer ${accessToken}` },
    });
    
    if (!response.ok) {
      throw new Error('获取云盘文件失败');
    }
    
    const data = await response.json();
    return data.files.map((file: any) => ({
      id: file.token,
      name: file.name,
      type: file.type === 'folder' ? 'folder' : 
            file.type === 'docx' ? 'doc' : 
            file.type === 'sheet' ? 'sheet' : 'file',
      size: file.size,
      updateTime: new Date(file.modified_time * 1000).toLocaleDateString(),
      mimeType: file.mime_type,
    }));
  },

  /**
   * 下载文档内容
   */
  async downloadDocument(accessToken: string, docToken: string, docType: string): Promise<Blob> {
    const response = await fetch(`/api/feishu/docs/${docToken}/content?type=${docType}`, {
      headers: { 'Authorization': `Bearer ${accessToken}` },
    });
    
    if (!response.ok) {
      throw new Error('下载文档失败');
    }
    
    return response.blob();
  },
};

// ========== 钉钉 API ==========

/** 钉钉应用 Key，从环境变量注入 */
const DINGTALK_APP_KEY = import.meta.env.VITE_DINGTALK_APP_KEY || '';
/** 钉钉 OAuth 回调地址 */
const DINGTALK_REDIRECT_URI = import.meta.env.VITE_DINGTALK_REDIRECT_URI || window.location.origin + '/auth/dingtalk/callback';

/** 钉钉平台 API 集合 */
export const dingtalkApi = {
  /**
   * 获取OAuth授权URL（扫码登录）
   */
  getAuthUrl(): string {
    const state = Math.random().toString(36).substring(7);
    sessionStorage.setItem('dingtalk_oauth_state', state);
    
    return `https://login.dingtalk.com/oauth2/auth?` +
      `client_id=${DINGTALK_APP_KEY}` +
      `&redirect_uri=${encodeURIComponent(DINGTALK_REDIRECT_URI)}` +
      `&response_type=code` +
      `&scope=openid corpid` +
      `&state=${state}` +
      `&prompt=consent`;
  },

  /**
   * 用授权码换取token
   */
  async exchangeToken(code: string): Promise<AuthState> {
    const response = await fetch('/api/auth/dingtalk/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
    });
    
    if (!response.ok) {
      throw new Error('钉钉授权失败');
    }
    
    return response.json();
  },

  /**
   * 获取钉钉文档空间列表
   */
  async getSpaces(accessToken: string): Promise<DocItem[]> {
    const response = await fetch('/api/dingtalk/doc/spaces', {
      headers: { 'Authorization': `Bearer ${accessToken}` },
    });
    
    if (!response.ok) {
      throw new Error('获取文档空间失败');
    }
    
    const data = await response.json();
    return data.spaces.map((space: any) => ({
      id: space.space_id,
      name: space.name,
      type: 'folder' as const,
    }));
  },

  /**
   * 获取钉钉文档列表
   */
  async getDocuments(accessToken: string, spaceId: string, parentId?: string): Promise<DocItem[]> {
    const url = parentId 
      ? `/api/dingtalk/doc/spaces/${spaceId}/docs?parent_id=${parentId}`
      : `/api/dingtalk/doc/spaces/${spaceId}/docs`;
      
    const response = await fetch(url, {
      headers: { 'Authorization': `Bearer ${accessToken}` },
    });
    
    if (!response.ok) {
      throw new Error('获取文档列表失败');
    }
    
    const data = await response.json();
    return data.docs.map((doc: any) => ({
      id: doc.doc_id,
      name: doc.title,
      type: doc.doc_type === 'alidoc' ? 'doc' : doc.doc_type,
      updateTime: new Date(doc.updated_time).toLocaleDateString(),
    }));
  },

  /**
   * 下载文档内容
   */
  async downloadDocument(accessToken: string, docId: string): Promise<Blob> {
    const response = await fetch(`/api/dingtalk/doc/${docId}/content`, {
      headers: { 'Authorization': `Bearer ${accessToken}` },
    });
    
    if (!response.ok) {
      throw new Error('下载文档失败');
    }
    
    return response.blob();
  },
};

// ========== 统一平台服务 ==========

/** 统一平台服务：屏蔽飞书/钉钉差异，提供统一的授权、文档树、批量下载接口 */
export const platformService = {
  /**
   * 获取平台授权URL
   */
  getAuthUrl(platform: Platform): string {
    switch (platform) {
      case 'feishu':
        return feishuApi.getAuthUrl();
      case 'dingtalk':
        return dingtalkApi.getAuthUrl();
      default:
        throw new Error(`不支持的平台: ${platform}`);
    }
  },

  /**
   * 处理OAuth回调
   */
  async handleCallback(platform: Platform, code: string): Promise<AuthState> {
    switch (platform) {
      case 'feishu':
        return feishuApi.exchangeToken(code);
      case 'dingtalk':
        return dingtalkApi.exchangeToken(code);
      default:
        throw new Error(`不支持的平台: ${platform}`);
    }
  },

  /**
   * 获取文档树
   */
  async getDocumentTree(platform: Platform, accessToken: string): Promise<DocItem[]> {
    switch (platform) {
      case 'feishu':
        // 获取知识库空间
        const wikiSpaces = await feishuApi.getWikiSpaces(accessToken);
        // 获取云盘根目录
        const driveFiles = await feishuApi.getDriveFiles(accessToken);
        return [
          { id: 'wiki', name: '知识库', type: 'folder', children: wikiSpaces },
          { id: 'drive', name: '云盘', type: 'folder', children: driveFiles },
        ];
      case 'dingtalk':
        return dingtalkApi.getSpaces(accessToken);
      default:
        return [];
    }
  },

  /**
   * 批量下载文档
   */
  /**
   * 批量下载文档（逐个串行下载，通过回调报告进度）
   * @param platform - 平台类型
   * @param accessToken - 授权令牌
   * @param docIds - 待下载的文档 ID 列表
   * @param onProgress - 进度回调 (当前序号, 总数)
   * @returns 每个文档的下载结果（含内容 Blob 或错误信息）
   */
  async downloadDocuments(
    platform: Platform,
    accessToken: string,
    docIds: string[],
    onProgress?: (current: number, total: number) => void
  ): Promise<{ id: string; content: Blob; error?: string }[]> {
    const results: { id: string; content: Blob; error?: string }[] = [];
    
    for (const [i, docId] of docIds.entries()) {
      onProgress?.(i + 1, docIds.length);
      
      try {
        let content: Blob;
        switch (platform) {
          case 'feishu':
            content = await feishuApi.downloadDocument(accessToken, docId, 'docx');
            break;
          case 'dingtalk':
            content = await dingtalkApi.downloadDocument(accessToken, docId);
            break;
          default:
            throw new Error('不支持的平台');
        }
        results.push({ id: docId, content });
      } catch (error) {
        results.push({ 
          id: docId, 
          content: new Blob(), 
          error: error instanceof Error ? error.message : '下载失败' 
        });
      }
    }
    
    return results;
  },
};

export default platformService;
