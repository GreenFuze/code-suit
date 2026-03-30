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
  return ts.createProgram({
    rootNames: files,
    options: compilerOptionsForFile(targetFile),
  });
}

function toRepositoryRelative(filePath) {
  return path.relative(repositoryRoot, filePath).split(path.sep).join("/");
}

function locationOf(sourceFile, node) {
  const position = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile, false));
  return {
    lineStart: position.line + 1,
    columnStart: position.character + 1,
  };
}

function typeIncludesNullish(type) {
  if (!type) return false;
  if ((type.flags & ts.TypeFlags.Undefined) !== 0 || (type.flags & ts.TypeFlags.Null) !== 0) {
    return true;
  }
  if (type.isUnion && type.isUnion()) {
    return type.types.some((item) => typeIncludesNullish(item));
  }
  return false;
}

function declarationHasQuestionToken(declaration) {
  return Boolean(declaration && declaration.questionToken);
}

function symbolIsOptional(symbol) {
  if (!symbol) return false;
  if ((symbol.flags & ts.SymbolFlags.Optional) !== 0) {
    return true;
  }
  const declarations = symbol.getDeclarations() || [];
  return declarations.some((item) => declarationHasQuestionToken(item));
}

function isOptionalPropertyAccessNode(node) {
  return Boolean(node.questionDotToken) || ts.isPropertyAccessChain(node);
}

function resolveAliasedSymbol(checker, symbol) {
  if (!symbol) {
    return null;
  }
  if ((symbol.flags & ts.SymbolFlags.Alias) !== 0) {
    try {
      return checker.getAliasedSymbol(symbol);
    } catch {
      return null;
    }
  }
  return symbol;
}

function localDeclarationTarget(checker, symbol, sourceFile) {
  const resolved = resolveAliasedSymbol(checker, symbol);
  if (!resolved) {
    return null;
  }
  const declarations = resolved.getDeclarations() || (resolved.valueDeclaration ? [resolved.valueDeclaration] : []);
  for (const declaration of declarations) {
    const declarationFile = declaration.getSourceFile();
    const declarationPath = path.resolve(declarationFile.fileName);
    if (!declarationPath.startsWith(projectRoot)) {
      continue;
    }
    if (!isSupportedFile(declarationPath) || declarationPath.endsWith(".d.ts") || isIgnoredPath(declarationPath)) {
      continue;
    }
    const { lineStart, columnStart } = locationOf(declarationFile, declaration.name || declaration);
    return {
      path: declarationPath,
      sourceFile: declarationFile,
      declaration,
      label: resolved.getName ? resolved.getName() : (declaration.name ? declaration.name.getText() : "anonymous"),
      lineStart,
      columnStart,
    };
  }
  return null;
}

function labelForFunctionLike(node) {
  if (node.name && ts.isIdentifier(node.name)) {
    return node.name.text;
  }
  if (node.parent && ts.isVariableDeclaration(node.parent) && ts.isIdentifier(node.parent.name)) {
    return node.parent.name.text;
  }
  if (node.parent && ts.isPropertyAssignment(node.parent) && ts.isIdentifier(node.parent.name)) {
    return node.parent.name.text;
  }
  return "anonymous";
}

function collectScopeLabels(sourceFile) {
  const labels = new Map();
  function visit(node, currentLabel) {
    let nextLabel = currentLabel;
    if (
      ts.isFunctionDeclaration(node) ||
      ts.isFunctionExpression(node) ||
      ts.isArrowFunction(node) ||
      ts.isMethodDeclaration(node)
    ) {
      nextLabel = labelForFunctionLike(node);
    }
    labels.set(node, nextLabel);
    ts.forEachChild(node, (child) => visit(child, nextLabel));
  }
  visit(sourceFile, path.basename(sourceFile.fileName));
  return labels;
}

function containsFieldInObjectLiteral(literal, fieldName) {
  for (const property of literal.properties) {
    if (ts.isPropertyAssignment(property) || ts.isShorthandPropertyAssignment(property) || ts.isMethodDeclaration(property)) {
      const name = property.name && ts.isIdentifier(property.name) ? property.name.text : property.name ? property.name.getText() : "";
      if (name === fieldName) {
        return true;
      }
    }
    if (ts.isSpreadAssignment(property)) {
      return true;
    }
  }
  return false;
}

