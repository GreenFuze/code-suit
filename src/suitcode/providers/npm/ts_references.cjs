#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

const [repoRootArg, attachmentRootArg, targetFileArg, lineArg, columnArg, includeDefinitionArg, tsLibraryArg] =
  process.argv.slice(2);

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(1);
}

if (!repoRootArg || !attachmentRootArg || !targetFileArg || !lineArg || !columnArg || !tsLibraryArg) {
  fail("usage: ts_references.cjs <repo-root> <attachment-root> <target-file> <line> <column> <include-definition> <typescript-lib>");
}

const repoRoot = path.resolve(repoRootArg);
const attachmentRoot = path.resolve(attachmentRootArg);
const targetFile = path.resolve(targetFileArg);
const line = Number.parseInt(lineArg, 10);
const column = Number.parseInt(columnArg, 10);
const includeDefinition = includeDefinitionArg === "true";

if (!Number.isInteger(line) || line < 1 || !Number.isInteger(column) || column < 1) {
  fail("line and column must be positive integers");
}

const ts = require(tsLibraryArg);

function normalizePath(value) {
  return path.resolve(value);
}

function isIgnoredSourceFile(sourceFile) {
  const fileName = normalizePath(sourceFile.fileName);
  return sourceFile.isDeclarationFile || fileName.includes(`${path.sep}node_modules${path.sep}`);
}

function findConfigPath() {
  const config = ts.findConfigFile(path.dirname(targetFile), ts.sys.fileExists, "tsconfig.json");
  if (config) {
    return config;
  }
  const attachmentConfig = path.join(attachmentRoot, "tsconfig.json");
  return fs.existsSync(attachmentConfig) ? attachmentConfig : undefined;
}

function buildProgram() {
  const configPath = findConfigPath();
  if (!configPath) {
    return ts.createProgram([targetFile], { allowJs: true, jsx: ts.JsxEmit.ReactJSX, noEmit: true });
  }
  const configFile = ts.readConfigFile(configPath, ts.sys.readFile);
  if (configFile.error) {
    const message = ts.flattenDiagnosticMessageText(configFile.error.messageText, "\n");
    fail(`unable to read tsconfig: ${message}`);
  }
  const parsed = ts.parseJsonConfigFileContent(
    configFile.config,
    ts.sys,
    path.dirname(configPath),
    { noEmit: true },
    configPath,
  );
  if (parsed.errors.length) {
    const message = parsed.errors.map((item) => ts.flattenDiagnosticMessageText(item.messageText, "\n")).join("; ");
    fail(`unable to parse tsconfig: ${message}`);
  }
  return ts.createProgram(parsed.fileNames, parsed.options);
}

function containsPosition(node, position) {
  return node.getStart() <= position && position < node.getEnd();
}

function findIdentifierAtPosition(node, position) {
  if (!containsPosition(node, position)) {
    return undefined;
  }
  let best = undefined;
  node.forEachChild((child) => {
    const candidate = findIdentifierAtPosition(child, position);
    if (candidate) {
      best = candidate;
    }
  });
  if (best) {
    return best;
  }
  if (ts.isIdentifier(node) && containsPosition(node, position)) {
    return node;
  }
  if (node.name && ts.isIdentifier(node.name) && containsPosition(node.name, position)) {
    return node.name;
  }
  return undefined;
}

function canonicalSymbol(checker, symbol) {
  if (!symbol) {
    return undefined;
  }
  if ((symbol.flags & ts.SymbolFlags.Alias) !== 0) {
    try {
      const aliased = checker.getAliasedSymbol(symbol);
      if (aliased && aliased !== symbol) {
        return aliased;
      }
    } catch (_err) {
      return symbol;
    }
  }
  return symbol;
}

function declarationKey(declaration) {
  if (!declaration || !declaration.getSourceFile) {
    return undefined;
  }
  const sourceFile = declaration.getSourceFile();
  return `${normalizePath(sourceFile.fileName)}:${declaration.getStart(sourceFile)}:${declaration.getEnd()}`;
}

function symbolKeys(symbol) {
  if (!symbol || !symbol.declarations) {
    return new Set();
  }
  return new Set(symbol.declarations.map(declarationKey).filter(Boolean));
}

function sameSymbol(left, right) {
  if (!left || !right) {
    return false;
  }
  if (left === right) {
    return true;
  }
  const leftKeys = symbolKeys(left);
  for (const key of symbolKeys(right)) {
    if (leftKeys.has(key)) {
      return true;
    }
  }
  return false;
}

function locationForIdentifier(identifier) {
  const sourceFile = identifier.getSourceFile();
  const start = sourceFile.getLineAndCharacterOfPosition(identifier.getStart(sourceFile));
  const end = sourceFile.getLineAndCharacterOfPosition(identifier.getEnd());
  return {
    path: path.relative(repoRoot, normalizePath(sourceFile.fileName)).split(path.sep).join("/"),
    line_start: start.line + 1,
    line_end: end.line + 1,
    column_start: start.character + 1,
    column_end: end.character + 1,
  };
}

const program = buildProgram();
const checker = program.getTypeChecker();
const targetSourceFile = program.getSourceFile(targetFile);
if (!targetSourceFile) {
  fail(`target file is not part of the TypeScript program: ${targetFile}`);
}
const position = ts.getPositionOfLineAndCharacter(targetSourceFile, line - 1, column - 1);
const targetIdentifier = findIdentifierAtPosition(targetSourceFile, position);
if (!targetIdentifier) {
  process.stdout.write(JSON.stringify({ references: [] }));
  process.exit(0);
}
const targetSymbol = canonicalSymbol(checker, checker.getSymbolAtLocation(targetIdentifier));
if (!targetSymbol) {
  process.stdout.write(JSON.stringify({ references: [] }));
  process.exit(0);
}

const targetLocation = locationForIdentifier(targetIdentifier);
const references = [];
const seen = new Set();

function visit(node) {
  if (ts.isIdentifier(node)) {
    const symbol = canonicalSymbol(checker, checker.getSymbolAtLocation(node));
    if (sameSymbol(targetSymbol, symbol)) {
      const location = locationForIdentifier(node);
      const isDefinition =
        location.path === targetLocation.path &&
        location.line_start === targetLocation.line_start &&
        location.column_start === targetLocation.column_start &&
        location.line_end === targetLocation.line_end &&
        location.column_end === targetLocation.column_end;
      if (includeDefinition || !isDefinition) {
        const key = `${location.path}:${location.line_start}:${location.column_start}:${location.line_end}:${location.column_end}`;
        if (!seen.has(key)) {
          seen.add(key);
          references.push(location);
        }
      }
    }
  }
  ts.forEachChild(node, visit);
}

for (const sourceFile of program.getSourceFiles()) {
  if (isIgnoredSourceFile(sourceFile)) {
    continue;
  }
  visit(sourceFile);
}

references.sort((left, right) =>
  left.path.localeCompare(right.path) ||
  left.line_start - right.line_start ||
  left.column_start - right.column_start ||
  left.line_end - right.line_end ||
  left.column_end - right.column_end
);

process.stdout.write(JSON.stringify({ references }));
