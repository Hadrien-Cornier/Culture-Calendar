#!/usr/bin/env node

import fs from "fs";
import path from "path";
import { createRequire } from "module";

const variantPath = process.argv[2];

if (!variantPath) {
  console.error("Usage: check_variant.mjs <variant-path>");
  process.exit(1);
}

const resolvedPath = path.resolve(variantPath);
const errors = [];

// Check required files exist
const requiredFiles = ["index.html", "script.js", "styles.css"];
for (const file of requiredFiles) {
  const filePath = path.join(resolvedPath, file);
  if (!fs.existsSync(filePath)) {
    errors.push(`Missing required file: ${file}`);
  }
}

// Check script.js for syntax errors
const scriptPath = path.join(resolvedPath, "script.js");
if (fs.existsSync(scriptPath)) {
  try {
    const content = fs.readFileSync(scriptPath, "utf-8");
    // Basic check: ensure it's not empty and contains expected patterns
    if (!content.trim()) {
      errors.push("script.js is empty");
    }
    if (!content.includes("renderListings")) {
      errors.push("script.js missing renderListings function");
    }
    // Check for paragraph parsing
    if (!content.includes('split(/\\n\\n+/)')) {
      errors.push("script.js missing paragraph parsing logic");
    }
    // Check for byline
    if (!content.includes('event-byline')) {
      errors.push("script.js missing event-byline class");
    }
    // Check for dateline
    if (!content.includes('event-dateline')) {
      errors.push("script.js missing event-dateline class");
    }
    // Check for first/body paragraph classes
    if (!content.includes('event-review-first')) {
      errors.push("script.js missing event-review-first class");
    }
    if (!content.includes('event-review-body')) {
      errors.push("script.js missing event-review-body class");
    }
  } catch (err) {
    errors.push(`Failed to read script.js: ${err.message}`);
  }
}

// Check styles.css for required classes
const stylesPath = path.join(resolvedPath, "styles.css");
if (fs.existsSync(stylesPath)) {
  try {
    const content = fs.readFileSync(stylesPath, "utf-8");
    const requiredClasses = [
      ".event-review-first",
      ".event-review-body",
      ".event-byline",
      ".event-dateline"
    ];
    for (const cls of requiredClasses) {
      if (!content.includes(cls)) {
        errors.push(`styles.css missing required class: ${cls}`);
      }
    }
    // Check for small-caps in dateline
    if (!content.includes("small-caps")) {
      errors.push("styles.css missing small-caps styling for dateline");
    }
  } catch (err) {
    errors.push(`Failed to read styles.css: ${err.message}`);
  }
}

// Check index.html references script.js
const indexPath = path.join(resolvedPath, "index.html");
if (fs.existsSync(indexPath)) {
  try {
    const content = fs.readFileSync(indexPath, "utf-8");
    if (!content.includes("script.js")) {
      errors.push("index.html doesn't reference script.js");
    }
    if (!content.includes("styles.css")) {
      errors.push("index.html doesn't reference styles.css");
    }
  } catch (err) {
    errors.push(`Failed to read index.html: ${err.message}`);
  }
}

if (errors.length > 0) {
  console.error(`✗ ${path.basename(resolvedPath)} validation failed:\n`);
  errors.forEach((err) => console.error(`  - ${err}`));
  process.exit(1);
} else {
  console.log(`✓ ${path.basename(resolvedPath)} variant validation passed`);
  process.exit(0);
}
