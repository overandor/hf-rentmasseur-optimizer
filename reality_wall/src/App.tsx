import { useState, useEffect } from 'react';
import type { WallState, View } from './types';
import { useWallState, useRemoteNavigation, useDisplayMode } from './hooks';
import { KPIPanel } from './components/KPIPanel';
import { ReceiptChain } from './components/ReceiptChain';
import { ProofCards } from './components/ProofCards';
import { ExperimentTracker } from './components/ExperimentTracker';
import { OperatorReport } from './components/OperatorReport';
import { ClientPulsePanel } from './components/ClientPulsePanel';
import { Header } from './components/Header';
import { ViewNav } from './components/ViewNav';
import { QRPairing } from './components/QRPairing';
import { DemoMode } from './components/DemoMode';
import { SpotlightOverlay } from './components/SpotlightOverlay';
import { CastView } from './components/CastView';

const VIEWS: View[] = ['overview', 'proof', 'receipts', 'kpi', 'experiments', 'cast'];
const ALL_VIEWS: View[] = [...VIEWS, 'pairing', 'demo'];

export function App() {
  const [serverUrl, setServerUrl] = useState(() => {
    const stored = localStorage.getItem('reality-wall-ws');
    if (stored) return stored;
    return `ws://${window.location.hostname}:7863/ws`;
  });
  const { state, refresh, spotlight, clearSpotlight, setPairingToken } = useWallState(serverUrl);
  const [currentView, setCurrentView] = useState<View>('overview');
  const { displayMode, switchMode } = useDisplayMode();

  const cardCount = getCardCount(currentView, state);
  const { focusedCard } = useRemoteNavigation(ALL_VIEWS, currentView, setCurrentView, cardCount, refresh);

  useEffect(() => {
    const interval = setInterval(refresh, 10000);
    return () => clearInterval(interval);
  }, [refresh]);

  if (currentView === 'pairing') {
    return (
      <QRPairing
        wsUrl={serverUrl}
        onPaired={() => setCurrentView('overview')}
        setPairingToken={setPairingToken}
      />
    );
  }

  if (currentView === 'demo') {
    return (
      <div className="app">
        <div className="scan-line" />
        <Header state={state} onPair={() => setCurrentView('pairing')} onDemo={() => setCurrentView('demo')} isDemo />
        <ViewNav views={VIEWS} current={currentView} onSelect={setCurrentView} />
        <main className="main-content">
          <DemoMode state={state} />
        </main>
      </div>
    );
  }

  return (
    <div className="app">
      <div className="scan-line" />
      <Header state={state} onPair={() => setCurrentView('pairing')} onDemo={() => setCurrentView('demo')} displayMode={displayMode} onSwitchMode={switchMode} />
      <ViewNav views={VIEWS} current={currentView} onSelect={setCurrentView} />
      <main className="main-content">
        {renderView(currentView, state, focusedCard)}
      </main>
      {spotlight && (
        <SpotlightOverlay
          spotlight={spotlight}
          state={state}
          onDismiss={clearSpotlight}
        />
      )}
    </div>
  );
}

function getCardCount(view: View, state: WallState): number {
  switch (view) {
    case 'overview': return 4;
    case 'proof': return state.lambdaReceipts.length || 1;
    case 'receipts': return state.receipts.length || 1;
    case 'kpi': return 4;
    case 'experiments': return state.experiments.length || 1;
    default: return 1;
  }
}

function renderView(view: View, state: WallState, focusedCard: number) {
  switch (view) {
    case 'overview':
      return (
        <div className="overview-grid">
          <KPIPanel kpis={state.kpis} compact />
          <OperatorReport report={state.operatorReport} />
          <ReceiptChain receipts={state.receipts.slice(0, 5)} compact />
          <ClientPulsePanel data={state.clientPulse} compact />
        </div>
      );
    case 'proof':
      return <ProofCards receipts={state.lambdaReceipts} focusedIndex={focusedCard} />;
    case 'receipts':
      return <ReceiptChain receipts={state.receipts} focusedIndex={focusedCard} />;
    case 'kpi':
      return <KPIPanel kpis={state.kpis} focusedIndex={focusedCard} />;
    case 'experiments':
      return <ExperimentTracker experiments={state.experiments} clientPulse={state.clientPulse} focusedIndex={focusedCard} />;
    case 'cast':
      return <CastView castUrl={`http://${window.location.hostname}:7864`} />;
    default:
      return null;
  }
}
