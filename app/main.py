from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, APIRouter, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import uuid
import logging
from typing import Dict, List
from app.claude_youtube_sum import process_youtube_summary
from app.schemas import DownloadRequest, TaskResponse, TaskStatus, TaskResult

"""
TODO: need to create a function that detects if the transcription hits the maximum content size limit

then split the transcription into chunks and then see if there is an openai API paradigm for that.
"""

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def some_function():
    logger.info("this is a log message")

some_function() # TEST

app = FastAPI()

# Add CORS middleware to allow requests from your frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active connections
class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.ping_interval = 30  # seconds
        self.ping_timeout = 10   # seconds

    async def connect(self, websocket: WebSocket, task_id: str):
        await websocket.accept()
        if task_id not in self.active_connections:
            self.active_connections[task_id] = []
        self.active_connections[task_id].append(websocket)

    def disconnect(self, websocket: WebSocket, task_id: str):
        if task_id in self.active_connections:
            if websocket in self.active_connections[task_id]:
                self.active_connections[task_id].remove(websocket)
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]

    async def broadcast_update(self, task_id: str, message: dict):
        if task_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[task_id]:
                try:
                    await connection.send_json(message)
                except RuntimeError:
                    disconnected.append(connection)
            
            # Clean up disconnected clients
            for conn in disconnected:
                self.disconnect(conn, task_id)

manager = ConnectionManager()

# In-memory task storage
tasks: Dict[str, Dict] = {}

@app.post("/start-download")
async def start_download(request: DownloadRequest, background_tasks: BackgroundTasks):
    # Validate URL
    if not request.url or "youtube.com" not in request.url and "youtu.be" not in request.url:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")
    
    # Create task
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "status": TaskStatus.PENDING,
        "url": request.url,
        "detail_level": request.detail_level
    }
    
    # Process in background
    background_tasks.add_task(process_task, task_id, request.url, request.detail_level)
    
    return TaskResponse(task_id=task_id, status=TaskStatus.PENDING)

@app.get("/task/{task_id}")
async def get_task_status(task_id: str):
    """Get the current status of a task"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task_data = tasks[task_id]
    
    return {
        "task_id": task_id,
        "status": task_data["status"],
        "summary": task_data.get("summary"),
        "error": task_data.get("error")
    }

@app.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    if task_id not in tasks:
        await websocket.close(code=1000)
        return
        
    await manager.connect(websocket, task_id)
    
    try:
        # Send initial status
        await websocket.send_json({
            "task_id": task_id,
            "status": tasks[task_id]["status"],
            "summary": tasks[task_id].get("summary"),
            "error": tasks[task_id].get("error")
        })
        
        # Implement proper ping/pong mechanism
        while True:
            try:
                # Wait for either a ping timeout or a message
                message = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=manager.ping_interval
                )
                
                # If we receive a ping, respond with pong
                if message == "ping":
                    await websocket.send_text("pong")
                
            except asyncio.TimeoutError:
                try:
                    # Send ping to check if client is still there
                    await websocket.send_text("ping")
                    # Wait for pong response
                    await asyncio.wait_for(
                        websocket.receive_text(),
                        timeout=manager.ping_timeout
                    )
                except (asyncio.TimeoutError, RuntimeError):
                    # If no pong received, close the connection
                    await websocket.close(code=1000)
                    break
            
    except WebSocketDisconnect:
        manager.disconnect(websocket, task_id)
    except Exception as e:
        logger.error(f"WebSocket error for task {task_id}: {str(e)}")
        manager.disconnect(websocket, task_id)
        await websocket.close(code=1000)

async def process_task(task_id: str, url: str, detail: str):
    try:
        # Update task status
        tasks[task_id]["status"] = TaskStatus.IN_PROGRESS
        await manager.broadcast_update(task_id, {
            "task_id": task_id, 
            "status": TaskStatus.IN_PROGRESS
        })
        
        # Process the YouTube summary
        try:
            summary = await process_youtube_summary(url, detail)
            
            # Update task with result
            tasks[task_id]["summary"] = summary
            tasks[task_id]["status"] = TaskStatus.COMPLETED
            
            # Broadcast the completion
            await manager.broadcast_update(task_id, {
                "task_id": task_id,
                "status": TaskStatus.COMPLETED,
                "summary": summary
            })
            
        except Exception as e:
            logger.error(f"Error processing task {task_id}: {str(e)}")
            tasks[task_id]["status"] = TaskStatus.FAILED
            tasks[task_id]["error"] = str(e)
            
            # Broadcast the failure
            await manager.broadcast_update(task_id, {
                "task_id": task_id,
                "status": TaskStatus.FAILED,
                "error": str(e)
            })
            
    except Exception as e:
        logger.error(f"Internal error in task {task_id}: {str(e)}")
        if task_id in tasks:
            tasks[task_id]["status"] = TaskStatus.FAILED
            tasks[task_id]["error"] = f"Internal server error: {str(e)}"
            
            # Broadcast the failure
            await manager.broadcast_update(task_id, {
                "task_id": task_id,
                "status": TaskStatus.FAILED,
                "error": f"Internal server error: {str(e)}"
            })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
