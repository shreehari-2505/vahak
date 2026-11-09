package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
)

// Define the exact JSON structure
type FileItem struct {
	Name  string `json:"name"`
	IsDir bool   `json:"is_dir"`
}

func scanHandler(w http.ResponseWriter, r *http.Request) {
	// os.ReadDir is the Go equivalent of os.scandir
	entries, err := os.ReadDir(".")
	if err != nil {
		http.Error(w, `{"error": "Failed to read directory"}`, http.StatusInternalServerError)
		return
	}

	// Pre-allocate the slice (array) for speed
	items := make([]FileItem, 0, len(entries))
	for _, entry := range entries {
		items = append(items, FileItem{
			Name:  entry.Name(),
			IsDir: entry.IsDir(),
		})
	}

	// Stream the JSON directly back to the client
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(items)
}

func main() {
	http.HandleFunc("/api/v1/scan", scanHandler)
	log.Println("Go Server running on http://127.0.0.1:8081")
	// Start the server (using 8081 so we don't hit the C++ or Python ports)
	log.Fatal(http.ListenAndServe(":8081", nil))
}