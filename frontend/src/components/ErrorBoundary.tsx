import { Component, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="flex flex-col items-center justify-center h-screen bg-base text-th-text-primary gap-4">
          <div className="text-display font-semibold">页面出错了</div>
          <div className="text-sm text-th-text-muted max-w-md text-center">
            {this.state.error?.message || '未知错误'}
          </div>
          <button
            className="btn-gradient px-5 py-2 rounded-btn text-sm mt-2"
            onClick={() => {
              this.setState({ hasError: false, error: null });
              window.location.href = '/';
            }}
          >
            返回首页
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
