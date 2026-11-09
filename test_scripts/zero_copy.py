import asyncio
import os

async def handle_client(reader, writer):
    # Read the incoming HTTP GET request
    await reader.readuntil(b'\r\n\r\n')
    
    # Prepare minimal HTTP headers
    file_size = os.path.getsize("test_video.mp4")
    headers = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: video/mp4\r\n"
        f"Content-Length: {file_size}\r\n\r\n"
    ).encode('utf-8')
    
    writer.write(headers)
    await writer.drain()

    # THE ZERO-COPY MAGIC:
    # Tell the Ubuntu kernel to pipe the file descriptor directly to the socket
    loop = asyncio.get_running_loop()
    with open("test_video.mp4", "rb") as f:
        await loop.sendfile(writer.transport, f)
    
    writer.close()

async def main():
    server = await asyncio.start_server(handle_client, '127.0.0.1', 8002)
    print("Python Zero-Copy Server running on :8002")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())