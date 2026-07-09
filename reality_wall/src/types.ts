export interface WallState {
  kpis: KPIData | null;
  receipts: Receipt[];
  decisions: Decision[];
  experiments: Experiment[];
  lambdaReceipts: LambdaReceipt[];
  clientPulse: ClientPulseData | null;
  operatorReport: OperatorReport | null;
  connected: boolean;
  lastUpdate: number;
}

export interface KPIData {
  immortality: number;
  virality: number;
  conversion: number;
  proof: number;
  composite: number;
  [key: string]: any;
}

export interface Receipt {
  id: string | number;
  timestamp: string;
  action: string;
  agent: string;
  artifact_hash: string;
  verified: boolean;
  [key: string]: any;
}

export interface Decision {
  id: string | number;
  timestamp: string;
  state: string;
  evidence: string;
  [key: string]: any;
}

export interface Experiment {
  id: string;
  name: string;
  hypothesis: string;
  status: string;
  created_at: string;
  [key: string]: any;
}

export interface LambdaReceipt {
  id: string;
  intent: string;
  lambda_score: number;
  transferability: number;
  created_at: string;
  source_hash?: string;
  receipt_hash?: string;
  file_delta_count?: number;
  [key: string]: any;
}

export interface ClientPulseData {
  snapshots: any[];
  active_experiments: any[];
  recent_decisions: any[];
}

export interface OperatorReport {
  status: string;
  proof: string;
  risk: string;
  next_move: string;
  [key: string]: any;
}

export type View = 'overview' | 'proof' | 'receipts' | 'kpi' | 'experiments' | 'pairing' | 'demo' | 'cast';

export type DisplayMode = 'dashboard' | 'cast' | 'auto';

export interface DisplayModeState {
  mode: DisplayMode;
  screenSharingActive: boolean;
  remoteManagementActive: boolean;
  conflict: boolean;
  lastSwitch: number;
}
