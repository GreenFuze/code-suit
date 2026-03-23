package service

import "example.com/acme/go-demo/pkg/util"

func BuildMessage(name string) string {
    return util.GreetingPrefix() + ", " + name
}