function explicitReturnObjectLiterals(functionLike) {
  if (!functionLike.body) {
    return [];
  }
  if (ts.isObjectLiteralExpression(functionLike.body)) {
    return [functionLike.body];
  }
  if (!ts.isBlock(functionLike.body)) {
    return [];
  }
  const literals = [];
  function visit(node) {
    if (ts.isReturnStatement(node) && node.expression && ts.isObjectLiteralExpression(node.expression)) {
      literals.push(node.expression);
    }
    ts.forEachChild(node, visit);
  }
  visit(functionLike.body);
  return literals;
}

function producerSitesForFunctionTarget(target, fieldName) {
  const declaration = target.declaration;
  const sourceFile = target.sourceFile;
  if (
    ts.isFunctionDeclaration(declaration) ||
    ts.isFunctionExpression(declaration) ||
    ts.isArrowFunction(declaration) ||
    ts.isMethodDeclaration(declaration)
  ) {
    const objectReturns = explicitReturnObjectLiterals(declaration);
    const missing = objectReturns.filter((item) => !containsFieldInObjectLiteral(item, fieldName));
    if (missing.length > 0) {
      return missing.map((item) => {
        const { lineStart, columnStart } = locationOf(sourceFile, item);
        return {
          path: toRepositoryRelative(sourceFile.fileName),
          line_start: lineStart,
          column_start: columnStart,
          label: target.label,
        };
      });
    }
  }
  return [];
}

function producerSitesForExpression(checker, expression, fieldName) {
  if (ts.isIdentifier(expression)) {
    const symbol = resolveAliasedSymbol(checker, checker.getSymbolAtLocation(expression));
    if (!symbol) {
      return [];
    }
    const declarations = symbol.getDeclarations() || [];
    for (const declaration of declarations) {
      if (ts.isVariableDeclaration(declaration) && declaration.initializer) {
        const declarationFile = declaration.getSourceFile();
        if (!path.resolve(declarationFile.fileName).startsWith(projectRoot)) {
          continue;
        }
        if (ts.isObjectLiteralExpression(declaration.initializer)) {
          if (containsFieldInObjectLiteral(declaration.initializer, fieldName)) {
            return [];
          }
          const { lineStart, columnStart } = locationOf(declarationFile, declaration.initializer);
          return [{
            path: toRepositoryRelative(declarationFile.fileName),
            line_start: lineStart,
            column_start: columnStart,
            label: declaration.name.getText(),
          }];
        }
        if (ts.isCallExpression(declaration.initializer)) {
          const target = resolveCallTarget(checker, declaration.initializer.expression);
          if (target) {
            return producerSitesForFunctionTarget(target, fieldName);
          }
        }
      }
    }
  }
  if (ts.isCallExpression(expression)) {
    const target = resolveCallTarget(checker, expression.expression);
    if (target) {
      return producerSitesForFunctionTarget(target, fieldName);
    }
  }
  return [];
}

function callTargetLabel(expression) {
  if (ts.isIdentifier(expression)) {
    return expression.text;
  }
  if (ts.isPropertyAccessExpression(expression)) {
    return expression.name.text;
  }
  return expression.getText();
}

function resolveCallTarget(checker, expression) {
  if (!ts.isIdentifier(expression) && !ts.isPropertyAccessExpression(expression)) {
    return null;
  }
  const symbol = checker.getSymbolAtLocation(expression);
  if (!symbol) {
    return null;
  }
  return localDeclarationTarget(checker, symbol, expression.getSourceFile());
}

