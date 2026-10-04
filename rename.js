import fs from 'fs';
import path from 'path';

const targetDirs = ['./src', './public', './index.html', './package.json'];

function replaceInFile(filePath) {
  try {
    let content = fs.readFileSync(filePath, 'utf8');
    let replaced = content
      .replace(/CarbonSetu/g, 'CarbonX')
      .replace(/carbonsetu/g, 'carbonx');
    
    if (content !== replaced) {
      fs.writeFileSync(filePath, replaced, 'utf8');
      console.log(`Replaced in: ${filePath}`);
    }
  } catch (err) {
    console.error(`Error reading/writing file ${filePath}:`, err);
  }
}

function traverseDirectory(dir) {
  try {
    const stats = fs.statSync(dir);
    if (stats.isFile()) {
      if (dir.endsWith('.js') || dir.endsWith('.jsx') || dir.endsWith('.html') || dir.endsWith('.css') || dir.endsWith('.json')) {
        replaceInFile(dir);
      }
      return;
    }

    const files = fs.readdirSync(dir);
    for (const file of files) {
      const fullPath = path.join(dir, file);
      const fileStats = fs.statSync(fullPath);
      if (fileStats.isDirectory()) {
        if (file !== 'node_modules' && file !== '.git' && file !== 'dist') {
          traverseDirectory(fullPath);
        }
      } else {
        if (fullPath.endsWith('.js') || fullPath.endsWith('.jsx') || fullPath.endsWith('.html') || fullPath.endsWith('.css') || fullPath.endsWith('.json')) {
          replaceInFile(fullPath);
        }
      }
    }
  } catch (err) {
    console.error(`Error traversing directory ${dir}:`, err);
  }
}

console.log('Starting global rename from CarbonSetu to CarbonX...');
for (const target of targetDirs) {
  traverseDirectory(target);
}
console.log('Rename complete!');
