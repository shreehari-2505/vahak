#include "httplib.h"
#include <filesystem>
#include <string>
#include <iostream>

namespace fs = std::filesystem;

int main() {
    httplib::Server svr;

    // THE UPGRADE: 
    // Force C++ to open 500 concurrent lanes to match Uvicorn's capacity
    svr.new_task_queue = [] { return new httplib::ThreadPool(500); };

    svr.Get("/api/v1/scan", [](const httplib::Request &, httplib::Response &res) {
        std::string json = "[";
        bool first = true;
        
        try {
            for (const auto & entry : fs::directory_iterator(".")) {
                if (!first) json += ",";
                json += "{\"name\":\"" + entry.path().filename().string() + "\",\"is_dir\":" + (entry.is_directory() ? "true" : "false") + "}";
                first = false;
            }
        } catch (...) {
            res.status = 500;
            res.set_content("{\"error\": \"Failed to read directory\"}", "application/json");
            return;
        }
        
        json += "]";
        res.set_content(json, "application/json");
    });

    std::cout << "Upgraded C++ Server running on http://127.0.0.1:8080\n";
    svr.listen("127.0.0.1", 8080);
    
    return 0;
}