function collectFlowEdges(sourceFile, checker) {
  const scopeLabels = collectScopeLabels(sourceFile);
  const edges = new Map();

  function addEdge(edge) {
    const key = `${edge.path}:${edge.edge_kind}:${edge.line_start}:${edge.column_start}:${edge.source_label}:${edge.target_label}`;
    edges.set(key, edge);
  }

  function currentLabel(node) {
    return scopeLabels.get(node) || path.basename(sourceFile.fileName);
  }

  function visit(node) {
    if (ts.isCallExpression(node)) {
      const directTarget = resolveCallTarget(checker, node.expression);
      if (directTarget) {
        const { lineStart, columnStart } = locationOf(sourceFile, node.expression);
        addEdge({
          path: toRepositoryRelative(directTarget.path),
          edge_kind: "calls_local_symbol",
          line_start: lineStart,
          column_start: columnStart,
          source_label: currentLabel(node),
          target_label: directTarget.label,
        });
      }
      for (const argument of node.arguments) {
        if (ts.isCallExpression(argument)) {
          const innerTarget = resolveCallTarget(checker, argument.expression);
          if (!innerTarget) {
            continue;
          }
          const { lineStart, columnStart } = locationOf(sourceFile, argument.expression);
          addEdge({
            path: toRepositoryRelative(sourceFile.fileName),
            edge_kind: "produces_value_for",
            line_start: lineStart,
            column_start: columnStart,
            source_label: innerTarget.label,
            target_label: callTargetLabel(node.expression),
          });
        }
      }
    }
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.initializer && ts.isCallExpression(node.initializer)) {
      const target = resolveCallTarget(checker, node.initializer.expression);
      if (target) {
        const { lineStart, columnStart } = locationOf(sourceFile, node.initializer.expression);
        addEdge({
          path: toRepositoryRelative(sourceFile.fileName),
          edge_kind: "produces_value_for",
          line_start: lineStart,
          column_start: columnStart,
          source_label: target.label,
          target_label: node.name.text,
        });
      }
    }
    if (
      ts.isBinaryExpression(node) &&
      node.operatorToken.kind === ts.SyntaxKind.EqualsToken &&
      ts.isIdentifier(node.left) &&
      ts.isCallExpression(node.right)
    ) {
      const target = resolveCallTarget(checker, node.right.expression);
      if (target) {
        const { lineStart, columnStart } = locationOf(sourceFile, node.right.expression);
        addEdge({
          path: toRepositoryRelative(sourceFile.fileName),
          edge_kind: "produces_value_for",
          line_start: lineStart,
          column_start: columnStart,
          source_label: target.label,
          target_label: node.left.text,
        });
      }
    }
    ts.forEachChild(node, visit);
  }

  visit(sourceFile);
  return Array.from(edges.values()).sort((a, b) =>
    a.path.localeCompare(b.path) ||
    a.line_start - b.line_start ||
    a.column_start - b.column_start ||
    a.source_label.localeCompare(b.source_label) ||
    a.target_label.localeCompare(b.target_label)
  );
}

function collectInvariantFindings(sourceFile, checker) {
  const findings = new Map();

  function addFinding(finding) {
    const key = `${finding.path}:${finding.access_kind}:${finding.line_start}:${finding.column_start}:${finding.field_name}:${finding.subject_label}`;
    findings.set(key, finding);
  }

  function visit(node) {
    if (ts.isPropertyAccessExpression(node) && !isOptionalPropertyAccessNode(node)) {
      const propertySymbol = checker.getSymbolAtLocation(node.name);
      const nodeType = checker.getTypeAtLocation(node);
      const accessKind =
        ts.isCallExpression(node.parent) && node.parent.expression === node ? "method_call" : "property_read";
      const maybeMissing = symbolIsOptional(propertySymbol) || typeIncludesNullish(nodeType);
      if (maybeMissing) {
        const { lineStart, columnStart } = locationOf(sourceFile, node.name);
        const producerSites = producerSitesForExpression(checker, node.expression, node.name.text);
        addFinding({
          path: toRepositoryRelative(sourceFile.fileName),
          access_kind: accessKind,
          line_start: lineStart,
          column_start: columnStart,
          field_name: node.name.text,
          subject_label: ts.isIdentifier(node.expression) ? node.expression.text : node.expression.getText(),
          declared_type: checker.typeToString(nodeType),
          producer_sites: producerSites,
        });
      }
    }
    ts.forEachChild(node, visit);
  }

  visit(sourceFile);
  return Array.from(findings.values()).sort((a, b) =>
    a.path.localeCompare(b.path) ||
    a.line_start - b.line_start ||
    a.column_start - b.column_start ||
    a.field_name.localeCompare(b.field_name)
  );
}

if (!targetFile.startsWith(projectRoot)) {
  console.log(JSON.stringify({ invariant_findings: [], local_flow_edges: [] }));
  process.exit(0);
}
if (!fs.existsSync(targetFile) || !fs.statSync(targetFile).isFile()) {
  console.error(`target file does not exist: ${targetFile}`);
  process.exit(1);
}
if (!isSupportedFile(targetFile) || targetFile.endsWith(".d.ts")) {
  console.log(JSON.stringify({ invariant_findings: [], local_flow_edges: [] }));
  process.exit(0);
}

const allFiles = walkFiles(projectRoot);
const program = createProgram(allFiles);
const checker = program.getTypeChecker();
const sourceFile = program.getSourceFile(targetFile);
if (!sourceFile) {
  console.log(JSON.stringify({ invariant_findings: [], local_flow_edges: [] }));
  process.exit(0);
}

console.log(JSON.stringify({
  invariant_findings: collectInvariantFindings(sourceFile, checker),
  local_flow_edges: collectFlowEdges(sourceFile, checker),
}));
