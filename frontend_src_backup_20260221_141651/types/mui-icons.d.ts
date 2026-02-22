declare module '@mui/icons-material/*' {
  import * as React from 'react';
  const Component: React.ComponentType<{
    className?: string;
    fontSize?: 'inherit' | 'small' | 'medium' | 'large';
    color?: string;
    sx?: Record<string, unknown>;
  }>;
  export default Component;
}
