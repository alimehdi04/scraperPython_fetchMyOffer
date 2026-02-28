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

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            await page.goto(target_url, timeout=60000, wait_until='domcontentloaded')
            print(f"[*] Page loaded")
            
            # Wait a bit for content to load
            await page.wait_for_timeout(5000)
            
            # Extract all job data using JavaScript with better filtering
            jobs_data = await page.evaluate('''
                () => {
                    const jobs = [];
                    const items = document.querySelectorAll('.individual_internship');
                    
                    items.forEach((item) => {
                        try {
                            // Get title
                            const titleElem = item.querySelector('.job-internship-name a, .job-title-href, h3 a');
                            const title = titleElem ? titleElem.innerText.trim() : '';
                            
                            // Skip if no title (likely an ad or malformed entry)
                            if (!title) return;
                            
                            // Get company
                            const companyElem = item.querySelector('.company-name, .heading_6.company_name p, .company_and_premium p');
                            const company = companyElem ? companyElem.innerText.trim() : '';
                            
                            // Get link
                            const linkElem = item.querySelector('.job-title-href, a.job-title-href, h3 a');
                            let link = linkElem ? linkElem.getAttribute('href') : '';
                            
                            // Construct full URL
                            let fullUrl = '';
                            if (link) {
                                if (link.startsWith('http')) {
                                    fullUrl = link;
                                } else if (link.startsWith('/')) {
                                    fullUrl = 'https://internshala.com' + link;
                                }
                            }
                            
                            // Get description
                            const descElem = item.querySelector('.about_job .text, .text');
                            const description = descElem ? descElem.innerText.trim() : '';
                            
                            // Filter: Only include Java-related internships
                            const titleLower = title.toLowerCase();
                            const companyLower = company.toLowerCase();
                            const descLower = description.toLowerCase();
                            
                            // Check if it's Java-related
                            const isJavaRelated = 
                                titleLower.includes('java') || 
                                companyLower.includes('java') || 
                                descLower.includes('java') ||
                                titleLower.includes('developer') && descLower.includes('spring') ||
                                titleLower.includes('programming') && descLower.includes('java');
                            
                            // Only include if it's Java-related AND not an ad
                            if (!isJavaRelated) return;
                            
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
            ''')
            
            print(f"[*] Found {len(jobs_data)} Java-related jobs")
            
            # Convert to your desired format
            for job in jobs_data:
                jobs.append({
                    "title": job.get('title', 'N/A'),
                    "company": job.get('company', 'N/A'),
                    "url": job.get('url', ''),
                    "description": job.get('description', 'No description available')[:500]  # Limit description length
                })
            
        except Exception as e:
            print(f"[!] Error: {e}")
            # Take a screenshot for debugging
            try:
                await page.screenshot(path="error_debug.png")
                print("[*] Saved error screenshot to error_debug.png")
            except:
                pass
        finally:
            await browser.close()
            
    return jobs




# --- BACKGROUND TASK WORKER ---

async def process_scrape_and_callback(request: ScrapeRequest):
    print(f"[*] Background task started for Job ID: {request.job_id}")
    
    # 1. Do the dirty work
    scraped_data = await scrape_internshala(request.query)
    
    # PRINT THE SCRAPED JOBS TO CONSOLE
    print("\n" + "="*80)
    print(f"[✓] SCRAPED {len(scraped_data)} JAVA-RELATED JOBS FOR QUERY: '{request.query}'")
    print("="*80)
    
    for i, job in enumerate(scraped_data, 1):
        print(f"\n--- JAVA JOB #{i} ---")
        print(f"Title: {job.get('title', 'N/A')}")
        print(f"Company: {job.get('company', 'N/A')}")
        print(f"URL: {job.get('url', 'N/A')}")
        desc = job.get('description', 'N/A')
        print(f"Description: {desc[:150]}..." if len(desc) > 150 else f"Description: {desc}")
    
    print("\n" + "="*80)
    print(f"[✓] TOTAL JAVA JOBS: {len(scraped_data)}")
    print("="*80 + "\n")
    
    # 2. Prepare the payload for Spring Boot
    payload = {
        "jobId": request.job_id,
        "status": "SUCCESS" if scraped_data else "FAILED",
        "data": scraped_data
    }
    
    # 3. Fire the webhook back to Java
    print(f"[*] Sending {len(scraped_data)} Java jobs to {request.callback_url}")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(request.callback_url, json=payload, timeout=10.0)
            print(f"[*] Webhook delivered. Spring Boot responded: {response.status_code}")
            
            if response.status_code == 200:
                print(f"[*] Response from Spring Boot: {response.text[:200]}...")
                
        except Exception as e:
            print(f"[!] Failed to deliver webhook to Spring Boot: {e}")


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