package main

import "log"

func main() {
    log.Fatal(NewApp().Listen(":8080"))
}
