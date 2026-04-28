/**
 * @module App
 * @description 应用根组件 — ErrorBoundary + RouterProvider。
 */
import { RouterProvider } from 'react-router-dom';
import { router } from './router';
import { ErrorBoundary } from './components/ErrorBoundary';

export default function App() {
  return (
    <ErrorBoundary>
      <RouterProvider router={router} />
    </ErrorBoundary>
  );
}
