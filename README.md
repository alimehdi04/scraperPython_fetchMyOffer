# 🕸️ Fetch My Offer - Playwright Scraper Worker

This repository contains the standalone Python web-scraping microservice for the **Fetch My Offer** ecosystem. It is a FastAPI application that uses asynchronous Playwright to navigate dynamic, JavaScript-heavy job boards, extract job listings, and fire webhooks back to the main Spring Boot orchestrator.

## ⚡ How It Works

1. The Spring Boot orchestrator sends an HTTP `POST` request to this API with a specific search query (e.g., "Java Backend Developer").
2. The API immediately returns a `202 Accepted` response to prevent blocking the main server.
3. A background task launches a headless Chromium browser using Playwright.
4. It navigates the target job board, executes custom JavaScript to parse the DOM, and extracts the Job Title, Company, URL, and Description.
5. It packages the extracted data into a JSON payload and delivers it via webhook back to the orchestrator for AI evaluation.

## 🛠️ Tech Stack

* **Language:** Python 3.11
* **Framework:** FastAPI, Uvicorn
* **Scraping Engine:** Microsoft Playwright (Async API)
* **HTTP Client:** HTTPX
* **Deployment:** Docker (using official Microsoft Playwright image)

## 🐳 Cloud Deployment (Docker)

Deploying headless browsers to the cloud requires specific underlying OS dependencies. This project utilizes a custom `Dockerfile` built on top of the official Microsoft Playwright image to ensure Chromium runs flawlessly in a containerized environment.

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy
```

# See the included Dockerfile for full build instructions
