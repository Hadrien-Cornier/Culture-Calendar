#!/usr/bin/env node
// scripts/patch_gitnexus_template.js
//
// Patches gitnexus's auto-generated AI context template to use
// `npm run analyze` instead of `npx gitnexus analyze`, which fails
// on Node v24 due to a tree-sitter-swift npm rebuild bug.
//
// Run manually:  node scripts/patch_gitnexus_template.js
// Or add to package.json as a postinstall script.

import { readFileSync, writeFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const TARGET = join(__dirname, '../node_modules/gitnexus/dist/cli/ai-context.js');

let content;
try {
  content = readFileSync(TARGET, 'utf8');
} catch (err) {
  console.error(`Could not read ${TARGET}: ${err.message}`);
  console.error('Run `npm install` first.');
  process.exit(1);
}

const patches = [
  {
    old: 'run \\`npx gitnexus analyze\\` in terminal first.',
    new: 'run \\`npm run analyze\\` (or \\`./node_modules/.bin/gitnexus analyze\\`) in terminal first. **Do not use \\`npx gitnexus\\`** — it fails on Node v24 due to a tree-sitter-swift rebuild bug.',
  },
  {
    // bash block: npx gitnexus analyze (bare, in backtick-escaped code block)
    old: '\\`\\`\\`bash\\nnpm run analyze\\n\\`\\`\\`',
    new: null, // already correct if previous patch ran
  },
];

let changed = 0;
for (const { old: from, new: to } of patches) {
  if (to === null) continue; // skip no-op entries
  if (content.includes(from)) {
    content = content.replaceAll(from, to);
    changed++;
    console.log(`✅ Patched: "${from.slice(0, 60)}..."`);
  } else {
    console.log(`⏭  Already patched or not found: "${from.slice(0, 60)}..."`);
  }
}

if (changed > 0) {
  writeFileSync(TARGET, content, 'utf8');
  console.log(`\nWrote ${changed} patch(es) to ${TARGET}`);
} else {
  console.log('\nNo changes needed — template already up to date.');
}
