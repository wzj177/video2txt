#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI听世界 - 应用程序入口
"""

from app.main import app

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=19080, log_level="info")
