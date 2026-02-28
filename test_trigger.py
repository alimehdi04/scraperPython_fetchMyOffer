import httpx
import asyncio
import uuid

async def test_scraper():
    # The URL where your FastAPI server is listening
    api_url = "http://localhost:8000/api/v1/scrape"
    
    # The payload we are sending (simulating Spring Boot's request)
    payload = {
        "query": "Java Intern",
        "location": "India",
        # We use httpbin.org as a temporary dummy receiver for the webhook
        "callback_url": "https://httpbin.org/post", 
        "job_id": f"job-{uuid.uuid4().hex[:8]}"
    }

    print(f"🚀 Sending scrape request to {api_url}...")
    print(f"📦 Payload: {payload}\n")

    async with httpx.AsyncClient() as client:
        try:
            # 1. We make the request and wait for the immediate 202 Accepted response
            response = await client.post(api_url, json=payload)
            
            print(f"✅ Received immediate response from FastAPI:")
            print(f"Status Code: {response.status_code}")
            print(f"Response Body: {response.json()}\n")
            
            print("⏳ Now watch your FastAPI terminal to see Playwright working in the background!")
            
        except Exception as e:
            print(f"❌ Error connecting to FastAPI: {e}")

if __name__ == "__main__":
    asyncio.run(test_scraper())