package main

import (
	"log"
	"net/http"
)

func main() {
	http.HandleFunc("/api/v1/transfer/video", func(w http.ResponseWriter, r *http.Request) {
		// http.ServeFile uses Linux Zero-Copy (sendfile) automatically under the hood
		http.ServeFile(w, r, "test_video.mp4")
	})

	log.Println("Go Streaming Server on :8081")
	log.Fatal(http.ListenAndServe(":8081", nil))
}