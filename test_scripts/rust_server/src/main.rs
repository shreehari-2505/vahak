use actix_web::{get, App, HttpResponse, HttpServer, Responder};
use serde::Serialize;
use std::fs;

#[derive(Serialize)]
struct FileItem {
    name: String,
    is_dir: bool,
}

#[get("/api/v1/scan")]
async fn scan_handler() -> impl Responder {
    let mut items = Vec::new();

    // std::fs::read_dir is Rust's safe wrapper around the OS directory scan
    if let Ok(entries) = fs::read_dir(".") {
        for entry in entries.flatten() {
            let is_dir = entry.file_type().map(|ft| ft.is_dir()).unwrap_or(false);
            let name = entry.file_name().to_string_lossy().into_owned();
            items.push(FileItem { name, is_dir });
        }
    }

    // Actix automatically serializes the Vec<FileItem> to JSON
    HttpResponse::Ok().json(items)
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    println!("Rust (Actix-Web) Server running on http://127.0.0.1:8082");
    
    // Actix automatically scales to the number of physical CPU cores
    HttpServer::new(|| {
        App::new().service(scan_handler)
    })
    .bind(("127.0.0.1", 8082))?
    .run()
    .await
}