#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");

const [, , repositoryRootArg, projectRootArg, targetFileArg, typescriptPathArg] = process.argv;

if (!repositoryRootArg || !projectRootArg || !targetFileArg || !typescriptPathArg) {
  console.error("expected arguments: <repository_root> <project_root> <target_file> <typescript_library_path>");
  process.exit(2);
}

const repositoryRoot = path.resolve(repositoryRootArg);
const projectRoot = path.resolve(projectRootArg);
const targetFile = path.resolve(targetFileArg);
const typescriptPath = path.resolve(typescriptPathArg);
const ts = require(typescriptPath);

const SUPPORTED_EXTENSIONS = new Set([".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs"]);
const IGNORED_DIRECTORIES = new Set(["node_modules", ".git", ".suit", "dist", "build", ".next", "coverage"]);
const configPathCache = new Map();
const compilerOptionsCache = new Map();

function isSupportedFile(filePath) {
  return SUPPORTED_EXTENSIONS.has(path.extname(filePath).toLowerCase());
}

function isIgnoredPath(filePath) {
  const relative = path.relative(projectRoot, filePath);
  if (!relative || relative.startsWith("..")) {
    return true;
  }
  return relative.split(path.sep).some((part) => IGNORED_DIRECTORIES.has(part));
}

function walkFiles(rootDir) {
  const results = [];
  const stack = [rootDir];
  while (stack.length > 0) {
    const current = stack.pop();
    const entries = fs.readdirSync(current, { withFileTypes: true });
    for (const entry of entries) {
      const nextPath = path.join(current, entry.name);
      if (entry.isDirectory()) {
        if (IGNORED_DIRECTORIES.has(entry.name) || entry.name.startsWith(".")) {
          continue;
        }
        stack.push(nextPath);
        continue;
      }
      if (entry.isFile() && isSupportedFile(nextPath) && !isIgnoredPath(nextPath)) {
        results.push(nextPath);
      }
    }
  }
  return results.sort();
}

function findNearestConfig(filePath) {
  const directory = path.dirname(filePath);
  if (configPathCache.has(directory)) {
    return configPathCache.get(directory);
  }
  let current = directory;
  while (true) {
    for (const candidateName of ["tsconfig.json", "jsconfig.json"]) {
      const candidate = path.join(current, candidateName);
      if (fs.existsSync(candidate)) {
        configPathCache.set(directory, candidate);
        return candidate;
      }
    }
    if (current === projectRoot) {
      break;
    }
    const parent = path.dirname(current);
    if (parent === current || !current.startsWith(projectRoot)) {
      break;
    }
    current = parent;
  }
  configPathCache.set(directory, null);
  return null;
}

function compilerOptionsForFile(filePath) {
  const configPath = findNearestConfig(filePath);
  if (compilerOptionsCache.has(configPath || "__default__")) {
    return compilerOptionsCache.get(configPath || "__default__");
  }
  let compilerOptions;
  if (configPath) {
    const configFile = ts.readConfigFile(configPath, ts.sys.readFile);
    if (configFile.error) {
      throw new Error(ts.flattenDiagnosticMessageText(configFile.error.messageText, "\n"));
    }
    const parsed = ts.parseJsonConfigFileContent(
      configFile.config,
      ts.sys,
      path.dirname(configPath),
      undefined,
      configPath,
    );
    if (parsed.errors && parsed.errors.length > 0) {
      throw new Error(ts.flattenDiagnosticMessageText(parsed.errors[0].messageText, "\n"));
    }
    compilerOptions = parsed.options;
  } else {
    compilerOptions = {
      allowJs: true,
      jsx: ts.JsxEmit.ReactJSX,
      module: ts.ModuleKind.ESNext,
      moduleResolution: ts.ModuleResolutionKind.NodeJs,
      target: ts.ScriptTarget.ES2020,
    };
  }
  const merged = {
    ...compilerOptions,
    allowJs: true,
    jsx: compilerOptions.jsx ?? ts.JsxEmit.ReactJSX,
  };
  compilerOptionsCache.set(configPath || "__default__", merged);
  return merged;
}

function createProgram(files) {
  const options = compilerOptionsForFile(targetFile);
  return ts.createProgram({
    rootNames: files,
    options,
  });
}

function toRepositoryRelative(filePath) {
  return path.relative(repositoryRoot, filePath).split(path.sep).join("/");
}

