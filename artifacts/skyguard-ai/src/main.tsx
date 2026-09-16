import { createRoot } from 'react-dom/client';

import App from './App';
import AiAnalysisPanel from './components/ai-analysis-panel';
import { ErrorBoundary } from '@/components/error-boundary';

import './index.css';

createRoot(document.getElementById('root')!, {
  // Keeps caught errors off reportError(), which would raise the dev overlay.
  onCaughtError: (error, errorInfo) => {
    console.error(error, errorInfo.componentStack);
  },
}).render(
  <ErrorBoundary>
    <App />
    <AiAnalysisPanel />
  </ErrorBoundary>,
);
