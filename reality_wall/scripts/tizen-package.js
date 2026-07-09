/**
 * Tizen packaging script — copies dist/ + config.xml into a Tizen widget structure.
 * Requires Tizen Studio for final .wgt packaging, but this prepares the structure.
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const root = path.resolve(__dirname, '..');

const widgetDir = path.join(root, 'tizen', 'widget');

if (fs.existsSync(widgetDir)) {
  fs.rmSync(widgetDir, { recursive: true });
}
fs.mkdirSync(widgetDir, { recursive: true });

const distDir = path.join(root, 'dist');
if (!fs.existsSync(distDir)) {
  console.error('dist/ not found — run `npm run build` first');
  process.exit(1);
}

function copyDir(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, entry.name);
    const d = path.join(dest, entry.name);
    if (entry.isDirectory()) copyDir(s, d);
    else fs.copyFileSync(s, d);
  }
}

copyDir(distDir, widgetDir);

const configSrc = path.join(root, 'tizen', 'config.xml');
const configDest = path.join(widgetDir, 'config.xml');
fs.copyFileSync(configSrc, configDest);

console.log('Tizen widget structure prepared at:', widgetDir);
console.log('');
console.log('To package as .wgt with Tizen Studio:');
console.log('  tizen package -t wgt -s <signing-profile> ' + widgetDir);
console.log('');
console.log('Or install directly via Tizen CLI:');
console.log('  tizen install -t wgt -n RealityWall.wgt -d <device-ip>');
