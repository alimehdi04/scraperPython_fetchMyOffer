from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import httpx
import asyncio
import sys
import urllib.parse
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

app = FastAPI(title="AI Opportunity Hunter - Scraper Worker")

# --- DATA MODELS ---
class ScrapeRequest(BaseModel):
    query: str
    location: Optional[str] = "India"
    platform: Optional[str] = "internshala" # 🛑 NEW FIELD
    callback_url: str
    job_id: str

class JobResult(BaseModel):
    title: str
    company: str
    url: str
    description: str


async def scrape_naukri(query: str) -> List[dict]:
    print(f"[*] Starting Playwright for Naukri query: {query}")
    jobs = []
    
    formatted_query = query.replace(" ", "-").lower()
    target_url = f"https://www.naukri.com/{formatted_query}-jobs"
    
    keywords = [word.lower() for word in query.split()]

    # 🛑 THE NEW STEALTH V2 API WRAPPER
    async with Stealth().use_async(async_playwright()) as p:
        
        # Keep the arguments to hide automation
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--window-size=1920,1080"
            ]
        )
        
        # Spoof realistic browser headers
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
            }
        )
        
        # Because we used Stealth().use_async() above, EVERY page created 
        # in this context automatically has 100% stealth injected into it!
        page = await context.new_page()
        
        try:
            # We still pass the referer to look like we came from Google
            await page.goto(target_url, timeout=60000, wait_until='domcontentloaded', referer="https://www.google.com/")
            
            page_title = await page.title()
            print(f"[*] Naukri page loaded. Page Title: '{page_title}'")
            
            # Wait for the specific job wrapper to appear in the DOM
            await page.wait_for_selector('.srp-jobtuple-wrapper', timeout=15000)
            await page.wait_for_timeout(3000) # Buffer for React to finish hydrating
            
            jobs_data = await page.evaluate('''
                (keywords) => {
                    const jobs = [];
                    const items = document.querySelectorAll('.srp-jobtuple-wrapper');
                    
                    items.forEach((item) => {
                        try {
                            const titleElem = item.querySelector('a.title');
                            const title = titleElem ? titleElem.innerText.trim() : '';
                            if (!title) return;
                            
                            const companyElem = item.querySelector('a.comp-name');
                            const company = companyElem ? companyElem.innerText.trim() : '';
                            
                            let link = titleElem ? titleElem.getAttribute('href') : '';
                            if (link && !link.startsWith('http')) {
                                link = 'https://www.naukri.com' + link;
                            }
                            
                            const detailsElem = item.querySelector('.job-details');
                            const description = detailsElem ? detailsElem.innerText.replace(/\\n/g, ' | ') : 'Details not provided';
                            
                            const titleLower = title.toLowerCase();
                            const descLower = description.toLowerCase();
                            let isMatch = false;
                            for (let word of keywords) {
                                if (titleLower.includes(word) || descLower.includes(word)) {
                                    isMatch = true;
                                    break;
                                }
                            }
                            
                            if (!isMatch) return;
                            
                            jobs.push({
                                title: title,
                                company: company,
                                url: link,
                                description: description,
                            });
                            
                        } catch (e) {
                            console.error('Error parsing Naukri job:', e);
                        }
                    });
                    
                    return jobs;
                }
            ''', keywords)
            
            print(f"[*] Found {len(jobs_data)} jobs matching '{query}' on Naukri")
            
            for job in jobs_data:
                jobs.append({
                    "title": job.get('title', 'N/A'),
                    "company": job.get('company', 'N/A'),
                    "url": job.get('url', ''),
                    "description": job.get('description', 'No description available')[:500] 
                })
            
        except Exception as e:
            print(f"[!] Error scraping Naukri: {e}")
        finally:
            await browser.close()
            
    return jobs


async def scrape_internshala(query: str) -> List[dict]:
    print(f"[*] Starting Playwright for query: {query}")
    jobs = []
    
    formatted_query = query.replace(" ", "-").lower()
    target_url = f"https://internshala.com/internships/keywords-{formatted_query}/"
    
    keywords = [word.lower() for word in query.split()]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            await page.goto(target_url, timeout=60000, wait_until='domcontentloaded')
            print(f"[*] Page loaded")
            
            await page.wait_for_timeout(3000)
            
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
                            
                            const titleLower = title.toLowerCase();
                            const companyLower = company.toLowerCase();
                            const descLower = description.toLowerCase();
                            
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
            ''', keywords)
            
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
    print(f"[*] Background task started for Job ID: {request.job_id} on platform: {request.platform}")
    
    # --- ROUTING LOGIC ---
    if request.platform and request.platform.lower() == "naukri":
        scraped_data = await scrape_naukri(request.query)
    else:
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

@app.api_route("/ping", methods=["GET", "HEAD"])
def ping():
    return "pong"

if __name__ == "__main__":
    import os
    import uvicorn
    # The cloud provider will set the PORT environment variable.
    # If it's not set (like on your local machine), it defaults to 8000.
    port = int(os.environ.get("PORT", 8000))
    
    print(f"🚀 Starting server on 0.0.0.0:{port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port)