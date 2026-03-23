package service

import "testing"

func TestBuildMessage(t *testing.T) {
    if got := BuildMessage("suitcode"); got != "hello, suitcode" {
        t.Fatalf("unexpected message: %s", got)
    }
}
