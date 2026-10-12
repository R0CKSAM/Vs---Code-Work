import os
import uvicorn

if __name__ == "__main__":
    os.environ["PORT"] = "6805"
    os.environ["HOST"] = "0.0.0.0"
    from app import app
    print("Office AI Background Remover starting at http://192.168.50.134:6805")
    uvicorn.run(app, host="0.0.0.0", port=6805)
