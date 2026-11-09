#include "httplib.h"
#include <iostream>

int main() {
    httplib::Server svr;
    
    // Match the 100 concurrent connections
    svr.new_task_queue = [] { return new httplib::ThreadPool(100); };

    // Automatically serve files from the current directory
    svr.set_mount_point("/api/v1/transfer", ".");

    std::cout << "C++ Streaming Server on :8080\n";
    svr.listen("127.0.0.1", 8080);
    return 0;
}