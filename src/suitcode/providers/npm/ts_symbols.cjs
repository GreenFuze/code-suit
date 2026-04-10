#!/usr/bin/env node
'use strict'

const fs = require('fs')
const path = require('path')

const [, , repositoryRootArg, targetFileArg, typescriptLibraryArg] = process.argv

if (!repositoryRootArg || !targetFileArg || !typescriptLibraryArg) {
  console.error('usage: ts_symbols.cjs <repository-root> <target-file> <typescript-library>')
  process.exit(2)
}

const repositoryRoot = path.resolve(repositoryRootArg)
const targetFile = path.resolve(targetFileArg)
const ts = require(typescriptLibraryArg)
const text = fs.readFileSync(targetFile, 'utf8')
const sourceFile = ts.createSourceFile(targetFile, text, ts.ScriptTarget.Latest, true, scriptKind(targetFile))
const symbols = []

function scriptKind(filePath) {
  const suffix = path.extname(filePath).toLowerCase()
  if (suffix === '.tsx') return ts.ScriptKind.TSX
  if (suffix === '.jsx') return ts.ScriptKind.JSX
  if (suffix === '.js' || suffix === '.mjs' || suffix === '.cjs') return ts.ScriptKind.JS
  return ts.ScriptKind.TS
}

function repositoryRelativePath(filePath) {
  return path.relative(repositoryRoot, filePath).replace(/\\/g, '/')
}

function locationForNode(node) {
  const start = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile))
  const end = sourceFile.getLineAndCharacterOfPosition(node.getEnd())
  return {
    line_start: start.line + 1,
    column_start: start.character + 1,
    line_end: end.line + 1,
    column_end: end.character + 1,
  }
}

function addSymbol(nameNode, kind, containerName = null, signature = null) {
  if (!nameNode || !nameNode.text) return
  const location = locationForNode(nameNode)
  symbols.push({
    name: nameNode.text,
    kind,
    path: repositoryRelativePath(targetFile),
    line_start: location.line_start,
    line_end: location.line_end,
    column_start: location.column_start,
    column_end: location.column_end,
    container_name: containerName,
    signature,
  })
}

function isFunctionInitializer(node) {
  return ts.isArrowFunction(node) || ts.isFunctionExpression(node)
}

function visit(node, containerName = null) {
  if (ts.isFunctionDeclaration(node)) {
    addSymbol(node.name, 'function', containerName)
  } else if (ts.isClassDeclaration(node)) {
    const className = node.name ? node.name.text : containerName
    addSymbol(node.name, 'class', containerName)
    for (const member of node.members) {
      if ((ts.isMethodDeclaration(member) || ts.isPropertyDeclaration(member)) && member.name && ts.isIdentifier(member.name)) {
        addSymbol(member.name, ts.isMethodDeclaration(member) ? 'method' : 'property', className || null)
      }
    }
  } else if (ts.isInterfaceDeclaration(node)) {
    addSymbol(node.name, 'interface', containerName)
  } else if (ts.isTypeAliasDeclaration(node)) {
    addSymbol(node.name, 'interface', containerName)
  } else if (ts.isEnumDeclaration(node)) {
    addSymbol(node.name, 'enum', containerName)
  } else if (ts.isVariableDeclaration(node) && node.name && ts.isIdentifier(node.name) && node.initializer && isFunctionInitializer(node.initializer)) {
    addSymbol(node.name, 'function', containerName)
  }
  ts.forEachChild(node, child => visit(child, containerName))
}

visit(sourceFile, null)
process.stdout.write(JSON.stringify({ symbols }))
