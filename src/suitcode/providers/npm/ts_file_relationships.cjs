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
  compilerOptionsCache.set(configPath || "__default__", compilerOptions);
  return compilerOptions;
}

function specifiersForSourceFile(filePath) {
  const content = fs.readFileSync(filePath, "utf8");
  const sourceFile = ts.createSourceFile(filePath, content, ts.ScriptTarget.Latest, true);
  const results = [];

  function pushSpecifier(node) {
    if (node && ts.isStringLiteralLike(node) && node.text.trim()) {
      results.push(node.text.trim());
    }
  }

  function visit(node) {
    if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) {
      pushSpecifier(node.moduleSpecifier);
    } else if (ts.isImportEqualsDeclaration(node) && ts.isExternalModuleReference(node.moduleReference)) {
      pushSpecifier(node.moduleReference.expression);
    } else if (
      ts.isCallExpression(node) &&
      node.expression.kind === ts.SyntaxKind.ImportKeyword &&
      node.arguments.length === 1
    ) {
      pushSpecifier(node.arguments[0]);
    } else if (
      ts.isCallExpression(node) &&
      ts.isIdentifier(node.expression) &&
      node.expression.text === "require" &&
      node.arguments.length === 1
    ) {
      pushSpecifier(node.arguments[0]);
    }
    ts.forEachChild(node, visit);
  }

  visit(sourceFile);
  return results;
}

function resolveLocalImport(specifier, containingFile) {
  const options = compilerOptionsForFile(containingFile);
  const resolved = ts.resolveModuleName(specifier, containingFile, options, ts.sys).resolvedModule;
  if (!resolved || !resolved.resolvedFileName) {
    return null;
  }
  const resolvedPath = path.resolve(resolved.resolvedFileName);
  if (!resolvedPath.startsWith(projectRoot)) {
    return null;
  }
  if (resolvedPath.endsWith(".d.ts")) {
    return null;
  }
  if (!isSupportedFile(resolvedPath) || isIgnoredPath(resolvedPath)) {
    return null;
  }
  return resolvedPath;
}

function toRepositoryRelative(filePath) {
  return path.relative(repositoryRoot, filePath).split(path.sep).join("/");
}

if (!targetFile.startsWith(projectRoot)) {
  console.log(JSON.stringify({ imports: [], imported_by: [] }));
  process.exit(0);
}
if (!fs.existsSync(targetFile) || !fs.statSync(targetFile).isFile()) {
  console.error(`target file does not exist: ${targetFile}`);
  process.exit(1);
}
if (!isSupportedFile(targetFile)) {
  console.log(JSON.stringify({ imports: [], imported_by: [] }));
  process.exit(0);
}

const imports = new Set();
const importedBy = new Set();
const allFiles = walkFiles(projectRoot);

for (const filePath of allFiles) {
  const specifiers = specifiersForSourceFile(filePath);
  const resolvedImports = new Set();
  for (const specifier of specifiers) {
    const resolved = resolveLocalImport(specifier, filePath);
    if (resolved && resolved !== filePath) {
      resolvedImports.add(resolved);
    }
  }
  if (filePath === targetFile) {
    for (const resolved of resolvedImports) {
      imports.add(toRepositoryRelative(resolved));
    }
    continue;
  }
  if (resolvedImports.has(targetFile)) {
    importedBy.add(toRepositoryRelative(filePath));
  }
}

console.log(
  JSON.stringify({
    imports: Array.from(imports).sort(),
    imported_by: Array.from(importedBy).sort(),
  }),
);
