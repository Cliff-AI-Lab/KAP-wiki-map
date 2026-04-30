/**
 * Vitest 全局 setup（M11 #2）。
 *
 * 引入 @testing-library/jest-dom 扩展 expect.toBeInTheDocument 等
 * happy-dom 不支持但 RTL 需要的 DOM 断言。
 */
import '@testing-library/jest-dom/vitest';
