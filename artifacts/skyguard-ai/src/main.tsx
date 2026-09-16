import { createRoot } from 'react-dom/client';
import App from './App';
import AwsDashboard from './components/aws-dashboard';
import AiAnalysisPanel from './components/ai-analysis-panel';
import MissingDataBanner from './components/missing-data-banner';
import SensorModeControl from './components/sensor-mode-control';
import { ErrorBoundary } from '@/components/error-boundary';
import './index.css';

const sensorMode = window.localStorage.getItem('skyguard-sensor-mode') === 'AWS' ? 'AWS' : 'FULL';

createRoot(document.getElementById('root')!, {
  onCaughtError: (error, errorInfo) => console.error(error, errorInfo.componentStack),
}).render(
  <ErrorBoundary>
    {sensorMode === 'AWS' ? <AwsDashboard /> : <App />}
    <AiAnalysisPanel />
    <MissingDataBanner />
    <SensorModeControl />
  </ErrorBoundary>,
);