function getResolvedComponentPath(checker, sourceFile, jsxTagName) {
  let symbol = checker.getSymbolAtLocation(jsxTagName);
  if (!symbol) {
    return null;
  }
  if ((symbol.flags & ts.SymbolFlags.Alias) !== 0) {
    try {
      symbol = checker.getAliasedSymbol(symbol);
    } catch {
      return null;
    }
  }
  const declarations = symbol.getDeclarations() || (symbol.valueDeclaration ? [symbol.valueDeclaration] : []);
  for (const declaration of declarations) {
    const declarationFile = declaration.getSourceFile();
    const declarationPath = path.resolve(declarationFile.fileName);
    if (!declarationPath.startsWith(projectRoot)) {
      continue;
    }
    if (!isSupportedFile(declarationPath) || declarationPath.endsWith(".d.ts") || isIgnoredPath(declarationPath)) {
      continue;
    }
    if (declarationPath === path.resolve(sourceFile.fileName)) {
      continue;
    }
    return declarationPath;
  }
  return null;
}

function collectPropInfo(openingElement) {
  const propNames = [];
  let hasSpreadProps = false;
  for (const attribute of openingElement.attributes.properties) {
    if (ts.isJsxAttribute(attribute)) {
      const name = attribute.name.getText().trim();
      if (name && !propNames.includes(name)) {
        propNames.push(name);
      }
      continue;
    }
    if (ts.isJsxSpreadAttribute(attribute)) {
      hasSpreadProps = true;
    }
  }
  return {
    propNames: propNames.sort(),
    hasSpreadProps,
  };
}

function renderSiteLocation(sourceFile, jsxTagName) {
  const position = sourceFile.getLineAndCharacterOfPosition(jsxTagName.getStart(sourceFile, false));
  return {
    lineStart: position.line + 1,
    columnStart: position.character + 1,
  };
}

function visitSourceFile(sourceFile, checker, onEdge) {
  function visit(node) {
    if (ts.isJsxSelfClosingElement(node) || ts.isJsxOpeningElement(node)) {
      const componentPath = getResolvedComponentPath(checker, sourceFile, node.tagName);
      if (componentPath) {
        const { propNames, hasSpreadProps } = collectPropInfo(node);
        const { lineStart, columnStart } = renderSiteLocation(sourceFile, node.tagName);
        onEdge({
          sourcePath: path.resolve(sourceFile.fileName),
          targetPath: componentPath,
          lineStart,
          columnStart,
          propNames,
          hasSpreadProps,
        });
      }
    }
    ts.forEachChild(node, visit);
  }

  visit(sourceFile);
}

if (!targetFile.startsWith(projectRoot)) {
  console.log(JSON.stringify({ renders: [], rendered_by: [] }));
  process.exit(0);
}
if (!fs.existsSync(targetFile) || !fs.statSync(targetFile).isFile()) {
  console.error(`target file does not exist: ${targetFile}`);
  process.exit(1);
}
if (!isSupportedFile(targetFile) || targetFile.endsWith(".d.ts")) {
  console.log(JSON.stringify({ renders: [], rendered_by: [] }));
  process.exit(0);
}

const allFiles = walkFiles(projectRoot);
const program = createProgram(allFiles);
const checker = program.getTypeChecker();
const renders = new Map();
const renderedBy = new Map();

for (const filePath of allFiles) {
  const sourceFile = program.getSourceFile(filePath);
  if (!sourceFile) {
    continue;
  }
  visitSourceFile(sourceFile, checker, (edge) => {
    if (edge.sourcePath === targetFile) {
      const key = `${edge.targetPath}:${edge.lineStart}:${edge.columnStart}:${edge.propNames.join(",")}:${edge.hasSpreadProps}`;
      renders.set(key, {
        path: toRepositoryRelative(edge.targetPath),
        line_start: edge.lineStart,
        column_start: edge.columnStart,
        prop_names: edge.propNames,
        has_spread_props: edge.hasSpreadProps,
      });
    }
    if (edge.targetPath === targetFile && edge.sourcePath !== targetFile) {
      const key = `${edge.sourcePath}:${edge.lineStart}:${edge.columnStart}:${edge.propNames.join(",")}:${edge.hasSpreadProps}`;
      renderedBy.set(key, {
        path: toRepositoryRelative(edge.sourcePath),
        line_start: edge.lineStart,
        column_start: edge.columnStart,
        prop_names: edge.propNames,
        has_spread_props: edge.hasSpreadProps,
      });
    }
  });
}

console.log(
  JSON.stringify({
    renders: Array.from(renders.values()).sort((a, b) =>
      a.path.localeCompare(b.path) ||
      a.line_start - b.line_start ||
      a.column_start - b.column_start
    ),
    rendered_by: Array.from(renderedBy.values()).sort((a, b) =>
      a.path.localeCompare(b.path) ||
      a.line_start - b.line_start ||
      a.column_start - b.column_start
    ),
  }),
);
