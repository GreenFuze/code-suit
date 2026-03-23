package main

import (
    "fmt"

    "example.com/acme/go-demo/internal/service"
)

func main() {
    fmt.Println(service.BuildMessage("world"))
}
