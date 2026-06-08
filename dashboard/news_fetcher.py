import requests
import xml.etree.ElementTree as ET
import json
import time
from datetime import datetime, date

NEWS_URL = "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"
OUTPUT_FILE = "news.json"
FETCH_INTERVAL_SECONDS = 600  # 10 minutes

def fetch_news():
    """Fetches news headlines from CNBC RSS feed."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(NEWS_URL, headers=headers)
        response.raise_for_status()

        root = ET.fromstring(response.content)
        headlines = []
        
        for item in root.findall('.//item')[:20]: # Limit to top 20 latest headlines
            title = item.find('title').text if item.find('title') is not None else "No Title"
            link = item.find('link').text if item.find('link') is not None else "#"
            pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ""
            
            headlines.append({
                "time": pub_date.replace(" GMT", "").replace(" +0000", ""),
                "headline": title,
                "link": link,
                "source": "CNBC"
            })

        return headlines

    except requests.exceptions.RequestException as e:
        print(f"Error fetching news: {e}")
        return None
    except Exception as e:
        print(f"Error parsing news XML: {e}")
        return None

def main():
    """Main loop to fetch and save news periodically."""
    while True:
        print("Fetching latest financial news...")
        headlines = fetch_news()
        if headlines:
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                payload = {"last_updated": datetime.now().isoformat(), "headlines": headlines}
                json.dump(payload, f, indent=4)
            print(f"Successfully saved {len(headlines)} headlines to {OUTPUT_FILE}.")
        print(f"Waiting for {FETCH_INTERVAL_SECONDS // 60} minutes until next fetch...")
        time.sleep(FETCH_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()