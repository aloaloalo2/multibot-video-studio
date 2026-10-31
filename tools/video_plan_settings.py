#!/usr/bin/env python3
"""Compatibility entry point. Channel settings now belong to Studio."""
from video_plan import studio_request
if __name__ == "__main__":
    base = "http://127.0.0.1:8770"
    studio_request(base, "/api/health")
    print("Налаштування каналів відкриваються у VideoKey Studio: " + base + "/")
