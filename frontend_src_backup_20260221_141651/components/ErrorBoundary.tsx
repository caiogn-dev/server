import React, { Component, ErrorInfo, ReactNode } from 'react';
import { Button } from './atoms/Button';
import { Card, CardContent, CardHeader, CardTitle } from './molecules/Card';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, errorInfo: null };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error:', error, errorInfo);
    this.setState({ error, errorInfo });
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    window.location.reload();
  };

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="min-h-screen flex items-center justify-center p-4 bg-zinc-50 dark:bg-black">
          <Card className="max-w-lg w-full">
            <CardHeader>
              <CardTitle className="text-red-600 dark:text-red-400">
                Algo deu errado
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-zinc-600 dark:text-zinc-400">
                Ocorreu um erro inesperado. Tente recarregar a página.
              </p>
              
              {this.state.error && (
                <div className="bg-red-50 dark:bg-red-900/20 p-4 rounded-lg overflow-auto">
                  <p className="text-sm font-mono text-red-800 dark:text-red-200">
                    {this.state.error.toString()}
                  </p>
                </div>
              )}

              <div className="flex gap-3">
                <Button onClick={this.handleReset} variant="primary">
                  Recarregar página
                </Button>
                <Button 
                  onClick={() => window.location.href = '/'} 
                  variant="secondary"
                >
                  Voltar ao início
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      );
    }

    return this.props.children;
  }
}
