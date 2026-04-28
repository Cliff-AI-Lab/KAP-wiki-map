/**
 * UI 组件库统一导出
 *
 * 本文件集中导出所有通用 UI 组件，页面模块通过
 * `import { Button, Card, ... } from '@/components/ui'` 引用。
 */

export { Button, IconButton } from './Button';
export type { ButtonProps, IconButtonProps } from './Button';

export { Card, CardHeader, CardTitle, CardContent, CardFooter } from './Card';
export type { CardProps } from './Card';

export { Input, Textarea, Select } from './Input';
export type { InputProps, TextareaProps, SelectProps } from './Input';

export { Badge, decisionVariant, statusVariant } from './Badge';
export type { BadgeProps } from './Badge';

export { Skeleton, SkeletonText, SkeletonCard } from './Skeleton';
export { Pagination } from './Pagination';
export { SearchInput } from './SearchInput';
export { TreeView } from './TreeView';
export type { TreeNode } from './TreeView';
export { EmptyState } from './EmptyState';
export { ThemeSwitcher } from './ThemeSwitcher';
export { PageHeader } from './PageHeader';
export { ToastProvider, useToast } from './Toast';

// V14: 新增 Linear 风格组件
export { Modal } from './Modal';
export type { ModalProps } from './Modal';
export { Tabs } from './Tabs';
export type { TabsProps, TabItem } from './Tabs';
export { Spinner } from './Spinner';
export type { SpinnerProps } from './Spinner';
export { Dropdown } from './Dropdown';
export type { DropdownProps, DropdownItem } from './Dropdown';
