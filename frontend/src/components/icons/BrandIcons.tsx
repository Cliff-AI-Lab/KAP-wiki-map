/**
 * 品牌与行业图标组件
 *
 * 使用简洁的 SVG 矢量图形式，包含：
 * - 平台品牌图标：飞书、钉钉、企业微信
 * - 行业图标：能源电力、制造业、养殖业、化工、医药、食品饮料、通用企业
 * - IndustryIcons 映射表 + getIndustryIcon() 工具函数
 *
 * 所有图标统一接收 size 和 className 属性，默认 24px。
 */

import React from 'react';

/** 图标通用属性 */
interface IconProps {
  size?: number;
  className?: string;
}

// 飞书图标 (官方风格 - 折纸鸟)
export const FeishuIcon: React.FC<IconProps> = ({ size = 24, className }) => (
  <svg 
    width={size} 
    height={size} 
    viewBox="0 0 24 24" 
    fill="currentColor"
    className={className}
  >
    <path d="M3.5 11.5L12 3l8.5 8.5L12 20 3.5 11.5z" fill="none" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M12 3v17M3.5 11.5L12 13l8.5-1.5" fill="none" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M8 7l4 6 4-6" fill="none" stroke="currentColor" strokeWidth="1.5"/>
  </svg>
);

// 钉钉图标 (官方风格 - 闪电/钉子)
export const DingTalkIcon: React.FC<IconProps> = ({ size = 24, className }) => (
  <svg 
    width={size} 
    height={size} 
    viewBox="0 0 24 24" 
    fill="currentColor"
    className={className}
  >
    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z" fill="none" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M15.5 7h-4l-1 4h2.5l-2 6 5-7h-3l2-3z" fill="currentColor"/>
  </svg>
);

// 企业微信图标 (官方风格)
export const WeChatWorkIcon: React.FC<IconProps> = ({ size = 24, className }) => (
  <svg 
    width={size} 
    height={size} 
    viewBox="0 0 24 24" 
    fill="currentColor"
    className={className}
  >
    <path d="M15.5 6.5C15.5 4.01 12.54 2 9 2S2.5 4.01 2.5 6.5c0 1.33.71 2.53 1.85 3.4l-.6 2.1 2.5-1.25c.85.25 1.75.38 2.75.38 3.54 0 6.5-2.01 6.5-4.63z" fill="none" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M21.5 12c0-2.21-2.24-4-5-4-.5 0-1 .05-1.45.15.3.7.45 1.45.45 2.22 0 3.17-3.33 5.75-7.5 5.75-.17 0-.33 0-.5-.02C8.5 18.3 10.9 20 14 20c.83 0 1.62-.1 2.35-.3l2.15 1.08-.52-1.8c1-. 77 1.52-1.77 1.52-2.98z" fill="none" stroke="currentColor" strokeWidth="1.5"/>
    <circle cx="6.5" cy="6.5" r="0.75" fill="currentColor"/>
    <circle cx="9" cy="6.5" r="0.75" fill="currentColor"/>
    <circle cx="11.5" cy="6.5" r="0.75" fill="currentColor"/>
  </svg>
);

// 行业图标 - 能源电力
export const EnergyIcon: React.FC<IconProps> = ({ size = 24, className }) => (
  <svg 
    width={size} 
    height={size} 
    viewBox="0 0 24 24" 
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
  </svg>
);

// 行业图标 - 制造业
export const ManufacturingIcon: React.FC<IconProps> = ({ size = 24, className }) => (
  <svg 
    width={size} 
    height={size} 
    viewBox="0 0 24 24" 
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M2 20a2 2 0 002 2h16a2 2 0 002-2V8l-7 5V8l-7 5V4a2 2 0 00-2-2H4a2 2 0 00-2 2v16z"/>
  </svg>
);

// 行业图标 - 养殖业
export const LivestockIcon: React.FC<IconProps> = ({ size = 24, className }) => (
  <svg 
    width={size} 
    height={size} 
    viewBox="0 0 24 24" 
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M12 3c-1.5 0-2.5 1-3 2-1 0-2 1-2 2v2c0 1 1 2 2 2h1v4H8l-2 4h12l-2-4h-2v-4h1c1 0 2-1 2-2V7c0-1-1-2-2-2-.5-1-1.5-2-3-2z"/>
    <circle cx="9" cy="7" r="1"/>
    <circle cx="15" cy="7" r="1"/>
  </svg>
);

// 行业图标 - 化工
export const ChemicalIcon: React.FC<IconProps> = ({ size = 24, className }) => (
  <svg 
    width={size} 
    height={size} 
    viewBox="0 0 24 24" 
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M9 3h6v8l4 9H5l4-9V3z"/>
    <path d="M9 3h6"/>
  </svg>
);

// 行业图标 - 医药
export const PharmaceuticalIcon: React.FC<IconProps> = ({ size = 24, className }) => (
  <svg 
    width={size} 
    height={size} 
    viewBox="0 0 24 24" 
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M10.5 20.5L3.5 13.5a5 5 0 117-7l7 7a5 5 0 11-7 7z"/>
    <path d="M8.5 8.5l7 7"/>
  </svg>
);

// 行业图标 - 食品饮料
export const FoodBeverageIcon: React.FC<IconProps> = ({ size = 24, className }) => (
  <svg 
    width={size} 
    height={size} 
    viewBox="0 0 24 24" 
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M18 8h1a4 4 0 010 8h-1"/>
    <path d="M2 8h16v9a4 4 0 01-4 4H6a4 4 0 01-4-4V8z"/>
    <line x1="6" y1="1" x2="6" y2="4"/>
    <line x1="10" y1="1" x2="10" y2="4"/>
    <line x1="14" y1="1" x2="14" y2="4"/>
  </svg>
);

// 行业图标 - 通用/企业
export const EnterpriseIcon: React.FC<IconProps> = ({ size = 24, className }) => (
  <svg 
    width={size} 
    height={size} 
    viewBox="0 0 24 24" 
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
    <line x1="9" y1="3" x2="9" y2="21"/>
    <line x1="15" y1="3" x2="15" y2="21"/>
    <line x1="3" y1="9" x2="21" y2="9"/>
    <line x1="3" y1="15" x2="21" y2="15"/>
  </svg>
);

/** 行业名称到图标组件的映射表 */
export const IndustryIcons: Record<string, React.FC<IconProps>> = {
  '能源电力': EnergyIcon,
  '制造业': ManufacturingIcon,
  '养殖业': LivestockIcon,
  '化工': ChemicalIcon,
  '医药': PharmaceuticalIcon,
  '食品饮料': FoodBeverageIcon,
  '通用': EnterpriseIcon,
};

/**
 * 根据行业名称获取对应图标组件
 * @param industry - 行业名称（如 "能源电力"）
 * @returns 对应的图标组件，未匹配时返回通用企业图标
 */
export const getIndustryIcon = (industry: string): React.FC<IconProps> => {
  return IndustryIcons[industry] || EnterpriseIcon;
};

export default {
  FeishuIcon,
  DingTalkIcon,
  WeChatWorkIcon,
  EnergyIcon,
  ManufacturingIcon,
  LivestockIcon,
  ChemicalIcon,
  PharmaceuticalIcon,
  FoodBeverageIcon,
  EnterpriseIcon,
  IndustryIcons,
  getIndustryIcon,
};
