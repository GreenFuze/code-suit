package main

import (
	"encoding/json"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
)

type symbol struct {
	Name        string `json:"name"`
	Kind        string `json:"kind"`
	LineStart   int    `json:"line_start"`
	LineEnd     int    `json:"line_end"`
	ColumnStart int    `json:"column_start"`
	ColumnEnd   int    `json:"column_end"`
	Signature   string `json:"signature,omitempty"`
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: structural_symbols <file>")
		os.Exit(2)
	}
	filePath := os.Args[len(os.Args)-1]
	fset := token.NewFileSet()
	parsed, err := parser.ParseFile(fset, filePath, nil, parser.SkipObjectResolution)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	items := collectSymbols(fset, parsed)
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(map[string][]symbol{"symbols": items}); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func collectSymbols(fset *token.FileSet, file *ast.File) []symbol {
	items := make([]symbol, 0)
	for _, decl := range file.Decls {
		switch typed := decl.(type) {
		case *ast.FuncDecl:
			kind := "function"
			name := typed.Name.Name
			if typed.Recv != nil && len(typed.Recv.List) > 0 {
				kind = "method"
				name = receiverName(typed.Recv.List[0].Type) + "." + name
			}
			items = append(items, makeSymbol(fset, typed.Name.Pos(), typed.End(), name, kind))
		case *ast.GenDecl:
			for _, spec := range typed.Specs {
				switch typedSpec := spec.(type) {
				case *ast.TypeSpec:
					items = append(items, makeSymbol(fset, typedSpec.Name.Pos(), typedSpec.End(), typedSpec.Name.Name, typeKind(typedSpec.Type)))
				case *ast.ValueSpec:
					kind := "variable"
					if typed.Tok.String() == "const" {
						kind = "constant"
					}
					for _, name := range typedSpec.Names {
						items = append(items, makeSymbol(fset, name.Pos(), typedSpec.End(), name.Name, kind))
					}
				}
			}
		}
	}
	return items
}

func makeSymbol(fset *token.FileSet, start token.Pos, end token.Pos, name string, kind string) symbol {
	startPos := fset.Position(start)
	endPos := fset.Position(end)
	return symbol{
		Name:        name,
		Kind:        kind,
		LineStart:   startPos.Line,
		LineEnd:     endPos.Line,
		ColumnStart: startPos.Column,
		ColumnEnd:   max(endPos.Column, startPos.Column),
	}
}

func typeKind(expr ast.Expr) string {
	switch expr.(type) {
	case *ast.InterfaceType:
		return "interface"
	case *ast.StructType:
		return "struct"
	default:
		return "type"
	}
}

func receiverName(expr ast.Expr) string {
	switch typed := expr.(type) {
	case *ast.Ident:
		return typed.Name
	case *ast.StarExpr:
		return receiverName(typed.X)
	case *ast.IndexExpr:
		return receiverName(typed.X)
	case *ast.IndexListExpr:
		return receiverName(typed.X)
	default:
		return ""
	}
}

func max(left int, right int) int {
	if left > right {
		return left
	}
	return right
}
