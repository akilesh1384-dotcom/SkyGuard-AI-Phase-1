import { useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import AwsDashboard from './components/aws-dashboard';
import AiAnalysisPanel from './components/ai-analysis-panel';
import MissingDataBanner from './components/missing-data-banner';
import SensorModeControl from './components/sensor-mode-control';
import DataSourceIndicator from './components/data-source-indicator';
import { ErrorBoundary } from '@/components/error-boundary';
import './index.css';

const sensorMode = window.localStorage.getItem('skyguard-sensor-mode') === 'AWS' ? 'AWS' : 'FULL';

function FrontendCopy() {
  useEffect(() => {
    const replaceStationCopy = () => {
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      const nodes: Text[] = [];
      let node: Node | null;
      while ((node = walker.nextNode())) nodes.push(node as Text);
      for (const textNode of nodes) {
        if (textNode.nodeValue?.includes('Automatic weather station · IIT field lab, New Delhi')) {
          textNode.nodeValue = textNode.nodeValue.replace(
            'Automatic weather station · IIT field lab, New Delhi',
            'Automatic weather station · SkyGuard AI prototype',
          );
        }
      }
    };

    replaceStationCopy();
    const observer = new MutationObserver(replaceStationCopy);
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    return () => observer.disconnect();
  }, []);

  return null;
}

createRoot(document.getElementById('root')!, {
  onCaughtError: (error, errorInfo) => console.error(error, errorInfo.componentStack),
}).render(
  <ErrorBoundary>
    {sensorMode === 'AWS' ? <AwsDashboard /> : <App />}
    <AiAnalysisPanel />
    <MissingDataBanner />
    <DataSourceIndicator />
    <SensorModeControl />
    <FrontendCopy />
  </ErrorBoundary>,
);
