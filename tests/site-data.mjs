import fs from 'node:fs';
import path from 'node:path';

export function siteData(root = '.') {
  let raw = 'data/results.json';
  const configPath = path.join(root, 'publication.json');
  if (fs.existsSync(configPath)) {
    const config = JSON.parse(fs.readFileSync(configPath));
    raw = JSON.parse(fs.readFileSync(path.join(root, config.file_map)))['data/results.json'];
  }
  return JSON.parse(fs.readFileSync(path.join(root, raw), 'utf8'));
}
