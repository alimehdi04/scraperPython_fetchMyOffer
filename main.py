from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import httpx
import asyncio
import sys
from playwright.async_api import async_playwright

# if sys.platform == "win32":
#     asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = FastAPI(title="AI Opportunity Hunter - Scraper Worker")

# --- DATA MODELS ---
class ScrapeRequest(BaseModel):
    query: str
    location: Optional[str] = "India"
    callback_url: str
    job_id: str

class JobResult(BaseModel):
    title: str
    company: str
    url: str
    description: str

async def scrape_internshala(query: str) -> List[dict]:
    print(f"[*] Starting Playwright for query: {query}")
    jobs = []
    
    formatted_query = query.replace(" ", "-").lower()
    target_url = f"https://internshala.com/internships/keywords-{formatted_query}/"
    
    # We create an array of keywords from the query to pass to JS
    # e.g., "Java Backend Intern" -> ["java", "backend", "intern"]
    keywords = [word.lower() for word in query.split()]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            await page.goto(target_url, timeout=60000, wait_until='domcontentloaded')
            print(f"[*] Page loaded")
            
            await page.wait_for_timeout(3000)
            
            # Pass the 'keywords' array directly into the JS evaluate function
            jobs_data = await page.evaluate('''
                (keywords) => {
                    const jobs = [];
                    const items = document.querySelectorAll('.individual_internship');
                    
                    items.forEach((item) => {
                        try {
                            const titleElem = item.querySelector('.job-internship-name a, .job-title-href, h3 a');
                            const title = titleElem ? titleElem.innerText.trim() : '';
                            if (!title) return;
                            
                            const companyElem = item.querySelector('.company-name, .heading_6.company_name p, .company_and_premium p');
                            const company = companyElem ? companyElem.innerText.trim() : '';
                            
                            const linkElem = item.querySelector('.job-title-href, a.job-title-href, h3 a');
                            let link = linkElem ? linkElem.getAttribute('href') : '';
                            
                            let fullUrl = '';
                            if (link) {
                                if (link.startsWith('http')) fullUrl = link;
                                else if (link.startsWith('/')) fullUrl = 'https://internshala.com' + link;
                            }
                            
                            const descElem = item.querySelector('.about_job .text, .text');
                            const description = descElem ? descElem.innerText.trim() : '';
                            
                            // Dynamic Filtering Logic
                            const titleLower = title.toLowerCase();
                            const companyLower = company.toLowerCase();
                            const descLower = description.toLowerCase();
                            
                            // Check if ANY of the search keywords exist in the job text
                            let isMatch = false;
                            for (let word of keywords) {
                                if (titleLower.includes(word) || descLower.includes(word) || companyLower.includes(word)) {
                                    isMatch = true;
                                    break;
                                }
                            }
                            
                            if (!isMatch) return;
                            
                            jobs.push({
                                title: title,
                                company: company,
                                url: fullUrl,
                                description: description,
                            });
                            
                        } catch (e) {
                            console.error('Error parsing job:', e);
                        }
                    });
                    
                    return jobs;
                }
            ''', keywords) # Pass the Python list to JS
            
            print(f"[*] Found {len(jobs_data)} jobs matching '{query}'")
            
            for job in jobs_data:
                jobs.append({
                    "title": job.get('title', 'N/A'),
                    "company": job.get('company', 'N/A'),
                    "url": job.get('url', ''),
                    "description": job.get('description', 'No description available')[:500] 
                })
            
        except Exception as e:
            print(f"[!] Error: {e}")
        finally:
            await browser.close()
            
    return jobs

async def process_scrape_and_callback(request: ScrapeRequest):
    print(f"[*] Background task started for Job ID: {request.job_id}")
    
    scraped_data = await scrape_internshala(request.query)


    # --- PRINT THE SCRAPED JOBS TO CONSOLE ---
    print("\n" + "="*80)
    print(f"[✓] SCRAPED {len(scraped_data)} JOBS FOR QUERY: '{request.query}'")
    print("="*80)
    
    if scraped_data:
        for i, job in enumerate(scraped_data, 1):
            print(f"\n--- JOB #{i} ---")
            print(f"Title: {job.get('title', 'N/A')}")
            print(f"Company: {job.get('company', 'N/A')}")
            print(f"URL: {job.get('url', 'N/A')}")
            desc = job.get('description', 'N/A')
            print(f"Description: {desc[:150]}..." if len(desc) > 150 else f"Description: {desc}")
        
        print("\n" + "="*80)
        print(f"[✓] TOTAL JOBS SCRAPED: {len(scraped_data)}")
        print("="*80 + "\n")
    else:
        print("\n[!] No jobs found for this query\n")

    
    payload = {
        "jobId": request.job_id,
        "status": "SUCCESS" if scraped_data else "FAILED",
        "data": scraped_data
    }
    
    print(f"[*] Sending {len(scraped_data)} jobs to {request.callback_url}")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(request.callback_url, json=payload, timeout=10.0)
            print(f"[*] Webhook delivered. Status Code: {response.status_code}")
        except Exception as e:
            print(f"[!] Failed to deliver webhook: {e}")



# --- API ENDPOINTS ---
@app.post("/api/v1/scrape")
async def trigger_scrape(request: ScrapeRequest, background_tasks: BackgroundTasks):
    """
    Spring Boot hits this endpoint. We immediately return 202 Accepted,
    and hand the heavy Playwright scraping off to a background task.
    """
    background_tasks.add_task(process_scrape_and_callback, request)
    return {
        "message": "Scrape request accepted. Processing in background.",
        "job_id": request.job_id
    }

@app.get("/health")
def health_check():
    return {"status": "Scraper is alive and ready."}