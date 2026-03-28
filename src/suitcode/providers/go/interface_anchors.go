package main

import (
	"encoding/json"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
)

type anchor struct {
	Line   int    `json:"line"`
	Column int    `json:"column"`
	Kind   string `json:"kind"`
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: interface_anchors <file>")
		os.Exit(2)
	}
	filePath := os.Args[len(os.Args)-1]
	fset := token.NewFileSet()
	parsed, err := parser.ParseFile(fset, filePath, nil, parser.SkipObjectResolution)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	anchors := collectAnchors(fset, parsed)
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(anchors); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func collectAnchors(fset *token.FileSet, file *ast.File) []anchor {
	seen := map[string]struct{}{}
	anchors := make([]anchor, 0)
	add := func(pos token.Pos, kind string) {
		if !pos.IsValid() {
			return
		}
		position := fset.Position(pos)
		if position.Line < 1 || position.Column < 1 {
			return
		}
		key := fmt.Sprintf("%d:%d:%s", position.Line, position.Column, kind)
		if _, exists := seen[key]; exists {
			return
		}
		seen[key] = struct{}{}
		anchors = append(anchors, anchor{Line: position.Line, Column: position.Column, Kind: kind})
	}

	ast.Inspect(file, func(node ast.Node) bool {
		switch typed := node.(type) {
		case *ast.TypeSpec:
			if _, ok := typed.Type.(*ast.InterfaceType); ok {
				add(typed.Name.Pos(), "interface_declaration")
			}
		case *ast.ValueSpec:
			collectTypeExprAnchors(typed.Type, add)
		case *ast.Field:
			collectTypeExprAnchors(typed.Type, add)
		case *ast.TypeAssertExpr:
			collectTypeExprAnchors(typed.Type, add)
		case *ast.CompositeLit:
			collectTypeExprAnchors(typed.Type, add)
		}
		return true
	})
	return anchors
}

func collectTypeExprAnchors(expr ast.Expr, add func(token.Pos, string)) {
	if expr == nil {
		return
	}
	switch typed := expr.(type) {
	case *ast.Ident:
		add(typed.NamePos, "type_usage")
	case *ast.SelectorExpr:
		add(typed.Sel.NamePos, "type_usage")
	case *ast.StarExpr:
		collectTypeExprAnchors(typed.X, add)
	case *ast.ArrayType:
		collectTypeExprAnchors(typed.Elt, add)
	case *ast.MapType:
		collectTypeExprAnchors(typed.Key, add)
		collectTypeExprAnchors(typed.Value, add)
	case *ast.ChanType:
		collectTypeExprAnchors(typed.Value, add)
	case *ast.Ellipsis:
		collectTypeExprAnchors(typed.Elt, add)
	case *ast.IndexExpr:
		collectTypeExprAnchors(typed.X, add)
	case *ast.IndexListExpr:
		collectTypeExprAnchors(typed.X, add)
	case *ast.ParenExpr:
		collectTypeExprAnchors(typed.X, add)
	case *ast.FuncType:
		if typed.Params != nil {
			for _, field := range typed.Params.List {
				collectTypeExprAnchors(field.Type, add)
			}
		}
		if typed.Results != nil {
			for _, field := range typed.Results.List {
				collectTypeExprAnchors(field.Type, add)
			}
		}
	}
}
