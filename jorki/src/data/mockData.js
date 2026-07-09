export const mockStats = {
  storage: 12.7,
  storageUnit: 'TB',
  bandwidth: 41.2,
  transfers: 241,
  integrity: 100,
  latency: 18,
  throughput: 37.4,
  upload: 18.2,
  download: 19.2,
  cpu: 31,
  ram: 12,
  diskSpeed: 7.8,
  connections: 842,
  requestsPerSec: 9224,
  avgLatency: 14,
  sessions: 5,
  filesIndexed: 27,
  queriesHandled: 1842,
}

export const mockTransfers = [
  { id: 1, name: 'movie.mov', size: '12.4 GB', progress: 96, speed: 2.7, eta: '0.4s', status: 'live', hash: 'Verified' },
  { id: 2, name: 'dataset.tar.gz', size: '4.2 GB', progress: 72, speed: 1.8, eta: '1.2s', status: 'live', hash: 'Verifying' },
  { id: 3, name: 'model_weights.bin', size: '8.1 GB', progress: 45, speed: 3.2, eta: '2.5s', status: 'live', hash: 'Pending' },
  { id: 4, name: 'presentation.mp4', size: '2.3 GB', progress: 100, speed: 0, eta: 'Done', status: 'complete', hash: 'Verified' },
  { id: 5, name: 'archive_2026.zip', size: '15.7 GB', progress: 28, speed: 1.4, eta: '8.2s', status: 'live', hash: 'Pending' },
  { id: 6, name: 'research_data.csv', size: '890 MB', progress: 100, speed: 0, eta: 'Done', status: 'complete', hash: 'Verified' },
]

export const mockEvents = [
  { id: 1, time: '14:02:18', type: 'UPLOAD', file: 'movie.mov', detail: '12.4 GB', status: 'Integrity Verified', color: 'primary' },
  { id: 2, time: '14:02:19', type: 'DOWNLOAD', file: 'dataset.tar', detail: 'Completed', status: '', color: 'success' },
  { id: 3, time: '14:02:20', type: 'SHARE', file: 'report.pdf', detail: 'Link Created', status: '', color: 'accent' },
  { id: 4, time: '14:02:21', type: 'API', file: 'Range Request', detail: '16 MB', status: '', color: 'secondary' },
  { id: 5, time: '14:02:22', type: 'UPLOAD', file: 'images.zip', detail: '340 MB', status: 'Integrity Verified', color: 'primary' },
  { id: 6, time: '14:02:23', type: 'STREAM', file: 'keynote.mp4', detail: 'Started', status: '', color: 'accent' },
  { id: 7, time: '14:02:24', type: 'DELETE', file: 'temp_cache/', detail: 'Cleaned', status: '', color: 'critical' },
  { id: 8, time: '14:02:25', type: 'REPLICATE', file: 'model.bin', detail: 'Edge: 3 nodes', status: '', color: 'success' },
]

export const mockNodes = [
  { name: 'New York', x: 25, y: 38, latency: 12 },
  { name: 'London', x: 47, y: 30, latency: 18 },
  { name: 'Berlin', x: 52, y: 33, latency: 22 },
  { name: 'Dubai', x: 62, y: 48, latency: 31 },
  { name: 'Singapore', x: 76, y: 58, latency: 44 },
  { name: 'Tokyo', x: 84, y: 38, latency: 38 },
  { name: 'San Francisco', x: 15, y: 42, latency: 15 },
  { name: 'São Paulo', x: 32, y: 68, latency: 52 },
]

export const mockConnections = [
  { from: 'New York', to: 'London' },
  { from: 'London', to: 'Berlin' },
  { from: 'New York', to: 'San Francisco' },
  { from: 'Dubai', to: 'Singapore' },
  { from: 'Singapore', to: 'Tokyo' },
  { from: 'New York', to: 'São Paulo' },
  { from: 'Berlin', to: 'Dubai' },
  { from: 'San Francisco', to: 'Tokyo' },
]

export const mockAIModels = [
  { name: 'GPT-5', status: 'Connected', color: 'success' },
  { name: 'Claude', status: 'Connected', color: 'success' },
  { name: 'Gemini', status: 'Connected', color: 'success' },
  { name: 'Cursor', status: 'Connected', color: 'success' },
]

export const mockFiles = [
  { name: 'dataset.zip', size: '4.2 GB', status: 'Shared', downloads: 142, icon: 'archive' },
  { name: 'movie.mov', size: '12.4 GB', status: 'Processing', downloads: 0, icon: 'video' },
  { name: 'report.pdf', size: '8.2 MB', status: 'Ready', downloads: 421, icon: 'file' },
  { name: 'image.png', size: '3.1 MB', status: 'Downloaded', downloads: 89, icon: 'image' },
  { name: 'model_weights.bin', size: '8.1 GB', status: 'Shared', downloads: 67, icon: 'database' },
  { name: 'keynote.mp4', size: '2.3 GB', status: 'Ready', downloads: 234, icon: 'video' },
]

export const commandPaletteItems = [
  { label: 'Transfer', icon: 'arrow-right-left', section: 'Navigate' },
  { label: 'Analytics', icon: 'bar-chart-3', section: 'Navigate' },
  { label: 'Users', icon: 'users', section: 'Navigate' },
  { label: 'Storage', icon: 'hard-drive', section: 'Navigate' },
  { label: 'Sessions', icon: 'monitor', section: 'Navigate' },
  { label: 'Logs', icon: 'scroll-text', section: 'Navigate' },
  { label: 'Search', icon: 'search', section: 'Navigate' },
  { label: 'Settings', icon: 'settings', section: 'Navigate' },
  { label: 'API', icon: 'code', section: 'Navigate' },
  { label: 'Nodes', icon: 'server', section: 'Navigate' },
  { label: 'Upload File', icon: 'upload', section: 'Actions' },
  { label: 'Create Share Link', icon: 'link', section: 'Actions' },
  { label: 'New Session', icon: 'plus', section: 'Actions' },
]

export const aiQueries = [
  'Summarize',
  'Find duplicates',
  'Extract tables',
  'Generate metadata',
  'Translate',
  'Create captions',
  'Index for search',
  'Compare versions',
  'Generate embeddings',
  'Explain contents',
]

export const eventTemplates = [
  { type: 'UPLOAD', detail: (f, s) => `${s}`, status: 'Integrity Verified', color: 'primary' },
  { type: 'DOWNLOAD', detail: () => 'Completed', status: '', color: 'success' },
  { type: 'SHARE', detail: () => 'Link Created', status: '', color: 'accent' },
  { type: 'API', detail: (f, s) => `${s}`, status: '', color: 'secondary' },
  { type: 'STREAM', detail: () => 'Started', status: '', color: 'accent' },
  { type: 'REPLICATE', detail: () => `Edge: ${Math.floor(Math.random() * 4) + 2} nodes`, status: '', color: 'success' },
]

export const fileNames = [
  'movie.mov', 'dataset.tar.gz', 'model_weights.bin', 'presentation.mp4',
  'archive_2026.zip', 'research_data.csv', 'images.zip', 'keynote.mp4',
  'report.pdf', 'backup.sql', 'vector_index.faiss', 'training_set.parquet',
]

export const fileSizes = [
  '12.4 GB', '4.2 GB', '8.1 GB', '2.3 GB', '340 MB', '890 MB',
  '16 MB', '1.2 GB', '45 GB', '128 MB', '7.7 GB', '23 GB',
]
